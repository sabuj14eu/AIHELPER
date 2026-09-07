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
