"""Document ingestion pipeline: upload -> extract -> clean -> chunk -> embed -> index."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import DOCUMENT_DELETED, DOCUMENT_INGESTED, record
from app.core.errors import NotFoundError, ValidationError
from app.core.ids import new_id
from app.core.logging import get_logger
from app.database.enums import Classification, DocumentStatus
from app.database.models import Document, DocumentChunk
from app.knowledge.chunking import chunk_text
from app.knowledge.extraction import MIME_BY_EXTENSION, extension_of, extract
from app.memory.retrieval import Retriever

log = get_logger("ingestion")

_MULTISPACE = re.compile(r"[ \t]{2,}")
_MULTINEWLINE = re.compile(r"\n{3,}")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(text: str) -> str:
    text = _CONTROL.sub("", text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _MULTISPACE.sub(" ", text)
    return _MULTINEWLINE.sub("\n\n", text).strip()


@dataclass
class IngestionResult:
    document: Document
    chunks: int
    indexed: int
    duplicate: bool = False

    def as_dict(self) -> dict:
        return {
            "document_id": self.document.id,
            "filename": self.document.filename,
            "status": self.document.status,
            "chunks": self.chunks,
            "indexed": self.indexed,
            "duplicate": self.duplicate,
            "size_bytes": self.document.size_bytes,
        }


class DocumentIngestor:
    def __init__(
        self,
        session: Session,
        client_id: str,
        *,
        retriever: Retriever,
        chunk_size: int = 900,
        chunk_overlap: int = 150,
        max_bytes: int = 20 * 1024 * 1024,
    ):
        self.session = session
        self.client_id = client_id
        self.retriever = retriever
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_bytes = max_bytes

    def ingest(
        self,
        data: bytes,
        filename: str,
        *,
        namespace: str = "default",
        classification: Classification | str = Classification.CONFIDENTIAL,
        title: str | None = None,
        request_id: str | None = None,
        meta: dict | None = None,
    ) -> IngestionResult:
        if len(data) > self.max_bytes:
            raise ValidationError(
                f"file is {len(data)} bytes; the limit is {self.max_bytes}"
            )
        digest = hashlib.sha256(data).hexdigest()

        existing = self.session.scalars(
            select(Document).where(
                Document.client_id == self.client_id, Document.sha256 == digest
            )
        ).first()
        if existing is not None:
            # Re-uploading the same bytes is a no-op, not a second copy.
            return IngestionResult(
                document=existing, chunks=existing.chunk_count, indexed=0, duplicate=True
            )

        extraction = extract(data, filename)  # raises ValidationError on a bad file
        text = clean(extraction.text)
        if not text:
            raise ValidationError("no usable text after cleaning")

        document = Document(
            id=new_id("doc"),
            client_id=self.client_id,
            namespace=namespace,
            filename=filename[:400],
            mime_type=MIME_BY_EXTENSION.get(extension_of(filename), "application/octet-stream"),
            size_bytes=len(data),
            sha256=digest,
            status=DocumentStatus.PROCESSING.value,
            classification=str(Classification(str(classification).upper()).value),
            title=(title or filename)[:400],
            chunk_count=0,
            meta={**(meta or {}), **extraction.meta, "char_count": len(text)},
        )
        self.session.add(document)
        self.session.flush()

        pieces = chunk_text(text, size=self.chunk_size, overlap=self.chunk_overlap)
        rows: list[DocumentChunk] = []
        for piece in pieces:
            rows.append(
                DocumentChunk(
                    id=new_id("chk"),
                    document_id=document.id,
                    client_id=self.client_id,
                    namespace=namespace,
                    ordinal=piece.ordinal,
                    content=piece.content,
                    char_count=piece.char_count,
                    meta={"start": piece.start, "end": piece.end},
                )
            )
        self.session.add_all(rows)
        self.session.flush()

        indexed = 0
        try:
            indexed = self.retriever.index_chunks(rows)
            document.status = DocumentStatus.READY.value
        except Exception as exc:
            # A document whose vectors did not land is not READY. Saying so is
            # the whole point: a silently unsearchable document looks fine in
            # the listing and answers nothing.
            document.status = DocumentStatus.FAILED.value
            document.error = f"indexing failed: {type(exc).__name__}: {exc}"[:1000]
            log.error("chunk_indexing_failed", document_id=document.id, error=type(exc).__name__)

        document.chunk_count = len(rows)
        record(
            self.session,
            actor=self.client_id,
            action=DOCUMENT_INGESTED,
            resource_type="document",
            resource_id=document.id,
            request_id=request_id,
            result="ok" if document.status == DocumentStatus.READY.value else "partial",
            detail={
                "filename": document.filename,
                "bytes": document.size_bytes,
                "chunks": len(rows),
                "indexed": indexed,
                "namespace": namespace,
                "classification": document.classification,
            },
        )
        return IngestionResult(
            document=document, chunks=len(rows), indexed=indexed, duplicate=False
        )

    # ------------------------------------------------------------ management
    def get(self, document_id: str) -> Document:
        document = self.session.get(Document, document_id)
        if document is None or document.client_id != self.client_id:
            raise NotFoundError(f"document '{document_id}' not found")
        return document

    def list(self, *, namespace: str | None = None, limit: int = 50, offset: int = 0) -> list[Document]:
        stmt = select(Document).where(Document.client_id == self.client_id)
        if namespace:
            stmt = stmt.where(Document.namespace == namespace)
        stmt = stmt.order_by(Document.created_at.desc()).limit(min(limit, 200)).offset(offset)
        return list(self.session.scalars(stmt))

    def delete(self, document_id: str, *, request_id: str | None = None) -> bool:
        document = self.get(document_id)
        chunk_ids = [c.id for c in document.chunks]
        self.retriever.unindex_document(document.id, chunk_ids)
        self.session.delete(document)
        record(
            self.session,
            actor=self.client_id,
            action=DOCUMENT_DELETED,
            resource_type="document",
            resource_id=document_id,
            request_id=request_id,
            detail={"chunks": len(chunk_ids)},
        )
        return True
