"""Audit log writer.

Every security-relevant and money-relevant action goes through here. The table
is append-only; this module is the only intended writer.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger, scrub_text
from app.database.models import AuditEvent

log = get_logger("audit")

# Actions worth naming so they are greppable and consistent.
CLIENT_CREATED = "client.created"
CLIENT_REVOKED = "client.revoked"
CLIENT_UPDATED = "client.updated"
AUTH_SUCCESS = "auth.success"
AUTH_FAILURE = "auth.failure"
RATE_LIMITED = "auth.rate_limited"
CHAT_REQUEST = "chat.request"
TOOL_INVOKED = "tool.invoked"
EXTERNAL_CALL = "provider.external_call"
EXTERNAL_BLOCKED = "provider.external_blocked"
BUDGET_TRIPPED = "cost.budget_tripped"
PRIVACY_BLOCK = "privacy.escalation_blocked"
REDACTION_APPLIED = "privacy.redaction_applied"
SOLUTION_CAPTURED = "learning.solution_captured"
SOLUTION_VALIDATED = "learning.solution_validated"
SOLUTION_PROMOTED = "learning.solution_promoted"
SOLUTION_REJECTED = "learning.solution_rejected"
MEMORY_WRITTEN = "memory.written"
MEMORY_DELETED = "memory.deleted"
DOCUMENT_INGESTED = "document.ingested"
DOCUMENT_DELETED = "document.deleted"
ADMIN_LOGIN = "admin.login"
ADMIN_ACTION = "admin.action"


def record(
    session: Session,
    *,
    actor: str,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    request_id: str | None = None,
    result: str = "ok",
    actor_type: str = "client",
    detail: dict | None = None,
) -> AuditEvent:
    """Append one audit row. Never raises for a detail-serialisation problem."""
    safe_detail = _safe(detail or {})
    event = AuditEvent(
        actor=actor,
        actor_type=actor_type,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=request_id,
        result=result,
        detail=safe_detail,
    )
    session.add(event)
    log.info("audit", action=action, actor=actor, result=result, resource_id=resource_id)
    return event


def _safe(detail: dict) -> dict:
    """Audit detail records metadata, not content. Long strings are truncated."""
    out: dict = {}
    for key, value in detail.items():
        if isinstance(value, str):
            out[key] = scrub_text(value)[:500]
        elif isinstance(value, (int, float, bool)) or value is None:
            out[key] = value
        elif isinstance(value, dict):
            out[key] = _safe(value)
        elif isinstance(value, (list, tuple)):
            out[key] = [_safe(v) if isinstance(v, dict) else str(v)[:200] for v in value][:25]
        else:
            out[key] = str(value)[:200]
    return out


def search(
    session: Session,
    *,
    actor: str | None = None,
    action: str | None = None,
    request_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditEvent]:
    stmt = select(AuditEvent).order_by(AuditEvent.id.desc())
    if actor:
        stmt = stmt.where(AuditEvent.actor == actor)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if request_id:
        stmt = stmt.where(AuditEvent.request_id == request_id)
    return list(session.scalars(stmt.limit(min(limit, 500)).offset(offset)))
