"""Capture, the promotion gates, and the lifecycle of a learned solution."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.database.enums import Classification, SolutionStatus
from app.learning.fallback_capture import capture
from app.learning.promotion import PromotionPipeline
from app.learning.similarity import fingerprint, jaccard, normalise
from app.learning.solution_store import SolutionStore


def make_candidate(db, client_id="acme", **overrides):
    payload = dict(
        question="What is the health contribution look-back rule?",
        answer=(
            "Under the flat tax the health contribution for a month is 4.9% of the income of "
            "the month before it."
        ),
        task_type="general",
        provider="anthropic",
        model="fake-paid-large",
        failure_reason="VALIDATION_FAILURE",
        local_attempt="INSUFFICIENT_CONTEXT",
        validation={"passed": True},
        confidence=0.9,
        classification=Classification.INTERNAL,
    )
    payload.update(overrides)
    return capture(db, client_id, **payload)


class TestNormalisation:
    def test_cosmetic_differences_collapse(self):
        assert fingerprint("What is the VAT rate?") == fingerprint("what is the vat rate")
        assert fingerprint("Please, what is the VAT rate?") == fingerprint("What is the VAT rate")

    def test_negation_is_never_normalised_away(self):
        assert fingerprint("Is X allowed?") != fingerprint("Is X not allowed?")
        assert fingerprint("Can I deduct this?") != fingerprint("Can I never deduct this?")

    def test_the_fingerprint_is_scoped_by_client(self):
        assert fingerprint("same question", salt="alpha") != fingerprint("same question", salt="beta")

    def test_jaccard_measures_token_overlap(self):
        assert jaccard("the vat rate in poland", "the VAT rate for Poland") > 0.5
        assert jaccard("the vat rate", "sourdough bread recipe") == 0.0

    def test_normalise_is_stable(self):
        assert normalise("  What   is  THIS?  ") == "what is this"

    def test_a_greeting_set_off_by_punctuation_is_dropped(self):
        assert normalise("Hello, what is the VAT rate?") == "what is the vat rate"
        assert normalise("Please what is the VAT rate") == "what is the vat rate"

    def test_a_filler_word_that_is_part_of_the_question_is_kept(self):
        """Dropping a content word would fuse two different questions."""
        assert normalise("Hello world program in Python") == "hello world program in python"
        assert fingerprint("Hello world program") != fingerprint("world program")
        assert normalise("So many options — which is best") == "so many options which is best"


class TestCapture:
    def test_a_capture_creates_a_candidate_not_knowledge(self, db):
        decision = make_candidate(db)
        assert decision.captured is True
        assert decision.solution.status == SolutionStatus.CANDIDATE.value

    def test_an_empty_answer_is_not_captured(self, db):
        assert make_candidate(db, answer="   ").captured is False

    def test_restricted_content_is_never_captured(self, db):
        decision = make_candidate(db, classification=Classification.RESTRICTED)
        assert decision.captured is False and "RESTRICTED" in decision.reason

    def test_an_injection_flagged_request_is_not_captured(self, db):
        decision = make_candidate(db, injection_suspected=True)
        assert decision.captured is False and "injection" in decision.reason

    def test_the_local_attempt_and_failure_reason_are_recorded(self, db):
        solution = make_candidate(db).solution
        assert solution.local_attempt == "INSUFFICIENT_CONTEXT"
        assert solution.failure_reason == "VALIDATION_FAILURE"

    def test_the_capture_is_audited(self, db):
        from sqlalchemy import select

        from app.database.models import AuditEvent

        make_candidate(db)
        db.flush()
        actions = {e.action for e in db.scalars(select(AuditEvent))}
        assert "learning.solution_captured" in actions


class TestPromotionGates:
    def _pipeline(self, runtime, db, client_id="acme", settings=None):
        return PromotionPipeline(
            db,
            client_id,
            settings=settings or runtime.settings,
            local_provider=runtime.providers.local,
            retriever=runtime.retriever(db, client_id),
        )

    def test_a_good_answer_passes_both_gates(self, runtime, db):
        solution = make_candidate(db).solution
        outcome = self._pipeline(runtime, db).process(solution)
        assert outcome.status is SolutionStatus.PROMOTED
        assert outcome.reproduction["passed"] is True

    def test_an_answer_that_fails_validation_is_rejected_at_gate_one(self, runtime, db):
        solution = make_candidate(db, answer="I cannot help with that.").solution
        outcome = self._pipeline(runtime, db).process(solution)
        assert outcome.status is SolutionStatus.REJECTED
        assert "validation failed" in outcome.reason

    def test_an_answer_the_local_model_cannot_use_is_rejected_at_gate_two(
        self, runtime, db, local_provider
    ):
        """The point of the reproduction gate: promoting this would buy nothing."""
        solution = make_candidate(db).solution
        local_provider.answer_override = "INSUFFICIENT_CONTEXT — still no idea."
        outcome = self._pipeline(runtime, db).process(solution)
        assert outcome.status is SolutionStatus.REJECTED
        assert "even with this solution as context" in outcome.reason

    def test_when_reproduction_cannot_run_the_solution_is_held_not_promoted(
        self, runtime, db, local_provider
    ):
        solution = make_candidate(db).solution
        local_provider.installed = False
        outcome = self._pipeline(runtime, db).process(solution)
        assert outcome.status is SolutionStatus.VALIDATED
        assert "held at VALIDATED" in outcome.reason

    def test_the_reproduction_gate_can_be_turned_off_and_says_so_on_the_row(
        self, runtime, db, settings
    ):
        settings.PROMOTION_REQUIRES_REPRODUCTION = False
        solution = make_candidate(db).solution
        outcome = self._pipeline(runtime, db, settings=settings).process(solution)
        assert outcome.status is SolutionStatus.PROMOTED
        assert "disabled by configuration" in solution.reproduction["reason"]

    def test_a_promotion_that_cannot_be_indexed_is_rolled_back(
        self, runtime, db, monkeypatch
    ):
        """An unindexed PROMOTED row would never be found again."""
        solution = make_candidate(db).solution
        pipeline = self._pipeline(runtime, db)

        def explode(_solution):
            raise RuntimeError("vector store is down")

        monkeypatch.setattr(pipeline.retriever, "index_solution", explode)
        outcome = pipeline.process(solution)
        assert outcome.status is SolutionStatus.VALIDATED
        assert solution.status == SolutionStatus.VALIDATED.value

    def test_a_manual_rejection_unindexes_the_solution(self, runtime, db):
        solution = make_candidate(db).solution
        pipeline = self._pipeline(runtime, db)
        pipeline.process(solution)
        assert solution.status == SolutionStatus.PROMOTED.value

        pipeline.reject(solution, "a reviewer disagreed")
        db.flush()
        retriever = runtime.retriever(db, "acme")
        assert retriever.find_exact_solution(solution.question) is None
        assert retriever.retrieve(solution.question).solution is None


class TestLifecycle:
    def test_an_expired_solution_is_not_retrieved(self, runtime, db):
        solution = make_candidate(db).solution
        pipeline = PromotionPipeline(
            db,
            "acme",
            settings=runtime.settings,
            local_provider=runtime.providers.local,
            retriever=runtime.retriever(db, "acme"),
        )
        pipeline.process(solution)
        solution.expires_at = datetime.now(UTC) - timedelta(days=1)
        db.flush()
        assert runtime.retriever(db, "acme").find_exact_solution(solution.question) is None

    def test_expire_due_marks_rows_expired(self, db):
        solution = make_candidate(db).solution
        solution.expires_at = datetime.now(UTC) - timedelta(days=1)
        db.flush()
        store = SolutionStore(db, "acme")
        assert len(store.expire_due()) == 1
        assert store.get(solution.id).status == SolutionStatus.EXPIRED.value

    def test_counts_cover_every_status(self, db):
        counts = SolutionStore(db, "acme").counts()
        assert set(counts) == {s.value for s in SolutionStatus}

    def test_a_solution_is_never_visible_to_another_client(self, db):
        solution = make_candidate(db, client_id="alpha").solution
        db.flush()
        assert SolutionStore(db, "beta").get(solution.id) is None
        assert SolutionStore(db, "beta").list() == []

    @pytest.mark.parametrize("status", list(SolutionStatus))
    def test_only_promoted_solutions_are_retrievable(self, runtime, db, status):
        solution = make_candidate(db).solution
        retriever = runtime.retriever(db, "acme")
        retriever.index_solution(solution)
        SolutionStore(db, "acme").set_status(solution, status)
        # The vector payload carries the status too, so reindex to be realistic.
        retriever.index_solution(solution)
        db.flush()
        found = retriever.find_exact_solution(solution.question)
        assert (found is not None) == (status is SolutionStatus.PROMOTED)
