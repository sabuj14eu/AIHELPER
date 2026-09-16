"""What kind of turn this was.

Validation used to answer one question — *did this answer pass?* — and the
router turned the two possible replies into two possible outcomes: a validated
answer, or a failure. That collapsed four situations the assistant genuinely
faces into two, and it put the worst reading on the two in the middle:

* a careful answer that names what it could not establish was labelled
  exactly like a suspected hallucination, and
* "the evidence for this does not exist", which the constitution calls a
  first-class successful outcome, was presented as a technical failure
  alongside "the local model crashed".

So the boolean stays — it still decides escalation and promotion, and nothing
here relaxes it — and this module sits beside it to say which of the four
situations actually occurred. The verdict drives what the reader is shown.

The bar is not lowered anywhere. One case is deliberately *tightened*: an
answer vetoed for contradicting its own sources, for a safety finding, for a
degenerate loop or for disagreeing with a deterministic tool used to be
returned to the reader with an "unverified" label. There is no reading of
those vetoes under which the text is worth showing, so it is withheld and the
reason is named instead.
"""

from __future__ import annotations

from enum import StrEnum

from app.validation.confidence import ValidationReport


class AnswerState(StrEnum):
    VERIFIED = "verified"
    """Passed validation: grounded, decisive, no veto. Say it plainly."""

    USEFUL = "useful"
    """A real answer that did not clear the bar. Show it, say it is unverified."""

    INSUFFICIENT = "insufficient"
    """The model reported it lacks the evidence. A successful outcome, not a fault."""

    FAILED = "failed"
    """No answer that can be shown: nothing came back, or what came back must not be."""


# The model said, in one form or another, "the evidence for this is not in
# front of me". That is a report about the *evidence*, not a refusal to work,
# and it is the answer to some questions.
INSUFFICIENCY_VETOES = frozenset(
    {"model_declared_insufficient_context", "model_lacks_evidence", "model_refused"}
)

# No reading of these leaves the text worth showing.
WITHHOLDING_VETOES = frozenset(
    {
        "safety_violation",
        "contradicts_context",
        "repetitive_output",
        "format_invalid",
        "disagrees_with_deterministic_tool",
    }
)

_WITHHOLD_REASON = {
    "safety_violation": "the answer failed a safety check",
    "contradicts_context": "the answer contradicted the sources it was given",
    "repetitive_output": "the model produced a repeating loop rather than an answer",
    "format_invalid": "the answer was not in the format that was requested",
    "disagrees_with_deterministic_tool": (
        "the answer disagreed with a calculation the system had already made"
    ),
}


def derive_state(*, has_text: bool, validation: ValidationReport | None) -> AnswerState:
    """Which of the four situations this turn is.

    ``has_text`` is whether the model returned anything at all — the router
    knows this and validation does not, because a call that raised never
    reaches a validator.
    """
    if not has_text:
        return AnswerState.FAILED
    if validation is None:
        # Answered, never judged (no validator ran). Honest label: unverified.
        return AnswerState.USEFUL
    if validation.passed:
        return AnswerState.VERIFIED
    vetoes = set(validation.vetoes)
    if vetoes & WITHHOLDING_VETOES:
        return AnswerState.FAILED
    if vetoes & INSUFFICIENCY_VETOES:
        return AnswerState.INSUFFICIENT
    return AnswerState.USEFUL


def withholding_reason(validation: ValidationReport | None) -> str | None:
    """Why a produced answer is not being shown, in words a reader can act on."""
    if validation is None:
        return None
    for veto in validation.vetoes:
        if veto in _WITHHOLD_REASON:
            return _WITHHOLD_REASON[veto]
    return None
