"""Embeddings, the vector store, chunking, ingestion and retrieval."""

from __future__ import annotations

from datetime import UTC

import pytest

from app.core.errors import ValidationError
from app.database.enums import DocumentStatus, MemoryStatus
from app.knowledge.chunking import chunk_text
from app.knowledge.extraction import extract
from app.memory.embeddings import HashingEmbedder, cosine, l2_normalise
from app.memory.long_term import LongTermMemory, namespace_for
from app.memory.semantic import DatabaseVectorStore
from app.memory.short_term import ShortTermMemory
from tests.conftest import make_client


class TestEmbeddings:
    def test_identical_text_scores_one(self):
        embedder = HashingEmbedder(512)
        a = embedder.embed_one("What is the VAT rate in Poland?")
        assert cosine(a, embedder.embed_one("What is the VAT rate in Poland?")) == pytest.approx(1.0)

    def test_lexically_similar_text_scores_high_and_unrelated_scores_low(self):
        embedder = HashingEmbedder(512)
        base = embedder.embed_one("What is the VAT rate in Poland?")
        similar = cosine(base, embedder.embed_one("what's the VAT rate in Poland"))
        unrelated = cosine(base, embedder.embed_one("How do I bake sourdough bread?"))
        assert similar > 0.5 > unrelated

    def test_the_fallback_embedder_declares_that_it_is_not_semantic(self):
        assert HashingEmbedder(512).semantic is False

    def test_vectors_are_unit_length(self):
        vector = HashingEmbedder(256).embed_one("some text here")
        assert sum(v * v for v in vector) == pytest.approx(1.0, abs=1e-9)

    def test_cosine_is_safe_on_degenerate_input(self):
        assert cosine([], [1.0]) == 0.0
        assert cosine([0.0, 0.0], [0.0, 0.0]) == 0.0
        assert l2_normalise([0.0, 0.0]) == [0.0, 0.0]


class TestVectorStore:
    def test_search_is_scoped_to_the_client_in_the_query(self, db):
        embedder = HashingEmbedder(256)
        store = DatabaseVectorStore(db)
        for client_id, ref in [("alpha", "a1"), ("beta", "b1")]:
            store.upsert(
                collection="c",
                point_id=f"p:{ref}",
                client_id=client_id,
                vector=embedder.embed_one("shared subject matter"),
                ref_type="memory",
                ref_id=ref,
            )
        db.flush()
        hits = store.search(
            collection="c", client_id="alpha", vector=embedder.embed_one("shared subject matter")
        )
        assert [h.ref_id for h in hits] == ["a1"]

    def test_a_point_cannot_be_overwritten_by_another_client(self, db):
        store = DatabaseVectorStore(db)
        store.upsert(
            collection="c", point_id="p1", client_id="alpha", vector=[1.0], ref_type="m", ref_id="x"
        )
        db.flush()
        with pytest.raises(PermissionError):
            store.upsert(
                collection="c", point_id="p1", client_id="beta", vector=[0.0], ref_type="m", ref_id="x"
            )

    def test_delete_removes_only_the_named_reference(self, db):
        store = DatabaseVectorStore(db)
        for ref in ("x", "y"):
            store.upsert(
                collection="c", point_id=f"p{ref}", client_id="a", vector=[1.0], ref_type="m", ref_id=ref
            )
        db.flush()
        assert store.delete_ref(collection="c", client_id="a", ref_type="m", ref_id="x") == 1
        assert store.count(collection="c", client_id="a") == 1


class TestChunking:
    def test_no_chunk_exceeds_the_configured_size(self):
        text = "\n\n".join(f"Paragraph {i}. " + ("word " * 60) for i in range(10))
        for chunk in chunk_text(text, size=400, overlap=80):
            assert chunk.char_count <= 400

    def test_chunks_overlap_so_a_straddling_fact_is_findable(self):
        text = " ".join(f"sentence{i} about things." for i in range(80))
        chunks = chunk_text(text, size=300, overlap=100)
        assert len(chunks) > 1
        overlaps = [
            bool(set(a.content.split()[-6:]) & set(b.content.split()[:12]))
            for a, b in zip(chunks, chunks[1:], strict=False)
        ]
        assert any(overlaps)

    def test_empty_and_tiny_inputs(self):
        assert chunk_text("") == []
        assert len(chunk_text("short")) == 1

    def test_a_single_token_longer_than_the_chunk_is_still_split(self):
        chunks = chunk_text("x" * 1000, size=300, overlap=50)
        assert chunks and all(c.char_count <= 300 for c in chunks)


class TestExtraction:
    def test_text_csv_and_json(self):
        assert extract(b"hello", "a.txt").text == "hello"
        assert "a | b" in extract(b"a,b\n1,2", "a.csv").text
        assert '"a": 1' in extract(b'{"a":1}', "a.json").text

    def test_an_unsupported_format_is_refused(self):
        with pytest.raises(ValidationError, match="unsupported file type"):
            extract(b"MZ", "a.exe")

    def test_an_empty_file_is_refused(self):
        with pytest.raises(ValidationError):
            extract(b"", "a.txt")

    def test_invalid_json_names_the_position(self):
        with pytest.raises(ValidationError, match="line 1"):
            extract(b"{bad", "a.json")


class TestLongTermMemory:
    def test_expiry_marks_rows_expired_and_removes_them_from_reads(self, db, client_row):
        memory = LongTermMemory(db, client_row.client_id)
        live = memory.write("still valid", source="s", confidence=0.9, ttl_days=30)
        stale = memory.write("out of date", source="s", confidence=0.9, ttl_days=1)
        from datetime import datetime, timedelta

        stale.expires_at = datetime.now(UTC) - timedelta(days=1)
        db.flush()

        assert {item.id for item in memory.list()} == {live.id}
        assert memory.expire_due() == 1
        assert db.get(type(stale), stale.id).status == MemoryStatus.EXPIRED.value

    def test_revocation_hides_an_item(self, db, client_row):
        memory = LongTermMemory(db, client_row.client_id)
        item = memory.write("temporary", source="s", confidence=0.5)
        assert memory.revoke(item.id) is True
        assert memory.list() == []

    def test_one_client_cannot_reach_another_by_id(self, db):
        alpha, _ = make_client(db, "alpha")
        beta, _ = make_client(db, "beta")
        item = LongTermMemory(db, alpha.client_id).write("alpha only", source="s", confidence=0.9)
        db.flush()
        assert LongTermMemory(db, beta.client_id).get(item.id) is None
        assert LongTermMemory(db, beta.client_id).revoke(item.id) is False

    def test_the_namespace_is_derived_from_the_client(self, client_row):
        assert namespace_for(client_row.client_id) == f"memory/{client_row.client_id}/default"


class TestShortTermMemory:
    def test_the_window_returns_recent_turns_oldest_first(self, db, client_row):
        short_term = ShortTermMemory(db, client_row.client_id)
        conversation = short_term.get_or_create(None)
        for index in range(20):
            short_term.append(conversation, "user" if index % 2 == 0 else "assistant", f"turn {index}")
        window = short_term.window(conversation.id, limit=6)
        assert [turn.content for turn in window] == [f"turn {i}" for i in range(14, 20)]

    def test_another_clients_conversation_is_not_reachable(self, db):
        alpha, _ = make_client(db, "alpha")
        beta, _ = make_client(db, "beta")
        conversation = ShortTermMemory(db, alpha.client_id).get_or_create(None)
        db.flush()
        with pytest.raises(PermissionError):
            ShortTermMemory(db, beta.client_id).get_or_create(conversation.id)


class TestIngestion:
    def test_a_document_is_chunked_indexed_and_findable(self, runtime, db, client_row):
        services = runtime.for_session(db, client_row.client_id)
        text = "The Fundusz Pracy is due only from a base at or above the minimum wage. " * 20
        result = services.ingestor.ingest(text.encode(), "rules.txt")
        db.flush()
        assert result.document.status == DocumentStatus.READY.value
        assert result.chunks == result.indexed > 0

        hits = services.retriever.retrieve("When is the Fundusz Pracy due?")
        assert any(item.source == "document" for item in hits.items)

    def test_deleting_a_document_removes_its_vectors(self, runtime, db, client_row):
        services = runtime.for_session(db, client_row.client_id)
        result = services.ingestor.ingest(b"a uniquely identifiable subject matter", "x.txt")
        db.flush()
        services.ingestor.delete(result.document.id)
        db.flush()
        hits = services.retriever.retrieve("uniquely identifiable subject matter")
        assert [item for item in hits.items if item.source == "document"] == []

    def test_an_indexing_failure_marks_the_document_failed_not_ready(
        self, runtime, db, client_row, monkeypatch
    ):
        """A document that is not searchable must never be reported as READY."""
        services = runtime.for_session(db, client_row.client_id)

        def explode(_chunks):
            raise RuntimeError("vector store is down")

        monkeypatch.setattr(services.ingestor.retriever, "index_chunks", explode)
        result = services.ingestor.ingest(b"some content to index", "x.txt")
        assert result.document.status == DocumentStatus.FAILED.value
        assert "indexing failed" in result.document.error


class TestThresholdsAreEvidenceBased:
    """The lexical threshold must sit in the measured gap, not be a guess.

    If a change to the embedder or the threshold closes that gap, this test
    fails — which is the point. A retrieval threshold set by taste either
    drops real matches (and pays a provider for them) or admits noise (and
    grounds an answer in something irrelevant).
    """

    RELATED = [
        ("When is the Fundusz Pracy due?",
         "The Fundusz Pracy is due only from a base at or above the minimum wage."),
        ("What is the 2026 ZUS social base?",
         "The ZUS social contribution base for 2026 is 5203.80 PLN, published by ZUS."),
        ("How are invoices numbered?",
         "Invoices are numbered FV/YYYY/NN in sequence per year."),
        ("What VAT rate applies to services?",
         "The standard VAT rate is 23%; reduced rates of 8% and 5% apply to listed services."),
    ]
    UNRELATED = [
        ("When is the Fundusz Pracy due?", "How do I bake sourdough bread at home?"),
        ("What is the 2026 ZUS social base?", "The train to Krakow leaves from platform four."),
        ("How are invoices numbered?", "Chess openings are classified by ECO code."),
        ("What VAT rate applies to services?", "Photosynthesis converts light into energy."),
    ]

    def _scores(self, pairs):
        embedder = HashingEmbedder(512)
        return [cosine(embedder.embed_one(a), embedder.embed_one(b)) for a, b in pairs]

    def test_the_threshold_sits_between_the_noise_floor_and_real_matches(self, settings):
        threshold = settings.LEXICAL_MEMORY_SIMILARITY_THRESHOLD
        worst_related = min(self._scores(self.RELATED))
        best_unrelated = max(self._scores(self.UNRELATED))
        assert best_unrelated < threshold < worst_related, (
            f"unrelated pairs reach {best_unrelated:.3f} and related pairs fall to "
            f"{worst_related:.3f}; the threshold of {threshold} is not in that gap"
        )

    def test_a_semantic_embedder_gets_the_stricter_pair(self, settings):
        """The two scales are never mixed up."""
        from app.memory.thresholds import for_embedder

        lexical = for_embedder(HashingEmbedder(512), settings)
        assert lexical.semantic is False
        assert lexical.memory == settings.LEXICAL_MEMORY_SIMILARITY_THRESHOLD

        class FakeSemantic(HashingEmbedder):
            semantic = True

        semantic = for_embedder(FakeSemantic(512), settings)
        assert semantic.memory == settings.MEMORY_SIMILARITY_THRESHOLD
        assert semantic.memory > lexical.memory


class TestNearMissVisibility:
    """"Nothing similar exists" and "we scored 0.59 against a 0.80 threshold"
    are different problems with different fixes, and they must not look the
    same. The second one silently re-escalates and pays, forever."""

    def _promote(self, runtime, db, client_row, question, answer):
        from app.learning.fallback_capture import capture
        from app.learning.promotion import PromotionPipeline

        solution = capture(
            db,
            client_row.client_id,
            question=question,
            answer=answer,
            task_type="general",
            provider="anthropic",
            model="m",
            failure_reason="VALIDATION_FAILURE",
            local_attempt="INSUFFICIENT_CONTEXT",
            validation={},
            confidence=0.9,
            classification="INTERNAL",
        ).solution
        PromotionPipeline(
            db,
            client_row.client_id,
            settings=runtime.settings,
            local_provider=runtime.providers.local,
            retriever=runtime.retriever(db, client_row.client_id),
        ).process(solution)
        db.flush()
        return solution

    def test_a_below_threshold_solution_is_reported_not_silently_dropped(
        self, runtime, db, client_row, settings
    ):
        self._promote(
            runtime, db, client_row,
            "What is the VAT rate in Poland?",
            "The standard Polish VAT rate is 23%.",
        )
        # Raise the bar so the same question's near-neighbour cannot clear it.
        settings.LEXICAL_SOLUTION_REUSE_THRESHOLD = 0.99
        from app.memory.thresholds import for_embedder

        runtime.thresholds = for_embedder(runtime.embedder, settings)

        result = runtime.retriever(db, client_row.client_id).retrieve(
            "what's the VAT rate for Poland"
        )
        assert result.solution is None, "the solution should not have been reused"
        assert result.near_miss_score > 0, (
            "a near-miss was found but reported as nothing at all"
        )
        assert result.reuse_threshold == 0.99
        assert result.as_dict()["near_miss_score"] > 0

    def test_a_genuine_absence_reports_zero_not_a_near_miss(
        self, runtime, db, client_row
    ):
        self._promote(
            runtime, db, client_row,
            "What is the VAT rate in Poland?",
            "The standard Polish VAT rate is 23%.",
        )
        result = runtime.retriever(db, client_row.client_id).retrieve(
            "How do I bake sourdough bread at home?"
        )
        assert result.solution is None
        assert result.near_miss_score == 0.0

    def test_the_threshold_in_force_is_always_reported(self, runtime, db, client_row):
        result = runtime.retriever(db, client_row.client_id).retrieve("anything")
        assert result.reuse_threshold == runtime.thresholds.solution_reuse


class TestSemanticThresholdMatchesTheMeasuredScale:
    """The semantic retrieval threshold, pinned to the real-model measurement.

    Measured on nomic-embed-text (audit/REAL_MODEL_GATE.md, 2026-09-09): the
    document chunk that answers a question scores 0.47-0.69 against it
    (median 0.59), a short memory item that answers it 0.66-0.69, unrelated
    question-to-question text at most 0.44 and an unrelated long chunk 0.57
    at the very top (p90 0.49). At the former default of 0.72 document QA
    retrieved nothing, ever (0/10). This test encodes those numbers with an
    exact-cosine embedder so a change to the threshold that would re-open the
    gap fails here, with the measurement in the message.
    """

    QUESTION = "How often are API keys rotated?"
    # text → cosine against the question, each a measured population point.
    SCORES = {
        "Integration API keys are rotated every 90 days.": 0.59,      # median right chunk
        "The printer is on the first floor of the office.": 0.66,     # a short memory item
        "Chess openings are classified by ECO code.": 0.44,           # max unrelated, q-to-q
        "Feed the sourdough starter every twelve hours at room temperature.": 0.49,  # p90 unrelated chunk
    }

    def _embedder(self):
        import math

        from app.memory.embeddings import Embedder

        scores = self.SCORES
        question = self.QUESTION

        class Exact(Embedder):
            semantic = True

            def __init__(self):
                self.dim = 8
                self.id = "exact-cosine"

            def embed(self, texts):
                out = []
                for text in texts:
                    if text.strip() == question:
                        out.append([1.0] + [0.0] * 7)
                        continue
                    key = next((k for k in scores if k in text), None)
                    if key is None:
                        out.append([0.0] * 7 + [1.0])
                        continue
                    c = scores[key]
                    axis = 1 + list(scores).index(key)
                    v = [0.0] * 8
                    v[0], v[axis] = c, math.sqrt(1 - c * c)
                    out.append(v)
                return out

        return Exact()

    def test_the_default_sits_between_measured_noise_and_the_median_right_chunk(self, settings):
        threshold = settings.MEMORY_SIMILARITY_THRESHOLD
        assert 0.44 < threshold <= 0.59, (
            f"MEMORY_SIMILARITY_THRESHOLD={threshold}: unrelated question-to-question text "
            "reaches 0.44 on nomic-embed-text and the median answering chunk scores 0.59; "
            "outside that range the real embedder either admits noise or never finds a "
            "document chunk (audit/REAL_MODEL_GATE.md)"
        )

    def test_an_answering_chunk_and_a_memory_item_are_retrieved_and_noise_is_not(
        self, runtime, db, client_row
    ):
        from sqlalchemy import select

        from app.database.models import MemoryItem
        from app.memory.long_term import LongTermMemory
        from app.memory.thresholds import for_embedder

        runtime.embedder = self._embedder()
        runtime.thresholds = for_embedder(runtime.embedder, runtime.settings)
        services = runtime.for_session(db, client_row.client_id)

        for text in self.SCORES:
            if "printer" in text:
                LongTermMemory(db, client_row.client_id).write(text, source="t", confidence=0.9)
                db.flush()
                services.retriever.index_memory(db.scalars(select(MemoryItem)).first())
            else:
                services.ingestor.ingest(text.encode(), f"{abs(hash(text))}.txt")
        db.flush()

        hits = services.retriever.retrieve(self.QUESTION, task_type="document_qa")
        found = " ".join(item.content for item in hits.items)
        assert "rotated every 90 days" in found, "the answering chunk (0.59) must be retrieved"
        assert "first floor" in found, "the answering memory item (0.66) must be retrieved"
        assert "Chess" not in found and "sourdough" not in found, "noise must stay out"
