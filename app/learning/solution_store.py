"""Storage and lifecycle for solution candidates.

Statuses and what each one means:

* ``CANDIDATE`` — a paid provider answered a question the local stack could
  not. Recorded, never yet used.
* ``VALIDATED`` — the answer passed the validation pipeline on its own terms.
* ``PROMOTED`` — the answer was additionally shown to be *usable by the local
  model*, and is now offered back as context. This is the only status that
  retrieval will return.
* ``REJECTED`` — failed a gate. Kept, because knowing what did not work is
  how the fallback report stays honest.
* ``EXPIRED`` — aged out. An answer that was right last March is not
  automatically right today.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.database.enums import Classification, SolutionStatus
from app.database.models import SolutionCandidate
from app.learning.similarity import fingerprint, normalise


class SolutionStore:
    def __init__(self, session: Session, client_id: str):
        self.session = session
        self.client_id = client_id

    # ---------------------------------------------------------------- write
    def create(
        self,
        *,
        question: str,
        answer: str,
        task_type: str,
        provider: str,
        model: str,
        failure_reason: str | None,
        local_attempt: str | None,
        validation_result: dict | None,
        confidence: float,
        classification: Classification | str = Classification.INTERNAL,
        context: dict | None = None,
        source_request_id: str | None = None,
        ttl_days: int | None = None,
    ) -> SolutionCandidate:
        expires_at = (
            datetime.now(UTC) + timedelta(days=ttl_days) if ttl_days else None
        )
        solution = SolutionCandidate(
            id=new_id("sol"),
            client_id=self.client_id,
            fingerprint=fingerprint(question, salt=self.client_id),
            question=question,
            normalized_question=normalise(question),
            task_type=task_type,
            classification=str(Classification(str(classification).upper()).value),
            context=context or {},
            local_attempt=(local_attempt or "")[:8000] or None,
            failure_reason=failure_reason,
            provider=provider,
            model=model,
            answer=answer,
            validation_result=validation_result or {},
            confidence=float(confidence),
            status=SolutionStatus.CANDIDATE.value,
            expires_at=expires_at,
            source_request_id=source_request_id,
        )
        self.session.add(solution)
        self.session.flush()
        return solution

    def set_status(
        self, solution: SolutionCandidate, status: SolutionStatus, reason: str = ""
    ) -> SolutionCandidate:
        solution.status = status.value
        solution.status_reason = reason[:300] or None
        if status is SolutionStatus.PROMOTED:
            solution.promoted_at = datetime.now(UTC)
        # Autoflush is off: flush so a read later in the same request sees this.
        self.session.flush()
        return solution

    def mark_used(self, solution: SolutionCandidate) -> None:
        solution.reuse_count = (solution.reuse_count or 0) + 1
        solution.last_used_at = datetime.now(UTC)
        self.session.flush()

    # ----------------------------------------------------------------- read
    def get(self, solution_id: str) -> SolutionCandidate | None:
        solution = self.session.get(SolutionCandidate, solution_id)
        if solution is None or solution.client_id != self.client_id:
            return None
        return solution

    def by_fingerprint(
        self, question: str, statuses: list[SolutionStatus] | None = None
    ) -> list[SolutionCandidate]:
        stmt = select(SolutionCandidate).where(
            SolutionCandidate.client_id == self.client_id,
            SolutionCandidate.fingerprint == fingerprint(question, salt=self.client_id),
        )
        if statuses:
            stmt = stmt.where(SolutionCandidate.status.in_([s.value for s in statuses]))
        return list(self.session.scalars(stmt.order_by(SolutionCandidate.created_at.desc())))

    def list(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
        all_clients: bool = False,
    ) -> list[SolutionCandidate]:
        stmt = select(SolutionCandidate)
        if not all_clients:
            stmt = stmt.where(SolutionCandidate.client_id == self.client_id)
        if status:
            stmt = stmt.where(SolutionCandidate.status == status)
        stmt = stmt.order_by(SolutionCandidate.created_at.desc()).limit(min(limit, 500)).offset(offset)
        return list(self.session.scalars(stmt))

    def counts(self, *, all_clients: bool = False) -> dict[str, int]:
        stmt = select(SolutionCandidate.status, func.count(SolutionCandidate.id))
        if not all_clients:
            stmt = stmt.where(SolutionCandidate.client_id == self.client_id)
        stmt = stmt.group_by(SolutionCandidate.status)
        counts = {status.value: 0 for status in SolutionStatus}
        for status, count in self.session.execute(stmt):
            counts[status] = int(count)
        return counts

    # ------------------------------------------------------------ lifecycle
    def expire_due(self, *, all_clients: bool = False) -> list[SolutionCandidate]:
        now = datetime.now(UTC)
        stmt = select(SolutionCandidate).where(
            SolutionCandidate.expires_at.is_not(None),
            SolutionCandidate.expires_at <= now,
            SolutionCandidate.status.in_(
                [SolutionStatus.CANDIDATE.value, SolutionStatus.VALIDATED.value, SolutionStatus.PROMOTED.value]
            ),
        )
        if not all_clients:
            stmt = stmt.where(SolutionCandidate.client_id == self.client_id)
        expired = list(self.session.scalars(stmt))
        for solution in expired:
            solution.status = SolutionStatus.EXPIRED.value
            solution.status_reason = "time-to-live elapsed"
        self.session.flush()
        return expired
