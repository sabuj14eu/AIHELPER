"""Memory: write, search, list, revoke. Namespaces are per client."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import current_client, runtime_dep, services_dep
from app.api.schemas import MemoryOut, MemorySearchResult, MemoryWriteRequest
from app.core.audit import MEMORY_DELETED, MEMORY_WRITTEN, record
from app.core.errors import NotFoundError
from app.database.models import Client
from app.memory.long_term import LongTermMemory, namespace_for
from app.runtime import Runtime, SessionServices

router = APIRouter(prefix="/api/v1", tags=["memory"])


def _out(item) -> MemoryOut:
    return MemoryOut(
        id=item.id,
        kind=item.kind,
        content=item.content,
        source=item.source,
        confidence=item.confidence,
        status=item.status,
        sensitivity=item.sensitivity,
        namespace=item.namespace,
        key=item.key,
        expires_at=item.expires_at,
        created_at=item.created_at,
    )


@router.post("/memory", response_model=MemoryOut, summary="Write a long-term memory item")
def write_memory(
    body: MemoryWriteRequest,
    client: Client = Depends(current_client),
    services: SessionServices = Depends(services_dep),
) -> MemoryOut:
    memory = LongTermMemory(services.session, client.client_id)
    item = memory.write(
        body.content,
        source=body.source,
        confidence=body.confidence,
        kind=body.kind,
        sensitivity=body.sensitivity,
        namespace=body.namespace or namespace_for(client.client_id),
        key=body.key,
        owner_ref=body.owner_ref,
        ttl_days=body.ttl_days,
        meta=body.meta,
    )
    services.retriever.index_memory(item)
    record(
        services.session,
        actor=client.client_id,
        action=MEMORY_WRITTEN,
        resource_type="memory",
        resource_id=item.id,
        detail={"kind": item.kind, "sensitivity": item.sensitivity, "source": item.source},
    )
    return _out(item)


@router.get("/memory", response_model=list[MemoryOut], summary="List memory items")
def list_memory(
    namespace: str | None = None,
    kind: str | None = None,
    status: str | None = "ACTIVE",
    limit: int = 50,
    offset: int = 0,
    client: Client = Depends(current_client),
    services: SessionServices = Depends(services_dep),
) -> list[MemoryOut]:
    memory = LongTermMemory(services.session, client.client_id)
    return [
        _out(item)
        for item in memory.list(
            namespace=namespace, kind=kind, status=status, limit=limit, offset=offset
        )
    ]


@router.get("/memory/search", response_model=MemorySearchResult, summary="Semantic memory search")
def search_memory(
    q: str = Query(min_length=2, max_length=500),
    limit: int = 5,
    namespace: str | None = None,
    services: SessionServices = Depends(services_dep),
    runtime: Runtime = Depends(runtime_dep),
) -> MemorySearchResult:
    result = services.retriever.retrieve(q, namespace=namespace, top_k=limit)
    return MemorySearchResult(
        query=q,
        hits=[
            {
                "source": item.source,
                "ref": item.ref,
                "score": round(item.score, 4),
                "content": item.content[:1000],
                "note": item.note,
            }
            for item in result.items[:limit]
        ],
        embedder=runtime.embedder.id,
        semantic=runtime.embedder.semantic,
    )


@router.delete("/memory/{memory_id}", summary="Revoke a memory item")
def revoke_memory(
    memory_id: str,
    client: Client = Depends(current_client),
    services: SessionServices = Depends(services_dep),
) -> dict:
    memory = LongTermMemory(services.session, client.client_id)
    if not memory.revoke(memory_id):
        raise NotFoundError(f"memory item '{memory_id}' not found")
    record(
        services.session,
        actor=client.client_id,
        action=MEMORY_DELETED,
        resource_type="memory",
        resource_id=memory_id,
    )
    return {"revoked": True, "memory_id": memory_id}


@router.get("/conversations", summary="List conversations")
def list_conversations(
    limit: int = 50,
    offset: int = 0,
    client: Client = Depends(current_client),
    services: SessionServices = Depends(services_dep),
) -> list[dict]:
    from app.memory.short_term import ShortTermMemory

    short_term = ShortTermMemory(services.session, client.client_id)
    return [
        {
            "id": c.id,
            "title": c.title,
            "user_ref": c.user_ref,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }
        for c in short_term.list_conversations(limit=limit, offset=offset)
    ]


@router.get("/conversations/{conversation_id}", summary="One conversation's turns")
def get_conversation(
    conversation_id: str,
    limit: int = 50,
    client: Client = Depends(current_client),
    services: SessionServices = Depends(services_dep),
) -> dict:
    from app.memory.short_term import ShortTermMemory

    short_term = ShortTermMemory(services.session, client.client_id)
    try:
        short_term.get_or_create(conversation_id)
    except PermissionError as exc:
        raise NotFoundError(f"conversation '{conversation_id}' not found") from exc
    return {
        "conversation_id": conversation_id,
        "turns": [t.as_dict() for t in short_term.window(conversation_id, limit=limit)],
    }
