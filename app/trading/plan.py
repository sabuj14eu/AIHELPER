"""A trading plan: its status, its inputs, and the prices it is allowed to name.

Four statuses, and only one of them is a setup. The other three are answers,
not failures — the same law the four answer states established, applied to a
market question:

    READY     conditions support a plan, and every price in it is sourced
    WAIT      the structure is readable but the location is not there yet
    NO_TRADE  the evidence argues against taking anything here
    UNKNOWN   the inputs needed to decide are missing or disagree

**A setup is never manufactured because someone asked for an entry.** That is
the whole reason WAIT, NO_TRADE and UNKNOWN are first-class here: an
assistant that must always produce a number will always produce a number, and
the number will be invented on the days the evidence is thinnest — which are
exactly the days it costs money.

**Prices are quoted, never generated.** `unsourced_prices` is the enforcement:
every price-shaped figure in a plan must appear in the evidence the plan was
built from. It is deterministic text analysis, not a judgement, and it is an
OBJECTIVE finding — a figure that is not in the source is not in the source —
so unlike a heuristic it is allowed to veto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

# The order Brother thinks in. It lives here as data so that the prompt, the
# plan record and the tests cannot drift apart: the prompt is rendered from
# this list, and a plan reports which of these inputs it had.
REASONING_STEPS: tuple[tuple[str, str], ...] = (
    ("market_data", "current price and what it is doing"),
    ("news", "scheduled events and what has just been released"),
    ("correlations", "DXY, yields and correlated markets where they matter"),
    ("structure", "multi-timeframe structure"),
    ("session", "which session it is, and what that asset does in it"),
    ("levels", "support, resistance and the levels that have been respected"),
    ("location", "where price is relative to those levels — the setup, or its absence"),
    ("buy_scenario", "what would have to be true for the long"),
    ("sell_scenario", "what would have to be true for the short"),
    ("risk_reward", "the reward against the risk, from the levels above"),
    ("invalidation", "what would prove the read wrong"),
    ("decision", "the status, and why"),
)
STEP_KEYS = tuple(key for key, _ in REASONING_STEPS)


class TradeStatus(StrEnum):
    READY = "READY"
    WAIT = "WAIT"
    NO_TRADE = "NO_TRADE"
    UNKNOWN = "UNKNOWN"

    @property
    def is_actionable(self) -> bool:
        """Only READY describes something to place. The rest are conclusions."""
        return self is TradeStatus.READY

    @property
    def is_failure(self) -> bool:
        """None of them is.

        Written as a property rather than left implicit because the first
        version of the four answer states got exactly this wrong: "I cannot
        establish this" was rendered as a fault, and the assistant was
        punished for obeying its own rules.
        """
        return False


# A price in these markets. Bare integers are excluded deliberately: "3 hours",
# "2 scenarios" and "tier 1" are not prices, and a check that flags them cries
# wolf until someone turns it off. A price here is a decimal, a thousands-
# separated figure, or a 4+ digit run — which is what gold, silver, indices and
# FX quotes actually look like when written down.
_PRICE = re.compile(r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b|\b\d+\.\d+\b|\b\d{4,}\b")


def prices_in(text: str) -> list[str]:
    """Price-shaped figures, normalised so 4,271.00 and 4271 are one price."""
    out: list[str] = []
    for raw in _PRICE.findall(text or ""):
        try:
            value = float(raw.replace(",", ""))
        except ValueError:  # pragma: no cover - the regex cannot produce this
            continue
        text_value = f"{value:g}"
        if text_value not in out:
            out.append(text_value)
    return out


def unsourced_prices(plan_text: str, evidence_texts: list[str]) -> list[str]:
    """Prices the plan names that no piece of evidence contains.

    The objective half of "never invent prices". It cannot tell a well-reasoned
    entry from a badly-reasoned one — it only says whether the number was read
    somewhere or produced from nothing, which is the difference that matters
    when a plan is about to be acted on.
    """
    available = set()
    for text in evidence_texts or []:
        available.update(prices_in(text))
    return [price for price in prices_in(plan_text) if price not in available]


@dataclass
class TradePlan:
    """A plan, or the honest absence of one.

    `inputs_present` and `inputs_absent` are not decoration. A plan that does
    not say which of the twelve inputs it had is a plan whose confidence cannot
    be read — and the Freshness Law is explicit that every displayed number
    needs its source, its age and its authority.
    """

    instrument: str
    status: TradeStatus = TradeStatus.UNKNOWN
    reason: str = ""
    buy: dict | None = None
    sell: dict | None = None
    inputs_present: list[str] = field(default_factory=list)
    inputs_absent: list[str] = field(default_factory=list)
    invalidation: str = ""
    confidence: float = 0.0
    unsourced: list[str] = field(default_factory=list)

    @property
    def is_safe_to_show_as_a_setup(self) -> bool:
        """READY with every price sourced. Anything else is shown as a read.

        An invented price in a plan is not a degraded plan, it is a different
        kind of object — the same distinction the clock incident drew between
        degraded data and corrupted data.
        """
        return self.status.is_actionable and not self.unsourced

    def as_dict(self) -> dict:
        return {
            "instrument": self.instrument,
            "status": self.status.value,
            "reason": self.reason,
            "buy": self.buy,
            "sell": self.sell,
            "inputs_present": self.inputs_present,
            "inputs_absent": self.inputs_absent,
            "invalidation": self.invalidation,
            "confidence": round(self.confidence, 3),
            "unsourced_prices": self.unsourced,
            "actionable": self.is_safe_to_show_as_a_setup,
        }


def confidence_from_inputs(present: list[str], *, conflicting: int = 0) -> float:
    """Confidence as a reading of the evidence, never as a feeling.

    It is the share of the twelve inputs that were actually available, less a
    penalty for each pair of inputs that disagree. It cannot exceed what the
    evidence supports, which is the entire point: a number that rises because
    the model sounded sure is a number that lies on exactly the days it
    matters.
    """
    if not STEP_KEYS:  # pragma: no cover - the list is a constant
        return 0.0
    have = len({key for key in present if key in STEP_KEYS})
    score = have / len(STEP_KEYS)
    return max(0.0, round(score - 0.15 * max(0, conflicting), 4))


def status_for(
    present: list[str], *, conflicting: int = 0, location_found: bool = False
) -> TradeStatus:
    """Which of the four, from the inputs alone. Deterministic (Iron Rule 2).

    The ladder is ordered by what a wrong call costs. Missing or conflicting
    core inputs is UNKNOWN, because a plan built on an input that is not there
    is worse than no plan. With the inputs but no location it is WAIT — the
    setup has not arrived, which is the ordinary state of a market. READY needs
    a location AND the inputs; it is the narrowest of the four and the only one
    that names prices.
    """
    have = {key for key in present if key in STEP_KEYS}
    core = {"market_data", "structure", "levels"}
    if conflicting > 0 or not core.issubset(have):
        return TradeStatus.UNKNOWN
    if not location_found:
        return TradeStatus.WAIT
    return TradeStatus.READY
