"""Health.

Component status, in the shape the work order asked for. A component that
cannot be probed reports UNKNOWN, never OK: an unprobed component is not a
healthy one, and paid providers are reported as configured-or-not rather than
probed, because probing them costs money.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text

from app import __version__
from app.api.deps import runtime_dep, settings_dep
from app.api.schemas import ComponentHealth, HealthResponse
from app.core.config import Settings
from app.database.session import get_engine
from app.runtime import Runtime

router = APIRouter(tags=["health"])


def _database() -> ComponentHealth:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return ComponentHealth(name="database", status="OK")
    except Exception as exc:
        return ComponentHealth(name="database", status="DOWN", detail=type(exc).__name__)


def _qdrant(runtime: Runtime, settings: Settings) -> ComponentHealth:
    if not settings.QDRANT_ENABLED:
        return ComponentHealth(
            name="qdrant",
            status="DISABLED",
            detail=f"semantic memory is using the {runtime.vector_backend} backend",
        )
    if runtime.recheck_qdrant():
        return ComponentHealth(name="qdrant", status="OK")
    return ComponentHealth(
        name="qdrant",
        status="DOWN",
        detail="unreachable; semantic memory has fallen back to the database vector store",
    )


def _n8n(settings: Settings) -> ComponentHealth:
    if not settings.N8N_URL:
        return ComponentHealth(name="n8n", status="DISABLED")
    import httpx

    try:
        response = httpx.get(f"{settings.N8N_URL.rstrip('/')}/healthz", timeout=3.0)
        if response.status_code < 500:
            return ComponentHealth(name="n8n", status="OK")
        return ComponentHealth(name="n8n", status="DOWN", detail=f"HTTP {response.status_code}")
    except Exception as exc:
        return ComponentHealth(name="n8n", status="DOWN", detail=type(exc).__name__)


def _collect(runtime: Runtime, settings: Settings) -> list[ComponentHealth]:
    components = [
        ComponentHealth(name="gateway", status="OK", detail=f"v{__version__}"),
        _database(),
        _qdrant(runtime, settings),
    ]
    for status in runtime.providers.health():
        data = status.as_dict()
        components.append(
            ComponentHealth(
                name=status.name,
                status=data["status"],
                detail=data["detail"] or ", ".join(data["models"][:3]),
            )
        )
    components.append(_n8n(settings))
    components.append(
        ComponentHealth(
            name="embedder",
            status="OK" if runtime.embedder.semantic else "DEGRADED",
            detail=(
                f"{runtime.embedder.id}"
                + ("" if runtime.embedder.semantic else " — lexical fallback, not semantic")
            ),
        )
    )
    return components


def _overall(components: list[ComponentHealth]) -> str:
    if any(c.status == "DOWN" and c.name in ("database", "gateway") for c in components):
        return "down"
    if any(c.status in ("DOWN", "DEGRADED", "UNAVAILABLE") for c in components):
        return "degraded"
    return "ok"


@router.get("/health", response_model=HealthResponse, summary="Component health")
def health(
    response: Response,
    runtime: Runtime = Depends(runtime_dep),
    settings: Settings = Depends(settings_dep),
) -> HealthResponse:
    components = _collect(runtime, settings)
    status = _overall(components)
    if status == "down":
        response.status_code = 503
    return HealthResponse(
        status=status,
        version=__version__,
        environment=settings.ENVIRONMENT,
        components=components,
        checked_at=datetime.now(UTC),
    )


@router.get("/api/v1/health", response_model=HealthResponse, summary="Component health (v1)")
def health_v1(
    response: Response,
    runtime: Runtime = Depends(runtime_dep),
    settings: Settings = Depends(settings_dep),
) -> HealthResponse:
    return health(response, runtime, settings)


@router.get("/healthz", summary="Liveness probe")
def healthz() -> dict:
    """Is the process up? Nothing more — used by the container orchestrator."""
    return {"status": "alive"}


@router.get("/readyz", summary="Readiness probe")
def readyz(response: Response, runtime: Runtime = Depends(runtime_dep)) -> dict:
    database = _database()
    ready = database.status == "OK"
    if not ready:
        response.status_code = 503
    return {"ready": ready, "database": database.status}
