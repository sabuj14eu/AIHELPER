"""FastAPI dependencies: identity, permissions, rate limiting, services."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import AgentSpec, build_agent_registry
from app.core.audit import AUTH_FAILURE, AUTH_SUCCESS, RATE_LIMITED, record, record_durable
from app.core.config import Settings, get_settings
from app.core.errors import AuthenticationError, PermissionDeniedError, RateLimitedError
from app.core.logging import client_id_var, get_logger
from app.core.security import parse_api_key, verify_api_key, verify_session_token
from app.database.models import Client
from app.database.session import get_db
from app.runtime import Runtime, SessionServices, get_runtime

log = get_logger("api.deps")
AGENTS = build_agent_registry()


def settings_dep(request: Request) -> Settings:
    """The settings this app instance was built with.

    Reading them off ``app.state`` rather than the module-level cache matters:
    a test (or a second app in one process) configures its own Settings, and a
    dependency that quietly used the global cache would apply a different
    budget, a different privacy policy and a different admin credential than
    the app it is serving.
    """
    configured = getattr(request.app.state, "settings", None)
    return configured or get_settings()


def db_dep() -> Iterator[Session]:
    yield from get_db()


def runtime_dep(request: Request) -> Runtime:
    runtime = getattr(request.app.state, "runtime", None)
    return runtime or get_runtime()


def _limiter(request: Request):
    return request.app.state.limiter


def current_client(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(db_dep),
    settings: Settings = Depends(settings_dep),
) -> Client:
    """Authenticate an API key and apply that client's rate limit.

    Failures are deliberately uniform: an unknown key, a wrong secret and a
    disabled client all produce the same message, so the endpoint cannot be
    used to enumerate valid client ids.
    """
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif x_api_key:
        token = x_api_key.strip()

    if not token:
        raise AuthenticationError("an API key is required")

    key_id = parse_api_key(token)
    if not key_id:
        # Committed in its own transaction: this request is about to be
        # rejected, and the request session is rolled back on the way out,
        # which would otherwise erase the record of the refusal.
        record_durable(actor="unknown", action=AUTH_FAILURE, result="failed", actor_type="anonymous",
                       detail={"reason": "malformed key"})
        raise AuthenticationError("invalid API key")

    client = db.scalars(select(Client).where(Client.api_key_id == key_id)).first()
    if (
        client is None
        or not verify_api_key(token, client.api_key_hash)
        or not client.enabled
        or client.revoked_at is not None
    ):
        record_durable(
            actor=key_id,
            action=AUTH_FAILURE,
            result="failed",
            actor_type="anonymous",
            detail={"reason": "unknown, revoked or disabled key"},
        )
        raise AuthenticationError("invalid API key")

    decision = _limiter(request).check(
        client.client_id, rate_override=client.rate_limit_per_minute
    )
    if not decision.allowed:
        record_durable(
            actor=client.client_id,
            action=RATE_LIMITED,
            result="blocked",
            detail={"retry_after": decision.retry_after, "limit": decision.limit},
        )
        raise RateLimitedError(
            f"rate limit exceeded; retry in {decision.retry_after:.0f}s",
            detail={"retry_after": decision.retry_after, "limit": decision.limit},
        )

    client_id_var.set(client.client_id)
    request.state.client_id = client.client_id
    record(db, actor=client.client_id, action=AUTH_SUCCESS, detail={"path": request.url.path})
    return client


def admin_client(client: Client = Depends(current_client)) -> Client:
    if not client.is_admin:
        raise PermissionDeniedError("this endpoint requires an administrator key")
    return client


def admin_session(
    request: Request, settings: Settings = Depends(settings_dep)
) -> dict:
    """Admin dashboard session, from the signed cookie."""
    token = request.cookies.get("ai_helper_admin")
    payload = verify_session_token(token or "", settings.AUTH_SECRET)
    if payload is None or payload.get("role") != "admin":
        raise AuthenticationError("administrator sign-in required")
    return payload


def services_dep(
    client: Client = Depends(current_client),
    db: Session = Depends(db_dep),
    runtime: Runtime = Depends(runtime_dep),
) -> SessionServices:
    return runtime.for_session(db, client.client_id)


def resolve_agent(name: str | None) -> AgentSpec | None:
    if not name:
        return None
    spec = AGENTS.get(name)
    if spec is None:
        raise PermissionDeniedError(f"unknown or disabled agent '{name}'")
    return spec
