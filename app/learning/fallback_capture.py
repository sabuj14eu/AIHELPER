"""Capture a fallback case.

Recording a case is unconditional; *believing* it is not. Every escalation
that produced an answer is written down with the full picture — what was
asked, what the local model produced, why that was rejected, which provider
solved it, and how the answer scored — and it enters the pipeline as a
CANDIDATE. Nothing here promotes anything.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.audit import SOLUTION_CAPTURED, record
from app.core.logging import get_logger
from app.database.enums import Classification, SolutionStatus
from app.database.models import SolutionCandidate
from app.learning.solution_store import SolutionStore

log = get_logger("learning")


@dataclass
class CaptureDecision:
    captured: bool
    solution: SolutionCandidate | None = None
    reason: str = ""


def capture(
    session: Session,
    client_id: str,
    *,
    question: str,
    answer: str,
    task_type: str,
    provider: str,
    model: str,
    failure_reason: str | None,
    local_attempt: str | None,
    validation: dict | None,
    confidence: float,
    classification: Classification | str,
    context: dict | None = None,
    request_id: str | None = None,
    ttl_days: int | None = None,
    injection_suspected: bool = False,
) -> CaptureDecision:
    """Store the fallback case, or say why it was not stored."""
    if not answer or not answer.strip():
        return CaptureDecision(False, reason="empty answer")

    classification_enum = Classification(str(classification).upper())
    if classification_enum is Classification.RESTRICTED:
        # A RESTRICTED request never reached an external provider, so this
        # should be unreachable; refuse anyway rather than rely on that.
        return CaptureDecision(False, reason="RESTRICTED content is not stored as a solution")

    if injection_suspected:
        # An answer produced from a request that looked like an injection
        # attempt is not learning material.
        return CaptureDecision(
            False, reason="request flagged for possible prompt injection; not captured"
        )

    store = SolutionStore(session, client_id)
    solution = store.create(
        question=question,
        answer=answer,
        task_type=str(task_type),
        provider=provider,
        model=model,
        failure_reason=failure_reason,
        local_attempt=local_attempt,
        validation_result=validation,
        confidence=confidence,
        classification=classification_enum,
        context=context,
        source_request_id=request_id,
        ttl_days=ttl_days,
    )
    record(
        session,
        actor=client_id,
        action=SOLUTION_CAPTURED,
        resource_type="solution",
        resource_id=solution.id,
        request_id=request_id,
        detail={
            "provider": provider,
            "model": model,
            "task_type": str(task_type),
            "failure_reason": failure_reason,
            "confidence": round(confidence, 3),
            "status": SolutionStatus.CANDIDATE.value,
        },
    )
    log.info(
        "fallback_captured",
        solution_id=solution.id,
        provider=provider,
        failure_reason=failure_reason,
    )
    return CaptureDecision(True, solution=solution)
