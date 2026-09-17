"""What a trading candidate is allowed to claim, and on what evidence.

Two refusals live here, and both were asked for in the same breath as the
feature, which is the right order — a learner is defined by what it declines
to learn.

**A fact and an interpretation are not the same object.** A tier 1 page says
"the Committee lowered the target range to 3-1/2 to 3-3/4 percent". That is a
SOURCE FACT: it has a publisher, a URL and a time, and it is either quoted
correctly or it is not. "Given the reaction and the structure, the long
scenario has a level to lean on" is a TRADING INTERPRETATION: it is reasoning,
it can be wrong while every fact inside it is right, and it has no publisher.
Stored as one sentence, the interpretation inherits the fact's citation and
becomes unfalsifiable — a claim that looks sourced and is not. So the record
carries both, separately, and rendering them always shows the seam.

**One observation is not a rule.** "Gold goes up after FOMC" seen once is n=1.
The trading constitution priced that lesson in real losses: n<20 is luck, ~100
to judge, and the VALIDATE column decides. So a candidate that generalises is
kept as an OBSERVATION with its n, and it cannot be offered as a RULE until
the observations accumulate. Repeated observations strengthen it; a single one
never becomes permanent. Nothing here promotes anything in any case — the
human gate is unchanged and this sits in front of it.

Deterministic throughout (Iron Rule 2). Whether a sentence generalises is
decided by a word list, not by a model.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import StrEnum

from app.trading.plan import TradeStatus

# The floor from the trading constitution: n<20 is luck. It is the number of
# independent observations before a generalisation may even be PROPOSED as a
# rule — not the number that makes it true, which is nearer 100.
EVIDENCE_FLOOR = 20

# Words that turn an observation into a claim about every future instance.
# Deliberately blunt and deliberately conservative: catching a sentence that
# was not really a rule costs an extra review, missing one lets "gold always
# goes up after FOMC" into memory as a fact.
_GENERALISING = re.compile(
    r"\b(always|never|every time|whenever|invariably|guaranteed|"
    r"consistently|reliably|each time|in all cases|will continue to)\b",
    re.I,
)


class ClaimKind(StrEnum):
    SOURCE_FACT = "source_fact"
    """A publisher said this. Checkable against the page it came from."""

    TRADING_INTERPRETATION = "trading_interpretation"
    """Reasoning about what the facts mean. Has no publisher and never gets one."""

    OBSERVATION = "observation"
    """A thing that happened once, or n times. Carries its n."""

    GENERAL_RULE = "general_rule"
    """A claim about every future instance. Needs n, and needs a person."""


def generalises(text: str) -> bool:
    """Does this sentence claim something about every future instance?"""
    return bool(_GENERALISING.search(text or ""))


@dataclass
class TradingCandidate:
    """A structured trading lesson, with its evidence and its limits.

    Every field is one a reviewer asked for, and the empty ones are as
    informative as the filled ones: a candidate with no `invalidation` is a
    candidate nobody can be proven wrong about.
    """

    instrument: str = ""
    market_conditions: str = ""
    event_context: str = ""
    timeframe: str = ""
    setup: str = ""
    direction: str = ""
    entry_logic: str = ""
    sl_logic: str = ""
    tp_logic: str = ""
    invalidation: str = ""
    status: TradeStatus = TradeStatus.UNKNOWN

    # The seam. These two are never concatenated into one string.
    source_fact: str = ""
    source_refs: list[dict] = field(default_factory=list)
    interpretation: str = ""

    observations: int = 1
    outcome: str = ""
    confidence: float = 0.0
    origin: str = ""

    @property
    def claim_kind(self) -> ClaimKind:
        """What this candidate is actually claiming.

        An interpretation that generalises is a GENERAL_RULE however it was
        meant, because that is how it will be read when it comes back out of
        memory months from now with the context gone.
        """
        if generalises(self.interpretation) or generalises(self.source_fact):
            return ClaimKind.GENERAL_RULE
        if self.interpretation:
            return ClaimKind.OBSERVATION
        return ClaimKind.SOURCE_FACT

    @property
    def may_be_proposed_as_a_rule(self) -> bool:
        """Has this been seen enough times to be worth a person's attention
        as a rule? Not "is it true" — that is the human's call and n=20 is
        only the floor at which the question stops being noise."""
        return self.observations >= EVIDENCE_FLOOR

    def evidence_note(self) -> str:
        """The one line a reviewer needs before reading anything else."""
        kind = self.claim_kind
        if kind is ClaimKind.GENERAL_RULE and not self.may_be_proposed_as_a_rule:
            return (
                f"stated as a rule but rests on n={self.observations} "
                f"(the floor is {EVIDENCE_FLOOR}) — kept as an observation, "
                "not offered as a rule"
            )
        if kind is ClaimKind.GENERAL_RULE:
            return f"stated as a rule, n={self.observations} — a person decides"
        if kind is ClaimKind.OBSERVATION:
            return f"an observation, n={self.observations}, not a rule"
        return "a source fact, checkable against its page"

    def render(self) -> str:
        """Fact and interpretation, with the seam visible.

        Always two labelled blocks, never one paragraph, and the labels are
        not decoration: they are what stops the second block from inheriting
        the first block's citation.
        """
        parts = []
        if self.source_fact:
            refs = ", ".join(
                r.get("source_domain", "") for r in self.source_refs if r.get("source_domain")
            )
            parts.append(f"SOURCE FACT{f' ({refs})' if refs else ''}:\n{self.source_fact}")
        if self.interpretation:
            parts.append(
                "TRADING INTERPRETATION (reasoning, not a sourced fact):\n"
                f"{self.interpretation}"
            )
        parts.append(f"EVIDENCE: {self.evidence_note()}")
        return "\n\n".join(parts)

    def as_dict(self) -> dict:
        data = asdict(self)
        data["status"] = self.status.value
        data["claim_kind"] = self.claim_kind.value
        data["may_be_proposed_as_a_rule"] = self.may_be_proposed_as_a_rule
        data["evidence_note"] = self.evidence_note()
        return data


# "Is this about a market?" is NOT the same question as "which agent should
# answer this?", and the first attempt here conflated them. The agent router
# needs two signals before it moves a message away from the generalist, and
# under that bar "what did the FOMC decide today" — the most ordinary trading
# question there is — scored one and came back False.
#
# The two questions have different costs, which is why they get different
# tests. Routing to the wrong specialist costs a worse answer. Failing to
# recognise a market question costs the whole structured record: the source
# fact and the interpretation get stored as one paragraph, which is the thing
# this module exists to prevent.
#
# So: a narrower list, any one of which is enough on its own, and a test
# asserts every pattern here is also a trading signal to the agent router.
# They may differ in breadth; they may not disagree.
_MARKET_SIGNALS = (
    # An instrument is named.
    r"(?i)\b(gold|xau|silver|xag|us100|nas100|us500|spx|btc|usdjpy|eurusd|dxy)\b",
    # A scheduled release or a policy decision.
    r"(?i)\b(fomc|nfp|cpi|rate decision|payrolls?)\b",
    # Execution vocabulary: only asked about a market.
    r"(?i)\b(entry|stop ?loss|take ?profit|pullback|support|resistance)\b",
)
_MARKET = tuple(re.compile(p) for p in _MARKET_SIGNALS)


def is_market_question(question: str) -> bool:
    """Is this a question about a market, rather than about the system?

    One signal is enough, and see the note above for why the bar is lower here
    than the agent router's. Deterministic: a control decision, so no model
    takes part in it (Iron Rule 2).
    """
    text = question or ""
    return any(pattern.search(text) for pattern in _MARKET)


def from_research(
    *,
    question: str,
    answer: str,
    sources: list[dict],
    confidence: float,
    origin: str,
    instrument: str = "",
) -> TradingCandidate:
    """Build the structured record for a researched market question.

    The split is made **structurally, not by asking a model which half is
    which**: everything a publisher wrote is the evidence, and everything the
    local model wrote about it is the interpretation. That is exactly the line
    that matters, it is knowable without judgement, and it cannot be got wrong
    by a small model having a bad minute.

    The status is UNKNOWN. Research reads published text; it does not see the
    chart, the session or the levels, and a status that claimed otherwise
    would be the manufactured setup this whole layer exists to prevent. A
    status is set by the reasoning step that actually has those inputs.
    """
    fact = "\n".join(
        f"- {s.get('claim', '').strip()} [{s.get('source_domain', '')}]"
        for s in sources
        if s.get("claim")
    )
    return TradingCandidate(
        instrument=instrument,
        event_context=question,
        source_fact=fact,
        source_refs=[
            {
                "source_domain": s.get("source_domain", ""),
                "source_url": s.get("source_url", ""),
                "source_tier": s.get("source_tier"),
                "source_trust": s.get("source_trust", ""),
                "retrieved_at": s.get("retrieved_at", ""),
            }
            for s in sources
        ],
        interpretation=answer,
        observations=1,
        confidence=confidence,
        origin=origin,
        status=TradeStatus.UNKNOWN,
    )
