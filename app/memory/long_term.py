"""Long-term memory.

Nothing is written here without: source, timestamp, confidence, status,
sensitivity, owner scope and — where it applies — an expiry. A memory row
without provenance is a rumour, and the write path refuses to create one.

Every read and every write is scoped to a client_id and a namespace, and the
namespace is derived from the authenticated client, never from user input.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.core.ids import new_id
from app.database.enums import Classification, MemoryKind, MemoryStatus
from app.database.models import MemoryItem

MAX_CONTENT_CHARS = 8000


def namespace_for(client_id: str, sub: str | None = None) -> str:
    """`memory/<client>/<sub>` — the namespace shape from the work order."""
    base = f"memory/{client_id}"
    return f"{base}/{sub}" if sub else f"{base}/default"


class LongTermMemory:
    def __init__(self, session: Session, client_id: str):
        self.session = session
        self.client_id = client_id

    # ---------------------------------------------------------------- write
    def write(
        self,
        content: str,
        *,
        source: str,
        confidence: float,
        kind: MemoryKind | str = MemoryKind.FACT,
        sensitivity: Classification | str = Classification.INTERNAL,
        namespace: str | None = None,
        key: str | None = None,
        owner_ref: str | None = None,
        ttl_days: int | None = None,
        meta: dict | None = None,
    ) -> MemoryItem:
        if not content or not content.strip():
            raise ValidationError("memory content may not be empty")
        if not source:
            raise ValidationError("memory requires a source")
        if not 0.0 <= confidence <= 1.0:
            raise ValidationError("confidence must be between 0 and 1")

        expires_at = (
            datetime.now(UTC) + timedelta(days=ttl_days) if ttl_days else None
        )
        item = MemoryItem(
            id=new_id("mem"),
            client_id=self.client_id,
            namespace=namespace or namespace_for(self.client_id),
            kind=str(MemoryKind(kind) if not isinstance(kind, str) else kind),
            key=key,
            content=content.strip()[:MAX_CONTENT_CHARS],
            source=source,
            confidence=float(confidence),
            status=MemoryStatus.ACTIVE.value,
            sensitivity=str(Classification(str(sensitivity).upper()).value),
            owner_ref=owner_ref,
            expires_at=expires_at,
            meta=meta or {},
        )
        self.session.add(item)
        self.session.flush()
        return item

    # ----------------------------------------------------------------- read
    def get(self, memory_id: str) -> MemoryItem | None:
        item = self.session.get(MemoryItem, memory_id)
        if item is None or item.client_id != self.client_id:
            return None
        return item

    def list(
        self,
        *,
        namespace: str | None = None,
        kind: str | None = None,
        status: str | None = MemoryStatus.ACTIVE.value,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MemoryItem]:
        stmt = select(MemoryItem).where(MemoryItem.client_id == self.client_id)
        if namespace:
            stmt = stmt.where(MemoryItem.namespace == namespace)
        if kind:
            stmt = stmt.where(MemoryItem.kind == kind)
        if status:
            stmt = stmt.where(MemoryItem.status == status)
        stmt = stmt.order_by(MemoryItem.created_at.desc()).limit(min(limit, 500)).offset(offset)
        return [m for m in self.session.scalars(stmt) if not self._is_stale(m)]

    def active_ids(self) -> set[str]:
        return {m.id for m in self.list(limit=500)}

    # ------------------------------------------------------------ lifecycle
    def _is_stale(self, item: MemoryItem) -> bool:
        if item.expires_at is None:
            return False
        expires = item.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        return expires <= datetime.now(UTC)

    # Sessions run with autoflush off, so every mutating method flushes
    # explicitly. Without this a read in the same request sees the pre-change
    # row — a revoked memory item would still be returned by list().
    def expire_due(self) -> int:
        """Mark expired rows EXPIRED. Content is kept for audit, not for reads."""
        now = datetime.now(UTC)
        stmt = select(MemoryItem).where(
            MemoryItem.client_id == self.client_id,
            MemoryItem.status == MemoryStatus.ACTIVE.value,
            MemoryItem.expires_at.is_not(None),
            MemoryItem.expires_at <= now,
        )
        count = 0
        for item in self.session.scalars(stmt):
            item.status = MemoryStatus.EXPIRED.value
            count += 1
        self.session.flush()
        return count

    def revoke(self, memory_id: str) -> bool:
        item = self.get(memory_id)
        if item is None:
            return False
        item.status = MemoryStatus.REVOKED.value
        self.session.flush()
        return True

    def delete(self, memory_id: str) -> bool:
        item = self.get(memory_id)
        if item is None:
            return False
        self.session.delete(item)
        self.session.flush()
        return True
