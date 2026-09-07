"""Model discovery and provider status."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import admin_client, current_client, runtime_dep
from app.api.schemas import ModelOut, ModelsResponse
from app.core.errors import ProviderUnavailableError
from app.database.models import Client
from app.runtime import Runtime

router = APIRouter(prefix="/api/v1", tags=["models"])


@router.get("/models", response_model=ModelsResponse, summary="Installed models and providers")
def list_models(
    _client: Client = Depends(current_client),
    runtime: Runtime = Depends(runtime_dep),
) -> ModelsResponse:
    manager = getattr(runtime.providers, "model_manager", None)
    rows = manager.report() if manager is not None else []
    local = runtime.providers.local
    available = bool(local and local.health().available)
    return ModelsResponse(
        local_available=available,
        models=[ModelOut(**row) for row in rows],
        embedder=runtime.embedder.id,
        embedder_semantic=runtime.embedder.semantic,
        providers=[h.as_dict() for h in runtime.providers.health()],
    )


@router.post("/models/{model_name:path}/pull", summary="Download a local model (admin)")
def pull_model(
    model_name: str,
    _admin: Client = Depends(admin_client),
    runtime: Runtime = Depends(runtime_dep),
) -> dict:
    """Ask Ollama to download a model. Long-running; the call blocks."""
    client = getattr(runtime.providers, "ollama_client", None)
    if client is None:
        raise ProviderUnavailableError("no Ollama client is configured")
    result = client.pull(model_name)
    manager = getattr(runtime.providers, "model_manager", None)
    if manager is not None:
        manager.invalidate()
    return {"model": model_name, "status": result.get("status", "completed")}


@router.get("/agents", summary="Available agent profiles")
def list_agents(_client: Client = Depends(current_client)) -> list[dict]:
    from app.api.deps import AGENTS

    return [spec.as_dict() for spec in AGENTS.list()]


@router.get("/tools", summary="Tools this client may use")
def list_tools(
    client: Client = Depends(current_client),
    runtime: Runtime = Depends(runtime_dep),
) -> list[dict]:
    return [spec.as_dict() for spec in runtime.tools.available_to(client.allowed_tools)]
