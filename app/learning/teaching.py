"""Teaching: the owner corrects Brother, and the correction goes through the gate.

The learning loop shipped in 1.0 learns only from paid answers. A
deployment that refuses paid providers on principle would therefore never
learn anything new, however many times the owner told it the right answer.
This is the other source: a human supplies question and answer, the pair
becomes a CANDIDATE like any paid answer would, and it must still pass the
same two gates (validation, then reproduction by the local model) before it
is offered back. A taught answer is not trusted because the owner typed it;
it is trusted because the local model showed it can use it.

A taught answer for a question that already has a PROMOTED solution
supersedes it: the old row is EXPIRED with the reason, never edited (a
changed mind is a new row).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.audit import SOLUTION_CAPTURED, record
from app.core.config import Settings
from app.core.logging import get_logger
from app.database.enums import Classification, SolutionStatus
from app.learning.promotion import PromotionOutcome, PromotionPipeline
from app.learning.solution_store import SolutionStore

log = get_logger("teaching")

TAUGHT_PROVIDER = "owner"


@dataclass
class TeachResult:
    solution_id: str
    outcome: PromotionOutcome
    superseded: list[str]

    def as_dict(self) -> dict:
        return {
            "solution_id": self.solution_id,
            "status": self.outcome.status.value,
            "reason": self.outcome.reason,
            "promoted": self.outcome.promoted,
            "reproduction": self.outcome.reproduction,
            "superseded": list(self.superseded),
        }


def teach(
    session: Session,
    client_id: str,
    *,
    question: str,
    answer: str,
    actor: str,
    settings: Settings,
    local_provider,
    retriever,
    evidence: str = "",
    classification: Classification | str = Classification.INTERNAL,
) -> TeachResult:
    question = (question or "").strip()
    answer = (answer or "").strip()
    if len(question) < 3 or len(answer) < 3:
        raise ValueError("a taught pair needs both a question and an answer")

    store = SolutionStore(session, client_id)
    pipeline = PromotionPipeline(
        session,
        client_id,
        settings=settings,
        local_provider=local_provider,
        retriever=retriever,
    )

    superseded: list[str] = []
    for old in store.by_fingerprint(question, statuses=[SolutionStatus.PROMOTED, SolutionStatus.VALIDATED]):
        old.status = SolutionStatus.EXPIRED.value
        old.status_reason = f"superseded by an answer taught by {actor}"[:300]
        old.expires_at = datetime.now(UTC)
        if retriever is not None:
            try:
                retriever.unindex_solution(old.id)
            except Exception as exc:  # the supersede must not fail on the index
                log.warning("teach_unindex_failed", solution_id=old.id, error=type(exc).__name__)
        superseded.append(old.id)
    session.flush()

    solution = store.create(
        question=question,
        answer=answer,
        task_type="general",
        provider=TAUGHT_PROVIDER,
        model=actor[:120],
        failure_reason=None,
        local_attempt=None,
        validation_result={"taught": {"by": actor, "evidence": evidence[:500]}},
        confidence=0.0,
        classification=classification,
        context={
            "texts": [answer if not evidence else f"{answer}\nEvidence: {evidence}"],
            "sources": [{"source": TAUGHT_PROVIDER, "ref": actor}],
        },
        ttl_days=None,
    )
    record(
        session,
        actor=actor,
        actor_type="admin",
        action=SOLUTION_CAPTURED,
        resource_type="solution",
        resource_id=solution.id,
        detail={"taught": True, "superseded": superseded},
    )
    outcome = pipeline.process(solution)
    log.info("taught", solution_id=solution.id, status=outcome.status.value, by=actor)
    return TeachResult(solution_id=solution.id, outcome=outcome, superseded=superseded)
