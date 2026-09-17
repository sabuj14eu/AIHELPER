"""Structured trading reasoning, and the two things it refuses to learn.

Brother is meant to become a disciplined trading research assistant, and the
discipline is mostly refusals. Three of them are tested here, each written as
the failure it prevents:

* it must never manufacture a setup because an entry was asked for,
* it must never name a price it was not given, and
* it must never turn one occurrence into a rule.
"""

from __future__ import annotations

import pytest

from app.trading.knowledge import (
    EVIDENCE_FLOOR,
    ClaimKind,
    TradingCandidate,
    from_research,
    generalises,
    is_market_question,
)
from app.trading.plan import (
    REASONING_STEPS,
    STEP_KEYS,
    TradePlan,
    TradeStatus,
    confidence_from_inputs,
    prices_in,
    status_for,
    unsourced_prices,
)


class TestNoTradeIsAnAnswer:
    def test_none_of_the_four_statuses_is_a_failure(self):
        """WAIT and UNKNOWN are conclusions, not faults. The four answer
        states learned this the expensive way: "I cannot establish this" was
        rendered as a technical failure, and the assistant was punished for
        obeying its own rules."""
        assert [s for s in TradeStatus if s.is_failure] == []

    def test_only_ready_is_something_to_place(self):
        assert [s for s in TradeStatus if s.is_actionable] == [TradeStatus.READY]

    def test_missing_core_inputs_give_unknown_not_a_guess(self):
        """No structure and no levels is not a thin setup — it is no setup,
        and a plan built on an input that is not there is worse than none."""
        assert status_for(["market_data"]) is TradeStatus.UNKNOWN
        assert status_for(["market_data", "structure"]) is TradeStatus.UNKNOWN

    def test_inputs_present_but_no_location_is_wait(self):
        """The ordinary state of a market: readable, and nothing to do."""
        assert status_for(["market_data", "structure", "levels"]) is TradeStatus.WAIT

    def test_conflicting_inputs_give_unknown_however_complete_they_are(self):
        """"Important data conflicting" is UNKNOWN, not a weighted average of
        two readings — averaging a disagreement invents a third answer that
        neither piece of evidence supports."""
        assert status_for(list(STEP_KEYS), conflicting=1, location_found=True) is (
            TradeStatus.UNKNOWN
        )

    def test_ready_needs_the_inputs_and_a_location(self):
        assert status_for(
            ["market_data", "structure", "levels"], location_found=True
        ) is TradeStatus.READY


class TestPricesAreQuotedNeverGenerated:
    def test_a_price_not_in_the_evidence_is_named(self):
        """The enforcement of "never invent prices". Objective, so it is
        allowed to veto: a figure that is not in the source is not in it."""
        missing = unsourced_prices(
            "BUY STOP entry 4271.5, SL 4265.0, TP 4300.0",
            ["Spot gold traded at 4,271.50 and found support at 4,265.00"],
        )
        assert missing == ["4300"]

    def test_the_same_price_written_differently_counts_as_sourced(self):
        """4,271.50 in a news story and 4271.5 in a plan are one price. A
        checker that missed that would flag every correctly-quoted plan, and a
        check that cries wolf gets switched off."""
        assert unsourced_prices("entry 4271.5", ["gold at 4,271.50 an ounce"]) == []

    def test_counts_and_durations_are_not_prices(self):
        """"3 hours", "2 scenarios", "tier 1" must not be read as prices."""
        assert prices_in("2 scenarios over 3 hours at tier 1") == []

    def test_a_plan_with_an_invented_price_is_not_shown_as_a_setup(self):
        plan = TradePlan(
            instrument="GOLD", status=TradeStatus.READY, unsourced=["4300"]
        )
        assert not plan.is_safe_to_show_as_a_setup, (
            "an invented price is not a degraded plan, it is a different object"
        )

    def test_a_fully_sourced_ready_plan_is_shown(self):
        plan = TradePlan(instrument="GOLD", status=TradeStatus.READY)
        assert plan.is_safe_to_show_as_a_setup


class TestConfidenceReadsTheEvidence:
    def test_it_is_the_share_of_inputs_that_were_actually_there(self):
        assert confidence_from_inputs(list(STEP_KEYS)) == 1.0
        assert confidence_from_inputs([]) == 0.0

    def test_conflicting_evidence_lowers_it(self):
        """Confidence is evidence quality, never how sure the model sounded."""
        full = confidence_from_inputs(list(STEP_KEYS))
        assert confidence_from_inputs(list(STEP_KEYS), conflicting=2) < full

    def test_an_unknown_input_name_cannot_inflate_it(self):
        assert confidence_from_inputs(["made_up_input", "another"]) == 0.0

    def test_a_plan_records_which_inputs_were_absent(self):
        """Every displayed number needs its source and its completeness. A
        plan that does not say what it was missing cannot be read at all."""
        plan = TradePlan(
            instrument="GOLD",
            inputs_present=["market_data", "news"],
            inputs_absent=["structure", "levels"],
        )
        data = plan.as_dict()
        assert data["inputs_absent"] == ["structure", "levels"]


class TestTheReasoningOrderIsSharedNotDuplicated:
    def test_the_prompt_is_rendered_from_the_same_list_the_code_uses(self):
        """Otherwise the order Brother is told to think in and the order the
        record reports drift apart, and nobody notices until they disagree."""
        from app.agents.builtin import TRADING_RESEARCH_PROCEDURE

        for _key, description in REASONING_STEPS:
            assert description in TRADING_RESEARCH_PROCEDURE

    def test_the_twelve_steps_are_the_twelve_asked_for(self):
        assert len(REASONING_STEPS) == 12
        assert STEP_KEYS[0] == "market_data" and STEP_KEYS[-1] == "decision"

    def test_the_procedure_tells_the_model_it_may_decline(self):
        from app.agents.builtin import TRADING_RESEARCH_PROCEDURE

        text = TRADING_RESEARCH_PROCEDURE
        assert "WAIT" in text and "NO TRADE" in text and "UNKNOWN" in text
        assert "never manufacture a setup" in text.lower()

    def test_the_procedure_forbids_an_unsourced_price(self):
        from app.agents.builtin import TRADING_RESEARCH_PROCEDURE

        assert "must appear in the CONTEXT" in TRADING_RESEARCH_PROCEDURE


class TestAFactIsNotAnInterpretation:
    def test_the_two_are_stored_apart_and_rendered_with_the_seam_showing(self):
        """Merged into one sentence, the interpretation inherits the fact's
        citation and becomes a claim that looks sourced and is not."""
        candidate = TradingCandidate(
            instrument="GOLD",
            source_fact="The Committee lowered the target range to 3-1/2 to 3-3/4 percent.",
            source_refs=[{"source_domain": "federalreserve.gov"}],
            interpretation="A softer policy path may support the metal here.",
        )
        rendered = candidate.render()
        assert "SOURCE FACT (federalreserve.gov):" in rendered
        assert "TRADING INTERPRETATION (reasoning, not a sourced fact):" in rendered
        assert rendered.index("SOURCE FACT") < rendered.index("TRADING INTERPRETATION")

    def test_the_split_is_structural_not_a_judgement_call(self):
        """Published text is the evidence; the model's own words are the
        interpretation. That line is knowable without asking anyone — and so
        it cannot be got wrong by a small model having a bad minute."""
        candidate = from_research(
            question="what did the FOMC decide",
            answer="This reads as a softer path from here.",
            sources=[
                {
                    "claim": "The Committee lowered the target range.",
                    "source_domain": "federalreserve.gov",
                    "source_url": "https://www.federalreserve.gov/x",
                    "source_tier": 1,
                    "source_trust": "VERIFIED",
                }
            ],
            confidence=0.8,
            origin="local-web-research",
        )
        assert "The Committee lowered" in candidate.source_fact
        assert "The Committee lowered" not in candidate.interpretation
        assert candidate.interpretation == "This reads as a softer path from here."

    def test_research_never_claims_a_trade_status(self):
        """It read published text. It did not see the chart, the session or
        the levels — a status here would be the manufactured setup this whole
        layer exists to prevent."""
        candidate = from_research(
            question="gold after the FOMC", answer="Softer path.", sources=[],
            confidence=0.9, origin="local-web-research",
        )
        assert candidate.status is TradeStatus.UNKNOWN

    def test_every_source_keeps_its_tier_on_the_record(self):
        candidate = from_research(
            question="q", answer="a",
            sources=[{"claim": "c", "source_domain": "bls.gov", "source_tier": 1,
                      "source_trust": "VERIFIED", "source_url": "https://bls.gov/x"}],
            confidence=0.5, origin="local-web-research",
        )
        assert candidate.source_refs[0]["source_tier"] == 1
        assert candidate.source_refs[0]["source_trust"] == "VERIFIED"


class TestOneObservationIsNotARule:
    @pytest.mark.parametrize(
        "text",
        [
            "Gold always goes up after FOMC.",
            "Gold never falls in the Asia session.",
            "Whenever the Fed cuts, the metal rallies.",
            "This will continue to hold.",
        ],
    )
    def test_a_generalising_sentence_is_recognised(self, text):
        assert generalises(text)

    def test_a_single_observation_stated_as_a_rule_is_not_offered_as_one(self):
        """The example given when this was asked for, and the reason the
        trading constitution exists: n<20 is luck."""
        candidate = TradingCandidate(
            instrument="GOLD",
            source_fact="Gold closed higher on the day of the September FOMC.",
            interpretation="Gold always goes up after FOMC.",
            observations=1,
        )
        assert candidate.claim_kind is ClaimKind.GENERAL_RULE
        assert not candidate.may_be_proposed_as_a_rule
        note = candidate.evidence_note()
        assert "n=1" in note and str(EVIDENCE_FLOOR) in note
        assert "not offered as a rule" in note

    def test_the_observation_itself_is_kept_not_discarded(self):
        """Dropping it loses what was seen. The refusal is about the claim's
        scope, never about the evidence."""
        candidate = TradingCandidate(
            source_fact="Gold closed higher after the September FOMC.",
            interpretation="Gold always goes up after FOMC.",
            observations=1,
        )
        assert "Gold closed higher" in candidate.render()

    def test_repeated_observations_may_be_proposed_and_still_need_a_person(self):
        candidate = TradingCandidate(
            interpretation="Gold always rallies after a cut.", observations=EVIDENCE_FLOOR
        )
        assert candidate.may_be_proposed_as_a_rule
        assert "a person decides" in candidate.evidence_note()

    def test_a_plain_reading_is_an_observation_not_a_rule(self):
        candidate = TradingCandidate(
            source_fact="The Committee lowered the range.",
            interpretation="That is a softer path than the June meeting implied.",
        )
        assert candidate.claim_kind is ClaimKind.OBSERVATION
        assert "not a rule" in candidate.evidence_note()

    def test_a_bare_fact_with_no_reading_is_a_source_fact(self):
        assert TradingCandidate(source_fact="CPI came in at 2.4%.").claim_kind is (
            ClaimKind.SOURCE_FACT
        )


class TestRecognisingAMarketQuestion:
    @pytest.mark.parametrize(
        "question",
        [
            "what did the FOMC decide today",
            "where is gold trading",
            "CPI print this morning",
            "where should my stop loss go",
            "is DXY strong right now",
        ],
    )
    def test_market_questions_are_recognised(self, question):
        assert is_market_question(question)

    @pytest.mark.parametrize(
        "question",
        [
            "what is the capital of France",
            "why did the deploy fail",
            "how do I add an alembic migration",
            "who designed the Eiffel tower",
        ],
    )
    def test_other_questions_are_left_alone(self, question):
        assert not is_market_question(question)

    def test_its_signals_never_contradict_the_agent_router(self):
        """A lower bar than the router's is fine — the two answer different
        questions and a missed market question costs more than a missed route.
        Disagreeing about the same WORD is not fine, so every signal here must
        also be a trading signal there."""
        from app.agents.router import score_domains
        from app.trading.knowledge import _MARKET

        for pattern in _MARKET:
            # A sentence that matches this pattern must look like trading to
            # the router too, even if one signal is not enough to route on.
            sample = {"gold": "gold", "fomc": "fomc", "entry": "entry"}
            for word in sample.values():
                if pattern.search(word):
                    score, _ = score_domains(word)["trading"]
                    assert score >= 1, f"the router does not see '{word}' as trading"
