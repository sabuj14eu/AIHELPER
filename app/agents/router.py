"""Choosing the specialist — deterministically.

Four Brother agents exist, each with its own prompt and its own tool set, and
until now nothing sent a message to any of them: the agent was whichever value
the chat's dropdown held, defaulting to ``brother``. So a trading question
reached the trading expert only if the reader remembered to pick it, which is
the same as saying the specialisation was decorative.

This is the missing step. It is regex over the message, not a model call, and
that is deliberate rather than a compromise:

* **Iron Rule 2 stands.** A model call here would be a model call on every
  request, including the ones a tool answers for free, and it would put an LLM
  inside a routing decision. The rule exists for good reasons and this module
  does not need to bend it.
* **Being wrong is cheap here, and it must stay cheap.** A miss costs one
  local call against a slightly wrong prompt. It cannot spend money, cannot
  send anything outside, and cannot write. That is only true because the
  fallback is ``brother`` — an agent that inherits the client's whole tool set
  — and never "no agent" or a refusal.

Every decision records the words that caused it, so the router's accuracy is
measurable against a labelled set rather than a matter of opinion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.agents.base import AgentRegistry, AgentSpec

# Each pattern is a phrase that only really occurs in one of the owner's
# domains. Scoring is "how many distinct signals matched", so a message has to
# lean into a domain to be routed there; one incidental word does not do it.
DOMAIN_SIGNALS: dict[str, list[re.Pattern[str]]] = {
    "trading": [
        # instruments
        re.compile(r"(?i)\b(gold|xau|silver|xag|us100|nas100|us500|spx|btc|usdjpy|eurusd|dxy)\b"),
        # execution vocabulary
        re.compile(r"(?i)\b(trade|trades|trading|entry|entries|stop ?loss|take ?profit|sl|tp|lot|lots|position|positions|order|orders)\b"),
        # market reading
        re.compile(r"(?i)\b(plan|setup|bias|outlook|session|pullback|trend|structure|candle|level|levels|support|resistance)\b"),
        # the calendar
        re.compile(r"(?i)\b(fomc|nfp|cpi|news|calendar|high[- ]impact|rate decision|payrolls?)\b"),
        # the system's parts
        re.compile(r"(?i)\b(council|pine|v7|v18|executor|mt5|bot|desk|lane|lanes|brain)\b"),
        # what it emits
        re.compile(r"(?i)\b(signal|signals|grade|grades|dispatch|payload|webhook|alert|alerts)\b"),
        # how it is judged
        re.compile(r"(?i)\b(win ?rate|profit ?factor|drawdown|expectancy|backtest|equity|journal|sample)\b"),
    ],
    "architect": [
        # shape of the software
        re.compile(r"(?i)\b(architecture|refactor|rewrite|redesign|module|modules|boundary|contract|interface)\b"),
        # something is wrong
        re.compile(r"(?i)\b(bug|defect|regression|stack ?trace|traceback|exception|error|crash|50\d)\b"),
        # the machines
        re.compile(r"(?i)\b(deploy|rollback|docker|nginx|systemd|compose|alembic|container|image|stack)\b"),
        # the checks
        re.compile(r"(?i)\b(test|tests|pytest|coverage|ci|lint|ruff|fixture)\b"),
        # the code
        re.compile(r"(?i)\b(code|function|class|api|database|schema|endpoint|router|sqlalchemy|fastapi|python|migration)\b"),
        # asking why
        re.compile(r"(?i)\b(why does|why is|how does|root cause|diagnose|broken|failing|not working)\b"),
        # the parts inside
        re.compile(r"(?i)\b(namespace|cache|queue|worker|config|parameter|scoped|retrieval|index)\b"),
        # the process around a change
        re.compile(r"(?i)\b(ceremony|backup|restart|verify|logs|commit|branch|revert)\b"),
        # data shapes
        re.compile(r"(?i)\b(table|tables|column|row|rows|record|records|entity|relation)\b"),
    ],
    "social": [
        # where it goes
        re.compile(r"(?i)\b(post|posts|thread|tweet|caption|linkedin|telegram|youtube|x\.com|instagram)\b"),
        # the act of authoring
        re.compile(r"(?i)\b(draft|write|compose|announce|publish|share)\b"),
        # who reads it
        re.compile(r"(?i)\b(audience|followers|hashtags?|engagement|viral|subscribers)\b"),
        # what is being made
        re.compile(r"(?i)\b(content|copy|headline|blurb|description|video|reel|short|clip|script)\b"),
    ],
}

# Words that pull a message out of a domain even when its vocabulary matched.
# "write a post about the trading system" is social, not trading.
DOMAIN_VETOES: dict[str, re.Pattern[str]] = {
    "trading": re.compile(r"(?i)\b(post|thread|tweet|caption|linkedin|hashtags?)\b"),
}

# At least this many distinct signals, or the message has not leaned far
# enough into a domain to move it off the generalist.
MIN_SIGNALS = 2

FALLBACK = "brother"


@dataclass(frozen=True)
class AgentChoice:
    name: str
    reason: str
    score: int = 0
    matched: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "agent": self.name,
            "reason": self.reason,
            "score": self.score,
            "matched": list(self.matched),
        }


def score_domains(message: str) -> dict[str, tuple[int, tuple[str, ...]]]:
    """How many distinct signals each domain found, and which words did it."""
    text = (message or "").strip()
    out: dict[str, tuple[int, tuple[str, ...]]] = {}
    for domain, patterns in DOMAIN_SIGNALS.items():
        veto = DOMAIN_VETOES.get(domain)
        if veto is not None and veto.search(text):
            out[domain] = (0, ())
            continue
        hits: list[str] = []
        for pattern in patterns:
            found = pattern.search(text)
            if found:
                hits.append(found.group(0).lower())
        out[domain] = (len(hits), tuple(hits))
    return out


def route_agent(
    message: str,
    registry: AgentRegistry,
    *,
    fallback: str = FALLBACK,
) -> AgentChoice:
    """Pick the specialist for this message. Never returns nothing.

    A tie goes to the fallback: two domains matching equally well means the
    message is not clearly either, and the generalist carries every tool.
    """
    default = registry.get(fallback)
    fallback_name = fallback if default is not None and default.enabled else "general"

    scores = score_domains(message)
    ranked = sorted(scores.items(), key=lambda kv: kv[1][0], reverse=True)
    if not ranked:
        return AgentChoice(fallback_name, "no domain signals are configured")

    top_domain, (top_score, matched) = ranked[0]
    runner_up = ranked[1][1][0] if len(ranked) > 1 else 0

    if top_score < MIN_SIGNALS:
        return AgentChoice(
            fallback_name,
            f"nothing pointed to a specialist (best was {top_domain} with {top_score})",
            top_score,
            matched,
        )
    if top_score == runner_up:
        return AgentChoice(
            fallback_name,
            f"two domains matched equally well ({top_score} each); not clearly either",
            top_score,
            matched,
        )
    spec = registry.get(top_domain)
    if spec is None or not spec.enabled:
        return AgentChoice(
            fallback_name, f"the {top_domain} agent is not available", top_score, matched
        )
    return AgentChoice(
        spec.name, "matched " + ", ".join(sorted(set(matched))), top_score, matched
    )


def resolve_requested(
    requested: str | None, message: str, registry: AgentRegistry, *, fallback: str = FALLBACK
) -> tuple[AgentSpec | None, AgentChoice | None]:
    """Honour an explicit choice; route only when the caller asked for "auto".

    A named agent is never overridden. Someone who picked the social agent for
    a question about gold meant it, and a router that argues with an explicit
    instruction is worse than no router.
    """
    if requested and requested.lower() != "auto":
        return registry.get(requested), None
    choice = route_agent(message, registry, fallback=fallback)
    return registry.get(choice.name), choice
