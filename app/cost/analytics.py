"""Learning and usage metrics.

The "estimated money saved" figure needs its assumption stated, because a
number like that is easy to quote and hard to defend. It is:

    (requests answered without a paid call) x (the mean cost of the paid calls
    that WERE made)

That is a counterfactual — it assumes each locally-answered request would
otherwise have cost about what an escalated one costs. It is an estimate of
avoided spend, not an invoice, and when no paid call has ever been made there
is no basis for it and it reports zero rather than guessing a rate.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.enums import Route, SolutionStatus
from app.database.models import CostRecord, RequestLog, SolutionCandidate


def _window(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


def usage_summary(session: Session, *, days: int = 30, client_id: str | None = None) -> dict:
    since = _window(days)

    def scoped(stmt):
        stmt = stmt.where(RequestLog.created_at >= since)
        if client_id:
            stmt = stmt.where(RequestLog.client_id == client_id)
        return stmt

    rows = session.execute(
        scoped(select(RequestLog.route, func.count(RequestLog.request_id))).group_by(RequestLog.route)
    ).all()
    by_route = {route: int(count) for route, count in rows}
    total = sum(by_route.values())

    paid = by_route.get(Route.PAID.value, 0)
    local = by_route.get(Route.LOCAL.value, 0)
    tool = by_route.get(Route.TOOL.value, 0)
    memory = by_route.get(Route.MEMORY.value, 0)
    failed = by_route.get(Route.FAILED.value, 0)

    memory_hits = int(
        session.execute(
            scoped(select(func.count(RequestLog.request_id))).where(RequestLog.memory_hit.is_(True))
        ).scalar_one()
        or 0
    )
    successes = int(
        session.execute(
            scoped(select(func.count(RequestLog.request_id))).where(RequestLog.success.is_(True))
        ).scalar_one()
        or 0
    )
    # Answered successfully AND without paying. This is the number the local-first
    # claim rests on, so it counts successes rather than merely "did not
    # escalate" — a request that failed outright is not a local success.
    local_successes = int(
        session.execute(
            scoped(select(func.count(RequestLog.request_id)))
            .where(RequestLog.success.is_(True))
            .where(RequestLog.route != Route.PAID.value)
        ).scalar_one()
        or 0
    )

    reasons = [
        {"reason": reason or "UNKNOWN", "count": int(count)}
        for reason, count in session.execute(
            scoped(
                select(RequestLog.escalation_reason, func.count(RequestLog.request_id))
            )
            .where(RequestLog.escalation_reason.is_not(None))
            .group_by(RequestLog.escalation_reason)
            .order_by(func.count(RequestLog.request_id).desc())
        ).all()
    ]

    solution_stmt = select(SolutionCandidate.status, func.count(SolutionCandidate.id)).group_by(
        SolutionCandidate.status
    )
    if client_id:
        solution_stmt = solution_stmt.where(SolutionCandidate.client_id == client_id)
    solutions = {status.value: 0 for status in SolutionStatus}
    for status, count in session.execute(solution_stmt):
        solutions[status] = int(count)

    cost_stmt = select(
        func.coalesce(func.sum(CostRecord.estimated_cost), 0.0), func.count(CostRecord.id)
    ).where(CostRecord.created_at >= since)
    if client_id:
        cost_stmt = cost_stmt.where(CostRecord.client_id == client_id)
    paid_cost, paid_calls = session.execute(cost_stmt).one()
    paid_cost = float(paid_cost or 0.0)
    paid_calls = int(paid_calls or 0)

    # Only requests that were actually answered without paying represent
    # avoided spend. A failed request avoided a cost and delivered nothing;
    # counting it as a saving would flatter the number.
    mean_paid_cost = (paid_cost / paid_calls) if paid_calls else 0.0
    estimated_saved = round(local_successes * mean_paid_cost, 4)

    return {
        "window_days": days,
        "total_requests": total,
        "local_requests": local,
        "tool_requests": tool,
        "memory_requests": memory,
        "api_fallback_requests": paid,
        "failed_requests": failed,
        "fallback_percentage": round(100.0 * paid / total, 2) if total else 0.0,
        "local_success_rate": round(100.0 * local_successes / total, 2) if total else 0.0,
        "answered_locally": local_successes,
        "answered_successfully": successes,
        "memory_hits": memory_hits,
        "promoted_solutions": solutions[SolutionStatus.PROMOTED.value],
        "validated_solutions": solutions[SolutionStatus.VALIDATED.value],
        "candidate_solutions": solutions[SolutionStatus.CANDIDATE.value],
        "rejected_solutions": solutions[SolutionStatus.REJECTED.value],
        "expired_solutions": solutions[SolutionStatus.EXPIRED.value],
        "escalation_reasons": reasons,
        "paid_calls": paid_calls,
        "paid_cost_window": round(paid_cost, 4),
        "mean_paid_call_cost": round(mean_paid_cost, 6),
        "estimated_money_saved_usd": estimated_saved,
        "estimate_basis": (
            "requests answered successfully without paying x the mean cost of the paid "
            "calls actually made; zero until at least one paid call exists"
        ),
    }


def recent_requests(
    session: Session, *, limit: int = 50, client_id: str | None = None, route: str | None = None
) -> list[RequestLog]:
    stmt = select(RequestLog).order_by(RequestLog.created_at.desc()).limit(min(limit, 500))
    if client_id:
        stmt = stmt.where(RequestLog.client_id == client_id)
    if route:
        stmt = stmt.where(RequestLog.route == route)
    return list(session.scalars(stmt))


def fallback_report(session: Session, *, limit: int = 50, client_id: str | None = None) -> list[dict]:
    """Why local AI failed, who solved it, and what happened to the answer."""
    stmt = (
        select(SolutionCandidate)
        .order_by(SolutionCandidate.created_at.desc())
        .limit(min(limit, 200))
    )
    if client_id:
        stmt = stmt.where(SolutionCandidate.client_id == client_id)
    return [
        {
            "id": s.id,
            "client_id": s.client_id,
            "question": s.question[:200],
            "task_type": s.task_type,
            "failure_reason": s.failure_reason,
            "provider": s.provider,
            "model": s.model,
            "status": s.status,
            "status_reason": s.status_reason,
            "confidence": round(s.confidence, 3),
            "reuse_count": s.reuse_count,
            "reproduction": s.reproduction or {},
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in session.scalars(stmt)
    ]
