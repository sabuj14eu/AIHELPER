"""SQLAlchemy models.

Isolation rule: every row that can hold client data carries ``client_id`` and
every query in this codebase filters on it. See docs/security.md.

Append-only rule: ``AuditEvent`` refuses UPDATE and DELETE at the ORM level.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.database.enums import (
    Classification,
    DocumentStatus,
    JobStatus,
    MemoryKind,
    MemoryStatus,
    SolutionStatus,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )


# --------------------------------------------------------------------------
# Clients — one row per application allowed to use the gateway.
# --------------------------------------------------------------------------
class Client(Base, TimestampMixin):
    __tablename__ = "clients"

    client_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    api_key_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    api_key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Permissions. An empty list means "nothing"; None means "the default set".
    allowed_tools: Mapped[list | None] = mapped_column(JSON, default=None)
    allowed_task_types: Mapped[list | None] = mapped_column(JSON, default=None)
    may_escalate: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # The floor a request from this client starts at. The detector can raise a
    # single request above it; nothing can push a request below it.
    default_classification: Mapped[str] = mapped_column(
        String(16), default=Classification.INTERNAL.value, nullable=False
    )
    # The ceiling for what may be sent to an external provider.
    max_external_classification: Mapped[str] = mapped_column(
        String(16), default=Classification.INTERNAL.value, nullable=False
    )
    daily_budget_usd: Mapped[float | None] = mapped_column(Float, default=None)
    rate_limit_per_minute: Mapped[int | None] = mapped_column(Integer, default=None)
    meta: Mapped[dict | None] = mapped_column(JSON, default=dict)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


# --------------------------------------------------------------------------
# Observability
# --------------------------------------------------------------------------
class RequestLog(Base, TimestampMixin):
    __tablename__ = "request_logs"

    request_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    task_type: Mapped[str] = mapped_column(String(32), index=True)
    classification: Mapped[str] = mapped_column(String(16), index=True)
    route: Mapped[str] = mapped_column(String(16), index=True)
    provider: Mapped[str | None] = mapped_column(String(32), index=True)
    model: Mapped[str | None] = mapped_column(String(120))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float | None] = mapped_column(Float, default=None)
    memory_hit: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    tool_used: Mapped[str | None] = mapped_column(String(64))
    escalation_reason: Mapped[str | None] = mapped_column(String(48), index=True)
    escalation_blocked_reason: Mapped[str | None] = mapped_column(String(48), index=True)
    validation_result: Mapped[dict | None] = mapped_column(JSON, default=dict)
    local_attempted: Mapped[bool] = mapped_column(Boolean, default=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    error_code: Mapped[str | None] = mapped_column(String(64))
    # Content is never stored here — only a fingerprint, so requests can be
    # correlated without keeping the message body in the log table.
    question_fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)

    __table_args__ = (Index("ix_request_logs_client_created", "client_id", "created_at"),)


class AuditEvent(Base, TimestampMixin):
    """Append-only. Updates and deletes raise at the ORM level."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(120), index=True)
    actor_type: Mapped[str] = mapped_column(String(32), default="client")
    action: Mapped[str] = mapped_column(String(80), index=True)
    resource_type: Mapped[str | None] = mapped_column(String(64), index=True)
    resource_id: Mapped[str | None] = mapped_column(String(128), index=True)
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    result: Mapped[str] = mapped_column(String(32), default="ok")
    detail: Mapped[dict | None] = mapped_column(JSON, default=dict)


class CostRecord(Base, TimestampMixin):
    """One row per paid-provider call. The billing truth of the system."""

    __tablename__ = "cost_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    client_id: Mapped[str] = mapped_column(String(64), index=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str] = mapped_column(String(120))
    task_type: Mapped[str | None] = mapped_column(String(32), index=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    reason_for_escalation: Mapped[str | None] = mapped_column(String(48), index=True)
    succeeded: Mapped[bool] = mapped_column(Boolean, default=True)


# --------------------------------------------------------------------------
# Memory
# --------------------------------------------------------------------------
class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    user_ref: Mapped[str | None] = mapped_column(String(120), index=True)
    title: Mapped[str | None] = mapped_column(String(300))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.id"
    )


class Message(Base, TimestampMixin):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    client_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    meta: Mapped[dict | None] = mapped_column(JSON, default=dict)
    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class MemoryItem(Base, TimestampMixin):
    """Long-term memory. Nothing is stored without source, confidence and status."""

    __tablename__ = "memory_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    namespace: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), default=MemoryKind.FACT.value, index=True)
    key: Mapped[str | None] = mapped_column(String(200), index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    status: Mapped[str] = mapped_column(String(16), default=MemoryStatus.ACTIVE.value, index=True)
    sensitivity: Mapped[str] = mapped_column(
        String(16), default=Classification.INTERNAL.value, index=True
    )
    owner_ref: Mapped[str | None] = mapped_column(String(120), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    meta: Mapped[dict | None] = mapped_column(JSON, default=dict)

    __table_args__ = (Index("ix_memory_client_ns_status", "client_id", "namespace", "status"),)


class VectorPoint(Base, TimestampMixin):
    """Durable fallback vector store, used when Qdrant is not available.

    Kept in the relational database so that semantic memory survives a restart
    even in the no-Qdrant deployment. Brute-force cosine search; adequate for
    the tens-of-thousands range, not a Qdrant replacement at scale.
    """

    __tablename__ = "vector_points"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    collection: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    client_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    ref_type: Mapped[str] = mapped_column(String(32), index=True)
    ref_id: Mapped[str] = mapped_column(String(64), index=True)
    vector: Mapped[list] = mapped_column(JSON, nullable=False)
    norm: Mapped[float] = mapped_column(Float, default=1.0)
    payload: Mapped[dict | None] = mapped_column(JSON, default=dict)

    __table_args__ = (Index("ix_vector_collection_client", "collection", "client_id"),)


# --------------------------------------------------------------------------
# Learning
# --------------------------------------------------------------------------
class SolutionCandidate(Base, TimestampMixin):
    """A hard case that a paid provider solved.

    Nothing here is trusted until it has been through the promotion pipeline:
    CANDIDATE -> VALIDATED -> PROMOTED. Only PROMOTED rows are offered back to
    the local model as context.
    """

    __tablename__ = "solution_candidates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_question: Mapped[str] = mapped_column(Text, nullable=False)
    task_type: Mapped[str] = mapped_column(String(32), index=True)
    classification: Mapped[str] = mapped_column(
        String(16), default=Classification.INTERNAL.value, index=True
    )
    context: Mapped[dict | None] = mapped_column(JSON, default=dict)
    local_attempt: Mapped[str | None] = mapped_column(Text)
    failure_reason: Mapped[str | None] = mapped_column(String(48), index=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str] = mapped_column(String(120))
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    validation_result: Mapped[dict | None] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(
        String(16), default=SolutionStatus.CANDIDATE.value, index=True
    )
    status_reason: Mapped[str | None] = mapped_column(String(300))
    reproduction: Mapped[dict | None] = mapped_column(JSON, default=dict)
    reuse_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    source_request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        Index("ix_solution_client_status", "client_id", "status"),
        Index("ix_solution_client_fp", "client_id", "fingerprint"),
    )


# --------------------------------------------------------------------------
# Knowledge
# --------------------------------------------------------------------------
class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    namespace: Mapped[str] = mapped_column(String(120), index=True, default="default")
    filename: Mapped[str] = mapped_column(String(400))
    mime_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(
        String(16), default=DocumentStatus.PENDING.value, index=True
    )
    error: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    classification: Mapped[str] = mapped_column(
        String(16), default=Classification.CONFIDENTIAL.value
    )
    title: Mapped[str | None] = mapped_column(String(400))
    meta: Mapped[dict | None] = mapped_column(JSON, default=dict)
    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentChunk.ordinal"
    )

    __table_args__ = (UniqueConstraint("client_id", "sha256", name="uq_doc_client_sha"),)


class DocumentChunk(Base, TimestampMixin):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    client_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    namespace: Mapped[str] = mapped_column(String(120), index=True, default="default")
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    meta: Mapped[dict | None] = mapped_column(JSON, default=dict)
    document: Mapped[Document] = relationship(back_populates="chunks")


# --------------------------------------------------------------------------
# Async jobs
# --------------------------------------------------------------------------
class Job(Base, TimestampMixin):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default=JobStatus.QUEUED.value, index=True)
    payload: Mapped[dict | None] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --------------------------------------------------------------------------
# Append-only enforcement for the audit table.
# --------------------------------------------------------------------------
class AppendOnlyViolation(RuntimeError):
    pass


@event.listens_for(AuditEvent, "before_update", propagate=True)
def _block_audit_update(_mapper, _connection, _target):  # pragma: no cover - guard
    raise AppendOnlyViolation("audit_events is append-only: UPDATE refused")


@event.listens_for(AuditEvent, "before_delete", propagate=True)
def _block_audit_delete(_mapper, _connection, _target):  # pragma: no cover - guard
    raise AppendOnlyViolation("audit_events is append-only: DELETE refused")
