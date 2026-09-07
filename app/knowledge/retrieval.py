"""Knowledge retrieval helpers.

The semantic path lives in :mod:`app.memory.retrieval`, which searches
documents, memory and promoted solutions in one pass. This module holds the
document-specific reads that the API surface needs.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import Document, DocumentChunk
from app.local_ai.prompts import ContextItem
from app.memory.retrieval import Retriever


def search(
    retriever: Retriever, query: str, *, namespace: str | None = None, limit: int = 5
) -> list[ContextItem]:
    """Semantic search restricted to document chunks."""
    result = retriever.retrieve(query, namespace=namespace, top_k=limit, include_solutions=False)
    return [item for item in result.items if item.source == "document"][:limit]


def document_stats(session: Session, client_id: str) -> dict:
    documents, chunks, bytes_total = session.execute(
        select(
            func.count(func.distinct(Document.id)),
            func.coalesce(func.sum(Document.chunk_count), 0),
            func.coalesce(func.sum(Document.size_bytes), 0),
        ).where(Document.client_id == client_id)
    ).one()
    return {
        "documents": int(documents or 0),
        "chunks": int(chunks or 0),
        "bytes": int(bytes_total or 0),
    }


def chunks_for(session: Session, client_id: str, document_id: str, limit: int = 100) -> list[DocumentChunk]:
    stmt = (
        select(DocumentChunk)
        .where(DocumentChunk.client_id == client_id, DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.ordinal)
        .limit(min(limit, 500))
    )
    return list(session.scalars(stmt))
