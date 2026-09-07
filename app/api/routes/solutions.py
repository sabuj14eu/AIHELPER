"""The learned-solution lifecycle, exposed for review and manual promotion."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import current_client, runtime_dep, services_dep
from app.api.schemas import SolutionOut
from app.core.errors import NotFoundError
from app.database.models import Client
from app.learning.promotion import PromotionPipeline
from app.learning.solution_store import SolutionStore
from app.runtime import Runtime, SessionServices

router = APIRouter(prefix="/api/v1", tags=["solutions"])


def _out(s) -> SolutionOut:
    return SolutionOut(
        id=s.id,
        question=s.question,
        task_type=s.task_type,
        status=s.status,
        status_reason=s.status_reason,
        provider=s.provider,
        model=s.model,
        confidence=s.confidence,
        failure_reason=s.failure_reason,
        reuse_count=s.reuse_count,
        created_at=s.created_at,
        promoted_at=s.promoted_at,
    )


@router.get("/solutions", response_model=list[SolutionOut], summary="List learned solutions")
def list_solutions(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    client: Client = Depends(current_client),
    services: SessionServices = Depends(services_dep),
) -> list[SolutionOut]:
    store = SolutionStore(services.session, client.client_id)
    return [
        _out(s)
        for s in store.list(
            status=status, limit=limit, offset=offset, all_clients=client.is_admin
        )
    ]


@router.get("/solutions/counts", summary="Counts by status")
def solution_counts(
    client: Client = Depends(current_client),
    services: SessionServices = Depends(services_dep),
) -> dict:
    return SolutionStore(services.session, client.client_id).counts(all_clients=client.is_admin)


@router.get("/solutions/{solution_id}", summary="One solution, in full")
def get_solution(
    solution_id: str,
    client: Client = Depends(current_client),
    services: SessionServices = Depends(services_dep),
) -> dict:
    solution = SolutionStore(services.session, client.client_id).get(solution_id)
    if solution is None:
        raise NotFoundError(f"solution '{solution_id}' not found")
    return {
        **_out(solution).model_dump(),
        "answer": solution.answer,
        "local_attempt": solution.local_attempt,
        "validation_result": solution.validation_result,
        "reproduction": solution.reproduction,
        "context": solution.context,
        "expires_at": solution.expires_at.isoformat() if solution.expires_at else None,
    }


@router.post("/solutions/{solution_id}/promote", summary="Run the promotion pipeline")
def promote(
    solution_id: str,
    client: Client = Depends(current_client),
    services: SessionServices = Depends(services_dep),
    runtime: Runtime = Depends(runtime_dep),
) -> dict:
    solution = SolutionStore(services.session, client.client_id).get(solution_id)
    if solution is None:
        raise NotFoundError(f"solution '{solution_id}' not found")
    pipeline = PromotionPipeline(
        services.session,
        client.client_id,
        settings=services.settings,
        local_provider=runtime.providers.local,
        retriever=services.retriever,
    )
    return pipeline.process(solution).as_dict()


@router.post("/solutions/{solution_id}/reject", summary="Reject a solution")
def reject(
    solution_id: str,
    reason: str = "rejected by a reviewer",
    client: Client = Depends(current_client),
    services: SessionServices = Depends(services_dep),
    runtime: Runtime = Depends(runtime_dep),
) -> dict:
    solution = SolutionStore(services.session, client.client_id).get(solution_id)
    if solution is None:
        raise NotFoundError(f"solution '{solution_id}' not found")
    pipeline = PromotionPipeline(
        services.session,
        client.client_id,
        settings=services.settings,
        local_provider=runtime.providers.local,
        retriever=services.retriever,
    )
    return pipeline.reject(solution, reason).as_dict()
