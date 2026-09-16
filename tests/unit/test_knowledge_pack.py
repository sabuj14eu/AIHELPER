"""The knowledge pack: parsing, idempotent loading, seeding through the gate,
and the Brother agents that make use of it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.database.enums import DocumentStatus, Route, SolutionStatus
from app.gateway.router import GatewayRequest
from app.knowledge.pack import (
    KnowledgePackLoader,
    PackError,
    discover,
    parse_header,
    parse_solutions,
    render_for_ingestion,
    seed_solutions,
)
from app.learning.promotion import PromotionPipeline
from app.learning.solution_store import SolutionStore

LAWS = """---
title: Freshness Law
domain: platform
repo: sabuj14eu/Sniper-System
sources: CLAUDE.md
verified_on: 2026-09-16
classification: INTERNAL
---

# The Freshness Law

The Sniper-System platform's Freshness Law says that stale data must never
become a valid positive signal. A stale bias is invalid and unused, not
neutral. Missing news is UNKNOWN, not low risk.

# The two witnesses rule

The platform's clock rule says a timestamp is inferred from at least two fresh
independent witnesses, one trading around the clock, or not inferred at all.
"""

SOLUTIONS = """---
title: Platform validated solutions
domain: platform
repo: sabuj14eu/Sniper-System
verified_on: 2026-09-16
---

### One tick cannot fix a clock
question: Why were candles stamped an hour late on 2026-08-20?
answer: The reporter read one tick during the metals rollover break and inferred
the broker offset from it. One tick cannot separate a clock offset from a stale
quote. The fix requires two fresh independent witnesses before any offset is inferred.
evidence: CLAUDE.md "A CLOCK NEEDS TWO WITNESSES", agents/mt5_reporter.detect_broker_offset

### A push is not delivered until the receiver says what it stored
question: Why did the reporter log 5000 candles pushed while the platform dropped rows?
answer: The reporter counted what it sent, not what was stored. Both ends now report
and compare counts, and a push is delivered only when the receiver confirms.
evidence: webhooks.upsert_candles_report

### Not a block
question: this one has no answer line
evidence: nothing
"""


def write_pack(root: Path) -> Path:
    (root / "platform").mkdir(parents=True)
    (root / "platform" / "platform__laws.md").write_text(LAWS, encoding="utf-8")
    (root / "platform" / "platform__validated_solutions.md").write_text(SOLUTIONS, encoding="utf-8")
    (root / "README.md").write_text("# not knowledge\n", encoding="utf-8")
    return root


class TestParsing:
    def test_header_is_split_from_the_body(self):
        header, body = parse_header(LAWS)
        assert header.title == "Freshness Law"
        assert header.domain == "platform"
        assert header.repo == "sabuj14eu/Sniper-System"
        assert header.classification == "INTERNAL"
        assert body.startswith("# The Freshness Law")

    def test_a_file_without_a_header_is_refused(self):
        with pytest.raises(PackError, match="header"):
            parse_header("# just markdown\n")

    def test_title_and_domain_are_required(self):
        with pytest.raises(PackError, match="title"):
            parse_header("---\ndomain: x\n---\nbody")

    def test_domain_must_be_a_slug(self):
        with pytest.raises(PackError, match="slug"):
            parse_header("---\ntitle: t\ndomain: Not A Slug\n---\nbody")

    def test_unknown_classification_is_refused(self):
        with pytest.raises(PackError, match="classification"):
            parse_header("---\ntitle: t\ndomain: d\nclassification: SECRET\n---\nbody")

    def test_solution_blocks_are_parsed_and_incomplete_ones_skipped(self):
        _, body = parse_header(SOLUTIONS)
        seeds = parse_solutions(body, source_file="platform/x.md", domain="platform")
        assert [s.title for s in seeds] == [
            "One tick cannot fix a clock",
            "A push is not delivered until the receiver says what it stored",
        ]
        first = seeds[0]
        assert first.question == "Why were candles stamped an hour late on 2026-08-20?"
        # A multi-line answer is joined into one paragraph.
        assert "\n" not in first.answer
        assert first.answer.endswith("before any offset is inferred.")
        assert "detect_broker_offset" in first.evidence

    def test_discover_skips_only_the_root_readme(self, tmp_path):
        root = write_pack(tmp_path / "pack")
        (root / "platform" / "README.md").write_text(
            "---\ntitle: nested readme\ndomain: platform\n---\nreal content\n", encoding="utf-8"
        )
        found = {f.relative for f in discover(root)}
        assert found == {
            "platform/README.md",
            "platform/platform__laws.md",
            "platform/platform__validated_solutions.md",
        }

    def test_rendered_text_opens_with_a_provenance_banner(self, tmp_path):
        root = write_pack(tmp_path / "pack")
        laws = next(f for f in discover(root) if f.relative.endswith("laws.md"))
        text = render_for_ingestion(laws).decode()
        assert text.startswith("Knowledge pack document: Freshness Law. Domain: platform.")
        assert "Repository: sabuj14eu/Sniper-System." in text
        assert "Verified on: 2026-09-16." in text
        assert "# The Freshness Law" in text


class TestLoading:
    def test_load_is_idempotent_and_tracks_changes(self, runtime, db, client_row, tmp_path):
        root = write_pack(tmp_path / "pack")
        services = runtime.for_session(db, client_row.client_id)
        loader = KnowledgePackLoader(db, client_row.client_id, ingestor=services.ingestor)

        first = loader.load(root)
        assert sorted(first.ingested) == [
            "platform/platform__laws.md",
            "platform/platform__validated_solutions.md",
        ]
        assert first.chunks > 0 and not first.failed

        second = loader.load(root)
        assert second.ingested == [] and second.replaced == []
        assert len(second.unchanged) == 2

        (root / "platform" / "platform__laws.md").write_text(
            LAWS + "\n# An addition\n\nThe platform's Freshness Law was extended.\n",
            encoding="utf-8",
        )
        third = loader.load(root)
        assert third.replaced == ["platform/platform__laws.md"]
        assert third.unchanged == ["platform/platform__validated_solutions.md"]
        # The replaced file is one document, not two.
        assert loader.status()["documents"] == 2

        (root / "platform" / "platform__validated_solutions.md").unlink()
        fourth = loader.load(root, prune=True)
        assert fourth.removed == ["platform/platform__validated_solutions.md"]
        assert loader.status()["documents"] == 1

    def test_documents_land_in_the_domain_namespace_with_provenance(
        self, runtime, db, client_row, tmp_path
    ):
        root = write_pack(tmp_path / "pack")
        services = runtime.for_session(db, client_row.client_id)
        loader = KnowledgePackLoader(db, client_row.client_id, ingestor=services.ingestor)
        loader.load(root)
        held = loader.existing()
        document = held["platform/platform__laws.md"]
        assert document.namespace == "platform"
        assert document.title == "Freshness Law"
        assert document.meta["repo"] == "sabuj14eu/Sniper-System"
        assert document.meta["verified_on"] == "2026-09-16"
        assert document.meta["source"] == "knowledge-pack"
        assert document.status == DocumentStatus.READY.value

    def test_status_compares_the_client_with_the_disk(self, runtime, db, client_row, tmp_path):
        root = write_pack(tmp_path / "pack")
        services = runtime.for_session(db, client_row.client_id)
        loader = KnowledgePackLoader(db, client_row.client_id, ingestor=services.ingestor)
        before = loader.status(root)
        assert before["documents"] == 0
        assert len(before["pack"]["missing_from_client"]) == 2

        loader.load(root)
        (root / "platform" / "platform__laws.md").write_text(LAWS + "\nchanged\n", encoding="utf-8")
        after = loader.status(root)
        assert after["pack"]["missing_from_client"] == []
        assert after["pack"]["stale_in_client"] == ["platform/platform__laws.md"]
        assert after["by_domain"]["platform"]["documents"] == 2

    def test_a_bad_file_refuses_the_whole_load(self, runtime, db, client_row, tmp_path):
        root = write_pack(tmp_path / "pack")
        (root / "platform" / "broken.md").write_text("no header here\n", encoding="utf-8")
        services = runtime.for_session(db, client_row.client_id)
        loader = KnowledgePackLoader(db, client_row.client_id, ingestor=services.ingestor)
        with pytest.raises(PackError):
            loader.load(root)
        assert loader.status()["documents"] == 0

    def test_the_pack_is_isolated_per_client(self, runtime, db, client_row, tmp_path):
        from tests.conftest import make_client

        root = write_pack(tmp_path / "pack")
        services = runtime.for_session(db, client_row.client_id)
        KnowledgePackLoader(db, client_row.client_id, ingestor=services.ingestor).load(root)
        other, _ = make_client(db, "other")
        other_services = runtime.for_session(db, other.client_id)
        assert (
            KnowledgePackLoader(db, other.client_id, ingestor=other_services.ingestor).status()[
                "documents"
            ]
            == 0
        )
        assert other_services.retriever.retrieve("What does the Freshness Law say?").items == []


class TestRetrievalAndAnswering:
    def test_a_loaded_pack_answers_a_question_locally_with_a_cited_source(
        self, runtime, db, client_row, tmp_path, local_provider, paid_provider
    ):
        from app.agents.builtin import BROTHER

        root = write_pack(tmp_path / "pack")
        services = runtime.for_session(db, client_row.client_id)
        KnowledgePackLoader(db, client_row.client_id, ingestor=services.ingestor).load(root)

        # The fake local model only knows what is in front of it — which is
        # exactly the property that makes this a real test of retrieval.
        local_provider.hard_topics.append("Freshness Law")
        response = services.router.handle(
            GatewayRequest(
                message="What does the Freshness Law say about stale data?",
                client=client_row,
                agent=BROTHER,
            )
        )
        assert response.route is Route.LOCAL
        assert response.success
        assert "stale" in response.answer.lower()
        assert any(s["source"] == "document" for s in response.sources)
        assert paid_provider.call_count == 0
        assert response.agent == "brother"
        # The Brother laws travelled with the request, appended to the base rules.
        system = local_provider.calls[-1].messages[0].content
        assert system.startswith("You are AI Helper")
        assert "Never infer from silence" in system

    def test_without_the_pack_the_same_question_is_insufficient_context(
        self, runtime, db, client_row, local_provider
    ):
        services = runtime.for_session(db, client_row.client_id)
        local_provider.hard_topics.append("Freshness Law")
        response = services.router.handle(
            GatewayRequest(message="What does the Freshness Law say about stale data?", client=client_row)
        )
        assert response.route is not Route.PAID or response.escalation_reason is not None
        assert not response.memory_hit


class TestSeeding:
    def test_solutions_are_seeded_through_the_promotion_gate(
        self, runtime, db, client_row, settings, local_provider, tmp_path
    ):
        root = write_pack(tmp_path / "pack")
        services = runtime.for_session(db, client_row.client_id)
        pipeline = PromotionPipeline(
            db,
            client_row.client_id,
            settings=settings,
            local_provider=local_provider,
            retriever=services.retriever,
        )
        counts = seed_solutions(db, client_row.client_id, discover(root), pipeline=pipeline)
        assert counts["seeded"] == 2
        assert counts["promoted"] == 2, counts
        store = SolutionStore(db, client_row.client_id)
        assert store.counts()[SolutionStatus.PROMOTED.value] == 2

        promoted = store.list(status=SolutionStatus.PROMOTED.value)
        row = next(s for s in promoted if "hour late" in s.question)
        assert row.provider == "knowledge-pack"
        assert row.model == "sabuj14eu/Sniper-System"
        assert row.validation_result["seed"]["evidence"].startswith('CLAUDE.md "A CLOCK')
        assert row.reproduction["attempted"] and row.reproduction["passed"]

        # Re-seeding never duplicates, and never resurrects a decision.
        again = seed_solutions(db, client_row.client_id, discover(root), pipeline=pipeline)
        assert again == {"seeded": 0, "skipped": 2, "promoted": 0, "validated": 0, "rejected": 0}

    def test_a_seeded_solution_answers_the_exact_question_without_a_model_call_for_free(
        self, runtime, db, client_row, settings, local_provider, paid_provider, tmp_path
    ):
        root = write_pack(tmp_path / "pack")
        services = runtime.for_session(db, client_row.client_id)
        pipeline = PromotionPipeline(
            db, client_row.client_id, settings=settings, local_provider=local_provider,
            retriever=services.retriever,
        )
        seed_solutions(db, client_row.client_id, discover(root), pipeline=pipeline)
        response = services.router.handle(
            GatewayRequest(
                message="Why were candles stamped an hour late on 2026-08-20?", client=client_row
            )
        )
        assert response.memory_hit and response.retrieval["exact_match"]
        assert response.solution_id is not None
        assert response.route is Route.LOCAL and response.cost_usd == 0.0
        assert paid_provider.call_count == 0

    def test_without_a_local_model_seeds_are_held_at_validated_not_promoted(
        self, runtime, db, client_row, settings, tmp_path
    ):
        root = write_pack(tmp_path / "pack")
        services = runtime.for_session(db, client_row.client_id)
        pipeline = PromotionPipeline(
            db, client_row.client_id, settings=settings, local_provider=None,
            retriever=services.retriever,
        )
        counts = seed_solutions(db, client_row.client_id, discover(root), pipeline=pipeline)
        assert counts["validated"] == 2 and counts["promoted"] == 0
        # Nothing is offered back as knowledge until the gate can be run.
        assert services.retriever.find_exact_solution(
            "Why were candles stamped an hour late on 2026-08-20?"
        ) is None


class TestAgents:
    def test_the_brother_agents_are_registered_and_only_narrow(self):
        from app.agents import build_agent_registry, narrowed_tools
        from app.agents.builtin import BROTHER_AGENTS

        registry = build_agent_registry()
        assert {a.name for a in BROTHER_AGENTS} <= set(registry.names())
        social = registry.get("social")
        assert social is not None
        assert "web_search" not in (social.allowed_tools or ())
        # Narrowing against a client that may only use the calculator leaves nothing extra.
        assert narrowed_tools(social, ["calculator"]) == []

    def test_every_brother_agent_carries_the_shared_laws_and_the_advisory_rule(self):
        from app.agents.builtin import BROTHER_AGENTS, BROTHER_LAWS

        for spec in BROTHER_AGENTS:
            assert BROTHER_LAWS in spec.system_prompt, spec.name
            assert "never claim to have run" in spec.system_prompt

    def test_the_laws_name_no_number_the_pack_should_own(self):
        """Facts live in the pack and are reloaded; the prompt must not fossilise them."""
        import re

        from app.agents.builtin import BROTHER_LAWS

        numbers = set(re.findall(r"\b\d{3,}\b", BROTHER_LAWS))
        assert numbers <= {"100"}, numbers


class TestCli:
    @pytest.fixture
    def pack(self, tmp_path):
        return write_pack(tmp_path / "pack")

    def test_bootstrap_creates_the_client_once_and_loads_the_pack(
        self, runtime, engine, capsys, pack
    ):
        from app import cli

        assert cli.main(["bootstrap-brother", "--path", str(pack)]) == 0
        out = json.loads(capsys.readouterr().out)
        assert out["client_id"] == "brother" and out["created"] is True
        assert out["api_key"].startswith("ahk_")
        assert out["pack"]["ingested"] == 2
        assert out["pack"]["solutions"]["seeded"] == 2

        # A second run neither reissues a key nor re-ingests.
        assert cli.main(["bootstrap-brother", "--path", str(pack)]) == 0
        out = json.loads(capsys.readouterr().out)
        assert out["created"] is False and "api_key" not in out
        assert out["pack"]["unchanged"] == 2 and out["pack"]["ingested"] == 0
        assert out["pack"]["solutions"]["skipped"] == 2

    def test_load_knowledge_needs_the_client(self, runtime, engine, capsys, pack):
        from app import cli

        assert cli.main(["load-knowledge", "--path", str(pack)]) == 2
        assert "bootstrap-brother" in capsys.readouterr().err

    def test_load_and_status_after_bootstrap(self, runtime, engine, capsys, pack):
        from app import cli

        assert cli.main(["bootstrap-brother", "--path", str(pack), "--no-seed"]) == 0
        capsys.readouterr()
        assert cli.main(["load-knowledge", "--path", str(pack), "--no-seed", "--prune"]) == 0
        report = json.loads(capsys.readouterr().out)
        assert report["unchanged"] == 2 and report["solutions"] == {}

        assert cli.main(["knowledge-status", "--path", str(pack)]) == 0
        status = json.loads(capsys.readouterr().out)
        assert status["documents"] == 2
        assert status["pack"]["missing_from_client"] == []
        assert status["solutions"]["PROMOTED"] == 0

    def test_a_missing_pack_directory_is_refused_with_a_reason(self, runtime, engine, capsys, tmp_path):
        from app import cli

        assert cli.main(["bootstrap-brother", "--path", str(tmp_path / "nope")]) == 2
        assert "not found" in capsys.readouterr().err


class TestTheShippedPack:
    """The pack committed in this repository must itself load."""

    ROOT = Path(__file__).resolve().parents[2] / "knowledge"

    def test_every_shipped_file_parses(self):
        files = discover(self.ROOT)
        assert files, "the shipped knowledge pack is empty"
        domains = {f.header.domain for f in files}
        assert "brother" in domains
        for pack_file in files:
            assert pack_file.header.verified_on, pack_file.relative
            assert pack_file.body, pack_file.relative

    def test_no_shipped_file_carries_a_secret_shape(self):
        from app.database.enums import Classification
        from app.privacy.classification import classify

        for pack_file in discover(self.ROOT):
            verdict = classify(pack_file.body, client_default=Classification.INTERNAL.value)
            assert verdict.classification is not Classification.RESTRICTED, pack_file.relative

    def test_shipped_solution_files_yield_parseable_blocks(self):
        for pack_file in discover(self.ROOT):
            if pack_file.is_solutions_file:
                seeds = parse_solutions(
                    pack_file.body, source_file=pack_file.relative, domain=pack_file.header.domain
                )
                assert seeds, f"{pack_file.relative} has no parseable solution blocks"
                for seed in seeds:
                    assert seed.evidence, f"{pack_file.relative}: '{seed.title}' has no evidence"
