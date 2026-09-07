"""Escalation policy — the decision to spend money.

Two separate questions, deliberately kept apart:

* :func:`why_escalate` — *should* this request go to a paid provider? Answers
  with exactly one :class:`EscalationReason`, or None. This is the field that
  later answers "why are we paying for AI?".
* :func:`may_escalate` — *is it allowed to*? Answers with a
  :class:`EscalationBlockReason` when not. Privacy, budget, client permission
  and configuration all live here.

Both must say yes. Wanting to escalate is never sufficient.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.database.enums import Classification, EscalationBlockReason, EscalationReason
from app.privacy.classification import may_leave_system
from app.validation.confidence import ValidationReport


@dataclass
class EscalationIntent:
    wanted: bool
    reason: EscalationReason | None = None
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "wanted": self.wanted,
            "reason": self.reason.value if self.reason else None,
            "detail": self.detail,
        }


@dataclass
class EscalationPermission:
    allowed: bool
    blocked_reason: EscalationBlockReason | None = None
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "blocked_reason": self.blocked_reason.value if self.blocked_reason else None,
            "detail": self.detail,
        }


def why_escalate(
    *,
    local_available: bool,
    local_timed_out: bool,
    local_failed: bool,
    validation: ValidationReport | None,
    had_context: bool,
    task_needs_context: bool,
    premium_requested: bool,
    threshold: float,
) -> EscalationIntent:
    """Exactly one reason, chosen most-specific-first."""
    if premium_requested:
        return EscalationIntent(
            True,
            EscalationReason.USER_REQUESTED_PREMIUM_MODEL,
            "the caller explicitly asked for a premium model",
        )
    if local_timed_out:
        return EscalationIntent(
            True, EscalationReason.LOCAL_TIMEOUT, "the local model did not answer in time"
        )
    if not local_available or local_failed:
        return EscalationIntent(
            True,
            EscalationReason.LOCAL_MODEL_UNAVAILABLE,
            "no local model was able to run the request",
        )
    if validation is None:
        return EscalationIntent(False)

    if validation.vetoes:
        # A task that is supposed to be answered from sources, with no sources
        # found, is a retrieval problem rather than a model problem — and it
        # is worth distinguishing, because the fix is different.
        if task_needs_context and not had_context:
            return EscalationIntent(
                True,
                EscalationReason.NO_KNOWLEDGE_FOUND,
                "nothing relevant was retrieved for a question that needs sources",
            )
        return EscalationIntent(
            True,
            EscalationReason.VALIDATION_FAILURE,
            f"the local answer failed validation: {validation.primary_failure}",
        )

    if validation.confidence < threshold:
        if task_needs_context and not had_context:
            return EscalationIntent(
                True,
                EscalationReason.NO_KNOWLEDGE_FOUND,
                "nothing relevant was retrieved for a question that needs sources",
            )
        if validation.confidence < threshold * 0.5:
            return EscalationIntent(
                True,
                EscalationReason.TASK_TOO_COMPLEX,
                f"confidence {validation.confidence:.2f} is far below the {threshold:.2f} threshold",
            )
        return EscalationIntent(
            True,
            EscalationReason.LOW_CONFIDENCE,
            f"confidence {validation.confidence:.2f} is below the {threshold:.2f} threshold",
        )

    return EscalationIntent(False)


def may_escalate(
    *,
    settings: Settings,
    classification: Classification,
    task_type: str,
    client_may_escalate: bool,
    client_max_classification: str | None,
    any_paid_provider: bool,
) -> EscalationPermission:
    """Everything that can forbid an escalation, checked before any spend."""
    # Order matters, and it is not the order the checks are cheapest in.
    # Reasons that are intrinsic to the REQUEST come before reasons that are
    # incidental to today's CONFIGURATION. "we did not send it because no
    # provider is configured" is a much weaker statement than "we would never
    # have sent it", and reporting the weaker one would hide the stronger one
    # from the audit trail — and would silently change meaning the day someone
    # enables a provider.
    ok, detail = may_leave_system(
        classification,
        allowed=settings.external_allowed,
        client_max=client_max_classification,
    )
    if not ok:
        return EscalationPermission(False, EscalationBlockReason.CLASSIFICATION_BLOCKED, detail)
    if not client_may_escalate:
        return EscalationPermission(
            False,
            EscalationBlockReason.CLIENT_NOT_PERMITTED,
            "this client is not permitted to use paid providers",
        )
    if str(task_type).lower() in settings.paid_task_denylist:
        return EscalationPermission(
            False,
            EscalationBlockReason.TASK_TYPE_DENIED,
            f"task type '{task_type}' may not be escalated",
        )
    if not settings.ESCALATION_ENABLED:
        return EscalationPermission(
            False, EscalationBlockReason.DISABLED, "escalation is disabled in this deployment"
        )
    if not any_paid_provider:
        return EscalationPermission(
            False,
            EscalationBlockReason.NOT_CONFIGURED,
            "no paid provider is enabled and configured",
        )
    return EscalationPermission(True)
