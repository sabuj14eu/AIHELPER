"""Where a solution came from, and what may be learned from.

The dashboard read "229 learned solutions" and every one was hand-written.
These tests fix the three things that follow from taking that seriously: an
honest count, a teach form that cannot swallow a fragment, and a system that
actually learns from being used.
"""

from __future__ import annotations

import pytest

from app.database.enums import SolutionStatus
from app.gateway.router import GatewayRequest
from app.learning.origin import SELF_PROVIDER, SolutionOrigin, origin_of, summarise
from app.learning.solution_store import SolutionStore
from app.validation.states import AnswerState


class TestOriginIsDerivedNotStored:
    @pytest.mark.parametrize(
        "provider,expected",
        [
            ("knowledge-pack", SolutionOrigin.SEEDED),
            ("owner", SolutionOrigin.TAUGHT),
            (SELF_PROVIDER, SolutionOrigin.SELF),
            ("anthropic", SolutionOrigin.PAID),
            ("openai", SolutionOrigin.PAID),
        ],
    )
    def test_each_provider_maps_to_its_origin(self, provider, expected):
        assert origin_of(provider) is expected

    def test_an_unknown_provider_is_treated_as_paid(self):
        """The safe default. PAID is the only origin that implies the answer
        came from outside, so guessing it errs toward less trust, not more."""
        for unknown in (None, "", "   ", "some-future-provider"):
            assert origin_of(unknown) is SolutionOrigin.PAID

    def test_every_origin_is_counted_including_the_empty_ones(self):
        """`self: 0` is the number this whole module exists to make visible.

        A zero that is shown is a fact; a zero that is omitted looks like a
        category nobody thought about.
        """

        class Row:
            def __init__(self, provider):
                self.provider = provider

        counts = summarise([Row("knowledge-pack")] * 229 + [Row("owner")])
        assert counts == {"seeded": 229, "taught": 1, "self": 0, "paid": 0}
        assert set(counts) == {o.value for o in SolutionOrigin}


class TestTeachRefusesWhatIsNotAnAnswer:
    """The gates check usability, not truth.

    The reproduction gate asks whether the local model can restate an answer
    with that answer in front of it, and it can restate two words perfectly.
    So a reply cut short by a timeout would pass both gates and then be served
    from memory for months. That is the one thing the gates cannot catch, so
    it is caught before anything is written.
    """

    def _teach(self, runtime, db, client_row, settings, **kwargs):
        from app.learning.teaching import teach

        services = runtime.for_session(db, client_row.client_id)
        return teach(
            db,
            client_row.client_id,
            actor="admin:test",
            settings=settings,
            local_provider=runtime.providers.local,
            retriever=services.retriever,
            **kwargs,
        )

    def test_a_truncated_answer_is_refused_with_a_reason_naming_the_cause(
        self, runtime, db, client_row, settings
    ):
        with pytest.raises(ValueError, match="cut short by a timeout"):
            self._teach(
                runtime, db, client_row, settings,
                question="Gold now 4265 what is trading plan. today fomc",
                answer="1. The",
            )

    def test_teaching_brother_its_own_shrug_is_refused(
        self, runtime, db, client_row, settings
    ):
        """"I don't know" is not an answer to remember; it is a gap to fill."""
        with pytest.raises(ValueError, match="does not know"):
            self._teach(
                runtime, db, client_row, settings,
                question="what is the gold plan",
                answer="I don't have enough information about the current structure.",
            )

    def test_a_degenerate_loop_is_refused(self, runtime, db, client_row, settings):
        with pytest.raises(ValueError, match="repeats itself"):
            self._teach(
                runtime, db, client_row, settings,
                question="what is the gold plan",
                answer="the same six words repeated again " * 12,
            )

    def test_a_real_correction_is_accepted_and_goes_through_the_gate(
        self, runtime, db, client_row, settings
    ):
        result = self._teach(
            runtime, db, client_row, settings,
            question="What is the v7 bot?",
            answer=(
                "The v7 bot is the mechanical arm of the system: it applies its own "
                "filters and sends to the bridge. All of its accounts are DEMO."
            ),
        )
        assert result.solution_id
        store = SolutionStore(db, client_row.client_id)
        row = next(r for r in store.list(limit=50) if r.id == result.solution_id)
        assert origin_of(row.provider) is SolutionOrigin.TAUGHT


@pytest.fixture
def seeded_context(runtime, db, client_row):
    """A document in the store, so a question about it retrieves evidence."""
    services = runtime.for_session(db, client_row.client_id)
    services.ingestor.ingest(
        b"The v7 bot is the mechanical arm of the Brother Sniper system. It "
        b"applies its own filters and sends orders to the bridge on port 5001. "
        b"Every account it trades is a DEMO account.",
        "v7.txt",
        namespace="default",
    )
    db.flush()
    return {"question": "What is the v7 bot and which port does its bridge use?"}


class TestBrotherKeepsItsOwnVerifiedAnswers:
    """With paid providers off, this is the only way anything is ever learned."""

    def _ask(self, runtime, db, client_row, message):
        services = runtime.for_session(db, client_row.client_id)
        return services.router.handle(GatewayRequest(message=message, client=client_row))

    def test_a_verified_grounded_answer_is_kept_as_a_candidate_to_confirm(
        self, runtime, db, client_row, settings, local_provider, seeded_context
    ):
        response = self._ask(runtime, db, client_row, seeded_context["question"])
        if response.state is not AnswerState.VERIFIED or response.memory_hit:
            pytest.skip("the fake local model did not produce a verified fresh answer")
        store = SolutionStore(db, client_row.client_id)
        kept = [r for r in store.list(limit=50) if origin_of(r.provider) is SolutionOrigin.SELF]
        assert kept, "a verified grounded answer must be kept"
        assert all(r.status == SolutionStatus.CANDIDATE.value for r in kept), (
            "a local answer passes its own reproduction gate by construction, so "
            "promoting it here would be a rubber stamp"
        )
        assert any("confirm" in note for note in response.notes)

    def test_an_ungrounded_answer_is_not_kept(
        self, runtime, db, client_row, settings, local_provider
    ):
        """Being right about the capital of France is not worth remembering,
        and memorising ungrounded general knowledge is how a store fills with
        things nobody can check."""
        self._ask(runtime, db, client_row, "What is the capital of France?")
        store = SolutionStore(db, client_row.client_id)
        kept = [r for r in store.list(limit=50) if origin_of(r.provider) is SolutionOrigin.SELF]
        assert kept == [], "nothing was consulted, so there is nothing to be right about"

    def test_it_can_be_switched_off(
        self, runtime, db, client_row, settings, local_provider, seeded_context
    ):
        settings.SELF_LEARNING_ENABLED = False
        self._ask(runtime, db, client_row, seeded_context["question"])
        store = SolutionStore(db, client_row.client_id)
        assert [r for r in store.list(limit=50) if origin_of(r.provider) is SolutionOrigin.SELF] == []



class TestStepsFourAndFive:
    """Steps 4 and 5 of the pipeline: duplicates, and disagreement with what is known.

    Capture used to ask one question — is this exact sentence already stored?
    Two failures got past that, and they fail in opposite directions: the same
    thing worded differently, and the opposite thing stored beside it.
    """

    class FakeRetriever:
        """Stands in for the vector index; the thresholds are the real ones' job."""

        def __init__(self, rows=(), raises=False):
            self.rows = list(rows)
            self.raises = raises

        def similar_promoted(self, text, *, limit=5, min_score=None):
            if self.raises:
                raise RuntimeError("qdrant is having a moment")
            return self.rows[:limit]

    def _row(self, db, client_row, question, answer):
        from app.learning.origin import SELF_PROVIDER

        return SolutionStore(db, client_row.client_id).create(
            question=question,
            answer=answer,
            task_type="general",
            provider=SELF_PROVIDER,
            model="m",
            failure_reason=None,
            local_attempt=None,
            validation_result={},
            confidence=0.9,
            classification="INTERNAL",
        )

    def test_a_reworded_duplicate_is_recognised(self, db, client_row):
        from app.learning.conflicts import check_against_known

        stored = self._row(
            db, client_row, "What port does the v7 bridge use?", "The bridge is on port 5001."
        )
        check = check_against_known(
            self.FakeRetriever([(stored, 0.74)]),
            question="which port is the v7 bridge on",
            answer="The bridge listens on port 5001.",
        )
        assert check.is_duplicate and check.duplicate.id == stored.id
        assert check.duplicate_score == 0.74

    def test_an_answer_that_disagrees_with_stored_knowledge_is_flagged(self, db, client_row):
        """The case validation cannot see.

        Validation checks an answer against the context retrieved *for that
        question*. A stale solution filed under a different question need not
        rank for it at all — so the two can sit in memory together, and
        whichever one retrieval surfaces is what Brother says.
        """
        from app.learning.conflicts import check_against_known

        stale = self._row(
            db, client_row,
            "Is a stale bias usable?",
            "A stale bias is neutral and used.",
        )
        check = check_against_known(
            self.FakeRetriever([(stale, 0.8)]),
            question="how does the system treat a stale bias",
            answer="A stale bias is invalid and unused, not neutral.",
        )
        assert check.has_conflict, "the two cannot both be true"
        assert check.conflicts[0].solution_id == stale.id
        assert check.conflicts[0].detail

    def test_agreeing_with_stored_knowledge_is_not_a_conflict(self, db, client_row):
        from app.learning.conflicts import check_against_known

        stored = self._row(
            db, client_row, "What is the v7 bot?", "The v7 bot is the mechanical arm."
        )
        check = check_against_known(
            self.FakeRetriever([(stored, 0.75)]),
            question="describe the v7 bot",
            answer="The v7 bot is the mechanical arm of the system.",
        )
        assert not check.has_conflict

    def test_a_broken_index_loses_the_check_not_the_lesson(self, db, client_row):
        """A quality gate, not a safety gate.

        Losing a check costs a duplicate row. Refusing to capture because the
        vector store blinked costs the thing the system was trying to learn.
        """
        from app.learning.conflicts import check_against_known

        check = check_against_known(
            self.FakeRetriever(raises=True), question="anything", answer="anything at all"
        )
        assert not check.is_duplicate and not check.has_conflict

    def test_no_retriever_is_handled(self, db, client_row):
        from app.learning.conflicts import check_against_known

        assert not check_against_known(None, question="q", answer="a").is_duplicate

    def test_the_duplicate_bar_sits_below_the_reuse_bar(self, settings):
        """Above the reuse bar a stored answer is served instead of asking the
        model, so nothing is ever captured up there. If these ever crossed, the
        duplicate check would cover a band that cannot occur."""
        assert settings.SOLUTION_DUPLICATE_THRESHOLD < settings.SOLUTION_REUSE_THRESHOLD
        assert (
            settings.LEXICAL_SOLUTION_DUPLICATE_THRESHOLD
            < settings.LEXICAL_SOLUTION_REUSE_THRESHOLD
        )
