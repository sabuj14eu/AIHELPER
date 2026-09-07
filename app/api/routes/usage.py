"""Usage, cost and the learning metrics.

A client sees its own numbers. An admin key sees the deployment's.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import current_client, services_dep
from app.api.schemas import CostResponse, UsageResponse
from app.cost.analytics import fallback_report, recent_requests, usage_summary
from app.database.models import Client
from app.runtime import SessionServices

router = APIRouter(prefix="/api/v1", tags=["usage"])


def _scope(client: Client) -> str | None:
    """An admin key sees everything; every other key sees only itself."""
    return None if client.is_admin else client.client_id


@router.get("/usage", response_model=UsageResponse, summary="Learning and routing metrics")
def usage(
    days: int = 30,
    client: Client = Depends(current_client),
    services: SessionServices = Depends(services_dep),
) -> UsageResponse:
    summary = usage_summary(services.session, days=days, client_id=_scope(client))
    spend = services.cost.summary()
    return UsageResponse(
        window_days=summary["window_days"],
        total_requests=summary["total_requests"],
        local_requests=summary["local_requests"],
        tool_requests=summary["tool_requests"],
        memory_requests=summary["memory_requests"],
        api_fallback_requests=summary["api_fallback_requests"],
        failed_requests=summary["failed_requests"],
        fallback_percentage=summary["fallback_percentage"],
        local_success_rate=summary["local_success_rate"],
        answered_locally=summary["answered_locally"],
        memory_hits=summary["memory_hits"],
        promoted_solutions=summary["promoted_solutions"],
        rejected_solutions=summary["rejected_solutions"],
        candidate_solutions=summary["candidate_solutions"],
        escalation_reasons=summary["escalation_reasons"],
        escalations_blocked=summary["escalations_blocked"],
        escalations_blocked_total=summary["escalations_blocked_total"],
        escalations_blocked_by_budget=summary["escalations_blocked_by_budget"],
        estimated_money_saved_usd=summary["estimated_money_saved_usd"],
        api_cost_today=round(spend.today, 4),
        api_cost_month=round(spend.month, 4),
    )


@router.get("/costs", response_model=CostResponse, summary="Spend against the budgets")
def costs(
    days: int = 30,
    _client: Client = Depends(current_client),
    services: SessionServices = Depends(services_dep),
) -> CostResponse:
    spend = services.cost.summary().as_dict()
    return CostResponse(
        **spend,
        by_provider=services.cost.by_provider(days=days),
        by_escalation_reason=services.cost.by_escalation_reason(days=days),
    )


@router.get("/usage/fallbacks", summary="Why local AI failed, and what happened next")
def fallbacks(
    limit: int = 50,
    client: Client = Depends(current_client),
    services: SessionServices = Depends(services_dep),
) -> list[dict]:
    return fallback_report(services.session, limit=limit, client_id=_scope(client))


@router.get("/usage/requests", summary="Recent request log")
def requests_log(
    limit: int = 50,
    route: str | None = None,
    client: Client = Depends(current_client),
    services: SessionServices = Depends(services_dep),
) -> list[dict]:
    rows = recent_requests(
        services.session, limit=limit, client_id=_scope(client), route=route
    )
    return [
        {
            "request_id": r.request_id,
            "client_id": r.client_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "task_type": r.task_type,
            "classification": r.classification,
            "route": r.route,
            "provider": r.provider,
            "model": r.model,
            "latency_ms": r.latency_ms,
            "cost_usd": r.cost_usd,
            "confidence": r.confidence,
            "memory_hit": r.memory_hit,
            "tool_used": r.tool_used,
            "escalation_reason": r.escalation_reason,
            "escalation_blocked_reason": r.escalation_blocked_reason,
            "success": r.success,
        }
        for r in rows
    ]
