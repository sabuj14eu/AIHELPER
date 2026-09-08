"""Document upload, listing and deletion. Everything is client-scoped."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import current_client, services_dep
from app.api.schemas import DocumentOut, DocumentUploadResponse
from app.core.errors import ValidationError
from app.database.enums import Classification
from app.database.models import Client
from app.knowledge.extraction import SUPPORTED_EXTENSIONS
from app.knowledge.retrieval import chunks_for, document_stats
from app.runtime import SessionServices

router = APIRouter(prefix="/api/v1", tags=["documents"])


@router.post("/documents", response_model=DocumentUploadResponse, summary="Upload a document")
async def upload_document(
    file: UploadFile = File(...),
    namespace: str = Form(default="default"),
    classification: str = Form(default="CONFIDENTIAL"),
    title: str | None = Form(default=None),
    client: Client = Depends(current_client),
    services: SessionServices = Depends(services_dep),
) -> DocumentUploadResponse:
    """Extract, chunk, embed and index one file.

    A file whose vectors do not land is reported as FAILED rather than READY:
    a document that looks present and answers nothing is worse than a visible
    error.
    """
    data = await file.read()
    if not data:
        raise ValidationError("the uploaded file is empty")
    # A caller-supplied classification is validated here, at the boundary, so a
    # bad value is a 422 the caller can fix rather than an opaque 500.
    try:
        Classification(classification.upper())
    except ValueError as exc:
        allowed = ", ".join(c.value for c in Classification)
        raise ValidationError(
            f"'{classification}' is not a valid classification; expected one of {allowed}"
        ) from exc
    result = services.ingestor.ingest(
        data,
        file.filename or "upload",
        namespace=namespace,
        classification=classification,
        title=title,
    )
    return DocumentUploadResponse(
        document_id=result.document.id,
        filename=result.document.filename,
        status=result.document.status,
        chunks=result.chunks,
        indexed=result.indexed,
        duplicate=result.duplicate,
        size_bytes=result.document.size_bytes,
    )


@router.get("/documents", response_model=list[DocumentOut], summary="List documents")
def list_documents(
    namespace: str | None = None,
    limit: int = 50,
    offset: int = 0,
    services: SessionServices = Depends(services_dep),
) -> list[DocumentOut]:
    return [
        DocumentOut(
            id=d.id,
            filename=d.filename,
            namespace=d.namespace,
            mime_type=d.mime_type,
            size_bytes=d.size_bytes,
            status=d.status,
            chunk_count=d.chunk_count,
            classification=d.classification,
            error=d.error,
            created_at=d.created_at,
        )
        for d in services.ingestor.list(namespace=namespace, limit=limit, offset=offset)
    ]


@router.get("/documents/formats", summary="Supported upload formats")
def supported_formats(_client: Client = Depends(current_client)) -> dict:
    """Requires a key like everything else under /api/v1.

    It discloses only a static list of extensions, but "harmless" is not the
    test — consistency is. An endpoint that is public by omission rather than
    by decision is the kind of thing that gets copied.
    """
    return {"extensions": sorted(SUPPORTED_EXTENSIONS)}


@router.get("/documents/stats", summary="Document totals for this client")
def stats(
    client: Client = Depends(current_client),
    services: SessionServices = Depends(services_dep),
) -> dict:
    return document_stats(services.session, client.client_id)


@router.get("/documents/{document_id}", response_model=DocumentOut, summary="One document")
def get_document(
    document_id: str,
    services: SessionServices = Depends(services_dep),
) -> DocumentOut:
    d = services.ingestor.get(document_id)
    return DocumentOut(
        id=d.id,
        filename=d.filename,
        namespace=d.namespace,
        mime_type=d.mime_type,
        size_bytes=d.size_bytes,
        status=d.status,
        chunk_count=d.chunk_count,
        classification=d.classification,
        error=d.error,
        created_at=d.created_at,
    )


@router.get("/documents/{document_id}/chunks", summary="A document's chunks")
def get_chunks(
    document_id: str,
    limit: int = 100,
    client: Client = Depends(current_client),
    services: SessionServices = Depends(services_dep),
) -> list[dict]:
    services.ingestor.get(document_id)  # raises if it is not this client's
    return [
        {"id": c.id, "ordinal": c.ordinal, "char_count": c.char_count, "content": c.content}
        for c in chunks_for(services.session, client.client_id, document_id, limit=limit)
    ]


@router.delete("/documents/{document_id}", summary="Delete a document and its vectors")
def delete_document(
    document_id: str,
    services: SessionServices = Depends(services_dep),
) -> dict:
    services.ingestor.delete(document_id)
    return {"deleted": True, "document_id": document_id}
