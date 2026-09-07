"""Document and memory lookup tools.

These are the only tools that touch stored client data, and both of them are
hard-scoped to the calling client's ``client_id``. The client_id is supplied by
the gateway from the authenticated identity — it is never a tool argument, so
a model cannot ask for another client's namespace.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.enums import MemoryStatus, RiskLevel
from app.database.models import Document, DocumentChunk, MemoryItem
from app.tools.registry import (
    PERM_READ_DOCUMENTS,
    PERM_READ_MEMORY,
    ToolResult,
    ToolSpec,
)


def list_documents(
    limit: int = 20,
    namespace: str | None = None,
    *,
    session: Session | None = None,
    client_id: str | None = None,
    **_ignored,
) -> ToolResult:
    if session is None or not client_id:
        return ToolResult(ok=False, error="document tools require an authenticated session")
    stmt = (
        select(Document)
        .where(Document.client_id == client_id)
        .order_by(Document.created_at.desc())
        .limit(min(limit, 100))
    )
    if namespace:
        stmt = stmt.where(Document.namespace == namespace)
    rows = list(session.scalars(stmt))
    listing = [
        {
            "id": d.id,
            "filename": d.filename,
            "namespace": d.namespace,
            "status": d.status,
            "chunks": d.chunk_count,
            "size_bytes": d.size_bytes,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in rows
    ]
    display = "\n".join(f"{d['id']}  {d['filename']}  ({d['chunks']} chunks)" for d in listing)
    return ToolResult(
        ok=True,
        value=listing,
        display=display or "no documents",
        meta={"count": len(listing), "client_id": client_id},
    )


def search_documents(
    query: str,
    limit: int = 5,
    namespace: str | None = None,
    *,
    session: Session | None = None,
    client_id: str | None = None,
    **_ignored,
) -> ToolResult:
    """Literal substring search over this client's chunks.

    Deliberately lexical: it is the cheap, exact complement to semantic search
    and it is what you want when the user quotes an invoice number.
    """
    if session is None or not client_id:
        return ToolResult(ok=False, error="document tools require an authenticated session")
    needle = (query or "").strip()
    if len(needle) < 2:
        return ToolResult(ok=False, error="query must be at least 2 characters")
    stmt = (
        select(DocumentChunk)
        .where(
            DocumentChunk.client_id == client_id,
            DocumentChunk.content.icontains(needle),
        )
        .order_by(DocumentChunk.document_id, DocumentChunk.ordinal)
        .limit(min(limit, 25))
    )
    if namespace:
        stmt = stmt.where(DocumentChunk.namespace == namespace)
    chunks = list(session.scalars(stmt))
    hits = [
        {
            "chunk_id": c.id,
            "document_id": c.document_id,
            "ordinal": c.ordinal,
            "excerpt": _excerpt(c.content, needle),
        }
        for c in chunks
    ]
    display = "\n\n".join(f"[{h['document_id']}#{h['ordinal']}] {h['excerpt']}" for h in hits)
    return ToolResult(
        ok=True,
        value=hits,
        display=display or "no matches",
        meta={"count": len(hits), "query_length": len(needle)},
    )


def _excerpt(content: str, needle: str, window: int = 220) -> str:
    index = content.lower().find(needle.lower())
    if index == -1:
        return content[:window]
    start = max(0, index - window // 2)
    end = min(len(content), index + len(needle) + window // 2)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(content) else ""
    return f"{prefix}{content[start:end]}{suffix}"


def search_memory(
    query: str,
    limit: int = 5,
    *,
    session: Session | None = None,
    client_id: str | None = None,
    **_ignored,
) -> ToolResult:
    if session is None or not client_id:
        return ToolResult(ok=False, error="memory tools require an authenticated session")
    needle = (query or "").strip()
    if len(needle) < 2:
        return ToolResult(ok=False, error="query must be at least 2 characters")
    stmt = (
        select(MemoryItem)
        .where(
            MemoryItem.client_id == client_id,
            MemoryItem.status == MemoryStatus.ACTIVE.value,
            MemoryItem.content.icontains(needle),
        )
        .order_by(MemoryItem.confidence.desc(), MemoryItem.created_at.desc())
        .limit(min(limit, 25))
    )
    items = list(session.scalars(stmt))
    hits = [
        {
            "id": m.id,
            "kind": m.kind,
            "content": m.content[:600],
            "source": m.source,
            "confidence": m.confidence,
        }
        for m in items
    ]
    display = "\n".join(f"[{h['kind']}:{h['id']}] {h['content'][:200]}" for h in hits)
    return ToolResult(ok=True, value=hits, display=display or "no matches", meta={"count": len(hits)})


LIST_SPEC = ToolSpec(
    name="document_list",
    description="List the documents this client has uploaded, newest first.",
    permissions={PERM_READ_DOCUMENTS},
    input_schema={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            "namespace": {"type": "string", "maxLength": 120},
        },
        "additionalProperties": False,
    },
    output_schema={"type": "object", "properties": {"value": {"type": "array"}}},
    risk=RiskLevel.LOW,
    handler=list_documents,
    answers_directly=False,
)

SEARCH_SPEC = ToolSpec(
    name="document_search",
    description=(
        "Exact substring search across this client's document chunks. Use it for quoted "
        "phrases, invoice numbers and identifiers, where semantic search is the wrong tool."
    ),
    permissions={PERM_READ_DOCUMENTS},
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "maxLength": 500},
            "limit": {"type": "integer", "minimum": 1, "maximum": 25},
            "namespace": {"type": "string", "maxLength": 120},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    output_schema={"type": "object", "properties": {"value": {"type": "array"}}},
    risk=RiskLevel.LOW,
    handler=search_documents,
    answers_directly=False,
)

MEMORY_SPEC = ToolSpec(
    name="memory_search",
    description="Search this client's stored long-term memory items by substring.",
    permissions={PERM_READ_MEMORY},
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "maxLength": 500},
            "limit": {"type": "integer", "minimum": 1, "maximum": 25},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    output_schema={"type": "object", "properties": {"value": {"type": "array"}}},
    risk=RiskLevel.LOW,
    handler=search_memory,
    answers_directly=False,
)
