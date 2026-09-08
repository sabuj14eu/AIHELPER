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


def record_durable(**kwargs) -> None:
    """Append one audit row in its own transaction, committed immediately.

    ``record`` writes into the caller's session, so a refusal audited there is
    lost when that request is rejected before it commits — an authentication
    failure and a rate-limit block are both raised out of the dependency layer,
    and the request session is then rolled back, taking the audit row with it.
    A refusal that is not recorded is the opposite of what an audit trail is
    for, so those refusals are written here instead: a fresh session that
    commits at once and is independent of the request's fate. It never raises —
    losing the request to a logging failure would be worse than losing the log.
    """
    from app.database.session import session_scope

    try:
        with session_scope() as session:
            record(session, **kwargs)
    except Exception:  # pragma: no cover - the audit write must never re-raise
        log.error("durable_audit_failed", action=kwargs.get("action"))


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
