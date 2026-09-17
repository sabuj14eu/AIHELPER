"""Admin: client management, the audit trail, and the dashboard.

Two ways in, on purpose:

* an **admin API key** for machine access (`/api/v1/admin/...`);
* a **signed session cookie** for the browser dashboard (`/admin/...`), issued
  from a username and a scrypt password hash held in configuration.

The dashboard is read-mostly. The only writes are creating and revoking client
keys, and promoting or rejecting a learned solution — each one audited with
its actor.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import __version__
from app.api.deps import (
    AGENTS,
    admin_client,
    admin_session,
    db_dep,
    resolve_agent,
    resolve_agent_for,
    runtime_dep,
    settings_dep,
)
from app.core import audit
from app.core.config import Settings
from app.core.errors import (
    AuthenticationError,
    NotFoundError,
    ProviderUnavailableError,
    RateLimitedError,
    ValidationError,
)
from app.core.security import create_session_token, generate_api_key, verify_password
from app.cost.analytics import fallback_report, recent_requests, usage_summary
from app.cost.tracker import CostTracker
from app.database.enums import Classification, SolutionStatus
from app.database.models import Client
from app.runtime import Runtime

api_router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
ui_router = APIRouter(prefix="/admin", tags=["admin-ui"], include_in_schema=False)


# ============================================================== admin API
@api_router.get("/clients", summary="List clients")
def list_clients(_admin: Client = Depends(admin_client), db: Session = Depends(db_dep)) -> list[dict]:
    return [_client_dict(c) for c in db.scalars(select(Client).order_by(Client.created_at))]


@api_router.post("/clients", status_code=201, summary="Create a client and issue its key")
def create_client(
    client_id: str,
    name: str | None = None,
    may_escalate: bool = True,
    max_external_classification: str = Classification.INTERNAL.value,
    default_classification: str = Classification.INTERNAL.value,
    daily_budget_usd: float | None = None,
    is_admin: bool = False,
    admin: Client = Depends(admin_client),
    db: Session = Depends(db_dep),
) -> dict:
    """The plaintext key is returned exactly once, here, and never stored."""
    if db.get(Client, client_id) is not None:
        raise ValidationError(f"client '{client_id}' already exists")
    key = generate_api_key()
    client = Client(
        client_id=client_id,
        name=name or client_id,
        api_key_id=key.key_id,
        api_key_hash=key.hashed,
        may_escalate=may_escalate,
        max_external_classification=Classification(max_external_classification.upper()).value,
        default_classification=Classification(default_classification.upper()).value,
        daily_budget_usd=daily_budget_usd,
        is_admin=is_admin,
    )
    db.add(client)
    audit.record(
        db,
        actor=admin.client_id,
        action=audit.CLIENT_CREATED,
        resource_type="client",
        resource_id=client_id,
        actor_type="admin",
        detail={"is_admin": is_admin, "may_escalate": may_escalate},
    )
    return {
        **_client_dict(client),
        "api_key": key.plaintext,
        "warning": "this key is shown once and cannot be recovered — store it now",
    }


@api_router.post("/clients/{client_id}/revoke", summary="Revoke a client's key")
def revoke_client(
    client_id: str, admin: Client = Depends(admin_client), db: Session = Depends(db_dep)
) -> dict:
    client = db.get(Client, client_id)
    if client is None:
        raise ValidationError(f"client '{client_id}' not found")
    client.enabled = False
    client.revoked_at = datetime.now(UTC)
    audit.record(
        db,
        actor=admin.client_id,
        action=audit.CLIENT_REVOKED,
        resource_type="client",
        resource_id=client_id,
        actor_type="admin",
    )
    return {"revoked": True, "client_id": client_id}


@api_router.get("/audit", summary="Search the audit trail")
def search_audit(
    actor: str | None = None,
    action: str | None = None,
    request_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    _admin: Client = Depends(admin_client),
    db: Session = Depends(db_dep),
) -> list[dict]:
    return [
        {
            "id": e.id,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "actor": e.actor,
            "actor_type": e.actor_type,
            "action": e.action,
            "resource_type": e.resource_type,
            "resource_id": e.resource_id,
            "request_id": e.request_id,
            "result": e.result,
            "detail": e.detail,
        }
        for e in audit.search(
            db, actor=actor, action=action, request_id=request_id, limit=limit, offset=offset
        )
    ]


@api_router.get("/overview", summary="Everything the dashboard shows, as JSON")
def overview(
    days: int = 30,
    _admin: Client = Depends(admin_client),
    db: Session = Depends(db_dep),
    runtime: Runtime = Depends(runtime_dep),
    settings: Settings = Depends(settings_dep),
) -> dict:
    return _overview_data(db, runtime, settings, days=days)


def _client_dict(client: Client) -> dict:
    return {
        "client_id": client.client_id,
        "name": client.name,
        "enabled": client.enabled,
        "is_admin": client.is_admin,
        "may_escalate": client.may_escalate,
        "default_classification": client.default_classification,
        "max_external_classification": client.max_external_classification,
        "daily_budget_usd": client.daily_budget_usd,
        "allowed_tools": client.allowed_tools,
        "rate_limit_per_minute": client.rate_limit_per_minute,
        "created_at": client.created_at.isoformat() if client.created_at else None,
        "revoked_at": client.revoked_at.isoformat() if client.revoked_at else None,
    }


def _overview_data(db: Session, runtime: Runtime, settings: Settings, *, days: int = 30) -> dict:
    cost = CostTracker(db, settings)
    return {
        "version": __version__,
        "environment": settings.ENVIRONMENT,
        "usage": usage_summary(db, days=days),
        "spend": cost.summary().as_dict(),
        "by_provider": cost.by_provider(days=days),
        "by_reason": cost.by_escalation_reason(days=days),
        "providers": [h.as_dict() for h in runtime.providers.health()],
        "runtime": {
            "embedder": runtime.embedder.id,
            "embedder_semantic": runtime.embedder.semantic,
            "vector_backend": runtime.vector_backend,
            "thresholds": runtime.thresholds.as_dict(),
            "tools": runtime.tools.names(),
        },
        "budgets": {
            "daily": settings.AI_DAILY_API_BUDGET,
            "monthly": settings.AI_MONTHLY_API_BUDGET,
            "per_request_cap": settings.AI_MAX_COST_PER_REQUEST,
            "escalation_enabled": settings.ESCALATION_ENABLED,
            "external_allowed": sorted(settings.external_allowed),
        },
        "clients": [_client_dict(c) for c in db.scalars(select(Client))],
        "fallbacks": fallback_report(db, limit=25),
        "recent": [
            {
                "request_id": r.request_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "client_id": r.client_id,
                "route": r.route,
                "task_type": r.task_type,
                "provider": r.provider,
                "cost_usd": r.cost_usd,
                "confidence": r.confidence,
                "memory_hit": r.memory_hit,
                "escalation_reason": r.escalation_reason,
                "success": r.success,
            }
            for r in recent_requests(db, limit=25)
        ],
    }


# =============================================================== dashboard
@ui_router.get("/login", response_class=HTMLResponse)
def login_form(request: Request) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request, "admin/login.html", {"error": None}
    )


@ui_router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    settings: Settings = Depends(settings_dep),
    db: Session = Depends(db_dep),
):
    if not settings.ADMIN_PASSWORD_HASH:
        return request.app.state.templates.TemplateResponse(
            request,
            "admin/login.html",
            {
                "error": (
                    "No administrator password is configured. Set ADMIN_PASSWORD_HASH — "
                    "generate one with: python -m app.cli hash-password"
                )
            },
            status_code=503,
        )
    if username != settings.ADMIN_USERNAME or not verify_password(
        password, settings.ADMIN_PASSWORD_HASH
    ):
        audit.record(
            db,
            actor=username[:60],
            action=audit.AUTH_FAILURE,
            actor_type="admin",
            result="failed",
            detail={"surface": "dashboard"},
        )
        return request.app.state.templates.TemplateResponse(
            request, "admin/login.html", {"error": "Incorrect username or password."}, status_code=401
        )

    token = create_session_token(username, settings.AUTH_SECRET, settings.SESSION_TTL_MINUTES)
    audit.record(db, actor=username, action=audit.ADMIN_LOGIN, actor_type="admin")
    response = RedirectResponse(url="/admin", status_code=303)
    response.set_cookie(
        "ai_helper_admin",
        token,
        httponly=True,
        samesite="lax",
        secure=settings.ENVIRONMENT == "production",
        max_age=settings.SESSION_TTL_MINUTES * 60,
    )
    return response


@ui_router.post("/logout")
def logout(response: Response):
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie("ai_helper_admin")
    return response


@ui_router.get("", response_class=HTMLResponse)
@ui_router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    days: int = 30,
    session: dict = Depends(admin_session),
    db: Session = Depends(db_dep),
    runtime: Runtime = Depends(runtime_dep),
    settings: Settings = Depends(settings_dep),
) -> HTMLResponse:
    data = _overview_data(db, runtime, settings, days=days)
    return request.app.state.templates.TemplateResponse(
        request, "admin/dashboard.html", {"data": data, "user": session.get("sub"), "days": days}
    )


@ui_router.get("/audit", response_class=HTMLResponse)
def audit_page(
    request: Request,
    actor: str | None = None,
    action: str | None = None,
    request_id: str | None = None,
    limit: int = 100,
    session: dict = Depends(admin_session),
    db: Session = Depends(db_dep),
) -> HTMLResponse:
    events = audit.search(
        db, actor=actor, action=action, request_id=request_id, limit=limit
    )
    return request.app.state.templates.TemplateResponse(
        request,
        "admin/audit.html",
        {
            "events": events,
            "user": session.get("sub"),
            "filters": {"actor": actor or "", "action": action or "", "request_id": request_id or ""},
        },
    )


@ui_router.get("/solutions", response_class=HTMLResponse)
def solutions_page(
    request: Request,
    status: str | None = None,
    origin: str | None = None,
    session: dict = Depends(admin_session),
    db: Session = Depends(db_dep),
) -> HTMLResponse:
    from app.database.models import SolutionCandidate
    from app.learning.origin import LABELS, SolutionOrigin, origin_of

    stmt = select(SolutionCandidate).order_by(SolutionCandidate.created_at.desc()).limit(200)
    if status:
        stmt = stmt.where(SolutionCandidate.status == status)
    rows = list(db.scalars(stmt))
    # Filtering on origin happens here rather than in the query because origin
    # is derived from `provider` rather than stored -- and the list is capped
    # at 200 rows, so there is nothing to gain by pushing it down.
    if origin:
        rows = [r for r in rows if origin_of(r.provider).value == origin]
    return request.app.state.templates.TemplateResponse(
        request,
        "admin/solutions.html",
        {
            "solutions": rows,
            "origin_of": lambda row: origin_of(row.provider).value,
            "origin_labels": {o.value: LABELS[o] for o in SolutionOrigin},
            "user": session.get("sub"),
            "status": status or "",
            "origin": origin or "",
            "statuses": [s.value for s in SolutionStatus],
            "origins": [o.value for o in SolutionOrigin],
        },
    )


@ui_router.post("/solutions/{solution_id}/{action}")
def solution_action(
    solution_id: str,
    action: str,
    session: dict = Depends(admin_session),
    db: Session = Depends(db_dep),
    runtime: Runtime = Depends(runtime_dep),
    settings: Settings = Depends(settings_dep),
):
    from app.database.models import SolutionCandidate
    from app.learning.promotion import PromotionPipeline

    solution = db.get(SolutionCandidate, solution_id)
    if solution is None:
        raise AuthenticationError("solution not found")
    pipeline = PromotionPipeline(
        db,
        solution.client_id,
        settings=settings,
        local_provider=runtime.providers.local,
        retriever=runtime.retriever(db, solution.client_id),
    )
    if action == "promote":
        pipeline.process(solution)
    elif action == "reject":
        pipeline.reject(solution, f"rejected by {session.get('sub')} in the dashboard")
    audit.record(
        db,
        actor=str(session.get("sub")),
        action=audit.ADMIN_ACTION,
        actor_type="admin",
        resource_type="solution",
        resource_id=solution_id,
        detail={"action": action},
    )
    return RedirectResponse(url="/admin/solutions", status_code=303)


@ui_router.get("/clients", response_class=HTMLResponse)
def clients_page(
    request: Request,
    session: dict = Depends(admin_session),
    db: Session = Depends(db_dep),
) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request,
        "admin/clients.html",
        {
            "clients": [_client_dict(c) for c in db.scalars(select(Client).order_by(Client.created_at))],
            "user": session.get("sub"),
            "new_key": request.query_params.get("key"),
            "new_client": request.query_params.get("client"),
        },
    )


@ui_router.post("/clients")
def create_client_ui(
    client_id: str = Form(...),
    name: str = Form(default=""),
    may_escalate: bool = Form(default=False),
    session: dict = Depends(admin_session),
    db: Session = Depends(db_dep),
):
    if db.get(Client, client_id) is not None:
        return RedirectResponse(url="/admin/clients", status_code=303)
    key = generate_api_key()
    db.add(
        Client(
            client_id=client_id,
            name=name or client_id,
            api_key_id=key.key_id,
            api_key_hash=key.hashed,
            may_escalate=may_escalate,
        )
    )
    audit.record(
        db,
        actor=str(session.get("sub")),
        action=audit.CLIENT_CREATED,
        actor_type="admin",
        resource_type="client",
        resource_id=client_id,
        detail={"may_escalate": may_escalate},
    )
    # The key travels once, in the redirect, and is never persisted anywhere.
    return RedirectResponse(
        url=f"/admin/clients?key={key.plaintext}&client={client_id}", status_code=303
    )


# ============================================================ Brother chat
# The dashboard's own conversation with the personal assistant. It is not a
# second path: the admin session only *identifies* the operator; the request
# runs as the personal client, through the same GatewayRouter, with the same
# validation, budgets, privacy gate and audit rows as a call to /api/v1/chat.
class TeachBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=3, max_length=4000)
    answer: str = Field(min_length=3, max_length=8000)
    evidence: str = Field(default="", max_length=500)


class AdminChatBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=32_000)
    agent: str | None = Field(default=None, max_length=64)
    conversation_id: str | None = Field(default=None, max_length=64)


class ResearchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=3, max_length=500)


def _personal_client(db: Session, settings: Settings) -> Client | None:
    client = db.get(Client, settings.PERSONAL_CLIENT_ID)
    if client is None or not client.enabled or client.revoked_at is not None:
        return None
    return client


def _knowledge_summary(db: Session, runtime: Runtime, client: Client | None) -> dict:
    from app.database.enums import SolutionStatus
    from app.knowledge.pack import KnowledgePackLoader
    from app.learning.origin import SolutionOrigin
    from app.learning.solution_store import SolutionStore

    empty = {
        "documents": 0,
        "by_domain": {},
        "solutions": {status.value: 0 for status in SolutionStatus},
        "by_origin": {origin.value: {"total": 0} for origin in SolutionOrigin},
    }
    if client is None:
        return empty
    services = runtime.for_session(db, client.client_id)
    summary = KnowledgePackLoader(db, client.client_id, ingestor=services.ingestor).status()
    # Beside the status counts on purpose: "229 promoted" and "229 of them
    # written by hand" are both true, and only the pair of them is honest.
    summary["by_origin"] = SolutionStore(db, client.client_id).counts_by_origin()
    return summary


@ui_router.get("/chat", response_class=HTMLResponse)
def chat_page(
    request: Request,
    session: dict = Depends(admin_session),
    db: Session = Depends(db_dep),
    runtime: Runtime = Depends(runtime_dep),
    settings: Settings = Depends(settings_dep),
) -> HTMLResponse:
    client = _personal_client(db, settings)
    agents = [a.as_dict() | {"description": a.description} for a in AGENTS.list() if a.enabled]
    local = runtime.providers.local
    local_health = local.health() if local is not None else None
    return request.app.state.templates.TemplateResponse(
        request,
        "admin/chat.html",
        {
            "user": session.get("sub"),
            "client_id": settings.PERSONAL_CLIENT_ID,
            "client_exists": client is not None,
            "knowledge": _knowledge_summary(db, runtime, client),
            "agents": agents,
            "agents_json": json.dumps(agents),
            "default_agent": settings.PERSONAL_AGENT if AGENTS.get(settings.PERSONAL_AGENT) else "general",
            "embedder": runtime.embedder.id,
            "embedder_semantic": runtime.embedder.semantic,
            "local_available": bool(local_health and local_health.available),
            "local_models": list(local_health.models) if local_health else [],
            # Whether the "look this up on the web" action exists at all. It
            # needs the endpoint AND the personal client's tool list to name a
            # network tool: a switch alone never grants the internet.
            "web_search_enabled": bool(
                settings.WEB_SEARCH_ENABLED
                and settings.WEB_SEARCH_URL
                and client is not None
                and "web_search" in (client.allowed_tools or [])
            ),
            "live": {
                "market_news": settings.MARKET_NEWS_ENABLED,
                "trading_status": bool(
                    settings.TRADING_STATUS_ENABLED
                    and settings.TRADING_PLATFORM_URL
                    and settings.TRADING_PLATFORM_API_KEY
                ),
            },
        },
    )


@ui_router.post("/chat/ask", status_code=202)
def chat_ask(
    request: Request,
    body: AdminChatBody,
    session: dict = Depends(admin_session),
    db: Session = Depends(db_dep),
    settings: Settings = Depends(settings_dep),
) -> dict:
    """Queue the question as a background job and return its id at once.

    A local model on CPU can take minutes, and every reverse proxy in front
    of the dashboard has a timeout shorter than that. The page polls
    ``/admin/chat/task/{id}`` instead, so no proxy ever waits on the model.
    The job runs the same GatewayRouter as a call to /api/v1/tasks.
    """
    from app.api.routes.tasks import CHAT_JOB

    client = _personal_client(db, settings)
    if client is None:
        raise ProviderUnavailableError(
            f"the personal client '{settings.PERSONAL_CLIENT_ID}' does not exist — "
            "run: python -m app.cli bootstrap-brother"
        )
    decision = request.app.state.limiter.check(
        client.client_id, rate_override=client.rate_limit_per_minute
    )
    if not decision.allowed:
        raise RateLimitedError(
            f"rate limit exceeded; retry in {decision.retry_after:.0f}s",
            detail={"retry_after": decision.retry_after, "limit": decision.limit},
        )
    # Refuse an unknown agent now, not inside the job. "auto" is legal and
    # is resolved by the router when the job runs, with the message in hand.
    resolve_agent(body.agent)
    job_id = request.app.state.jobs.submit(
        client_id=client.client_id,
        kind=CHAT_JOB,
        payload={
            "message": body.message,
            "agent": body.agent or "auto",
            "agent_fallback": settings.PERSONAL_AGENT,
            "conversation_id": body.conversation_id,
            "user_ref": f"admin:{session.get('sub')}"[:120],
            "store_conversation": True,
        },
    )
    return {"task_id": job_id, "status": "queued"}


@ui_router.get("/chat/task/{task_id}")
def chat_task(
    task_id: str,
    session: dict = Depends(admin_session),
    db: Session = Depends(db_dep),
    settings: Settings = Depends(settings_dep),
) -> dict:
    from app.database.models import Job

    job = db.get(Job, task_id)
    if job is None or job.client_id != settings.PERSONAL_CLIENT_ID:
        raise NotFoundError(f"task '{task_id}' not found")
    return {
        "task_id": job.id,
        "status": job.status,
        "result": job.result or None,
        "error": job.error,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


@ui_router.post("/chat/ask-now")
def chat_ask_now(
    request: Request,
    body: AdminChatBody,
    session: dict = Depends(admin_session),
    db: Session = Depends(db_dep),
    runtime: Runtime = Depends(runtime_dep),
    settings: Settings = Depends(settings_dep),
) -> dict:
    """The synchronous form, for scripts behind no proxy. Same ladder, same client."""
    from app.gateway.router import GatewayRequest

    client = _personal_client(db, settings)
    if client is None:
        raise ProviderUnavailableError(
            f"the personal client '{settings.PERSONAL_CLIENT_ID}' does not exist — "
            "run: python -m app.cli bootstrap-brother"
        )
    # The same per-client rate limit the API applies; an operator's browser is
    # not exempt from the guard against an accidental loop.
    decision = request.app.state.limiter.check(
        client.client_id, rate_override=client.rate_limit_per_minute
    )
    if not decision.allowed:
        raise RateLimitedError(
            f"rate limit exceeded; retry in {decision.retry_after:.0f}s",
            detail={"retry_after": decision.retry_after, "limit": decision.limit},
        )
    agent, routing = resolve_agent_for(
        body.agent, body.message, fallback=settings.PERSONAL_AGENT
    )
    services = runtime.for_session(db, client.client_id)
    result = services.router.handle(
        GatewayRequest(
            message=body.message,
            client=client,
            conversation_id=body.conversation_id,
            user_ref=f"admin:{session.get('sub')}"[:120],
            agent=agent,
        )
    )
    answer = result.as_dict()
    if routing is not None:
        answer["agent_routing"] = routing
    return answer


@ui_router.post("/chat/research", status_code=202)
def chat_research(
    request: Request,
    body: ResearchBody,
    session: dict = Depends(admin_session),
    db: Session = Depends(db_dep),
    settings: Settings = Depends(settings_dep),
) -> dict:
    """Queue a web-research run and return at once.

    Queued rather than run here for the same reason the chat is: a search plus
    a grounded local answer is minutes of work, and no reader and no reverse
    proxy should be holding a connection open for it. The chat has already
    answered with what it had.

    What comes back is never an answer that has been adopted. It is a
    candidate, with its sources and their tiers, waiting on /admin/solutions
    for a person to confirm or reject.
    """
    from app.api.routes.tasks import RESEARCH_JOB

    if not settings.WEB_SEARCH_ENABLED:
        raise ValidationError(
            "web search is disabled in this deployment (WEB_SEARCH_ENABLED=false)"
        )
    client = _personal_client(db, settings)
    if client is None:
        raise ProviderUnavailableError(
            f"the personal client '{settings.PERSONAL_CLIENT_ID}' does not exist — "
            "run: python -m app.cli bootstrap-brother"
        )
    job_id = request.app.state.jobs.submit(
        client_id=client.client_id,
        kind=RESEARCH_JOB,
        payload={"question": body.question},
    )
    audit.record(
        db,
        actor=str(session.get("sub")),
        action=audit.ADMIN_ACTION,
        actor_type="admin",
        resource_type="job",
        resource_id=job_id,
        detail={"action": "research", "question": body.question[:200]},
    )
    return {"task_id": job_id, "status": "queued"}


@ui_router.post("/chat/teach")
def chat_teach(
    body: TeachBody,
    session: dict = Depends(admin_session),
    db: Session = Depends(db_dep),
    runtime: Runtime = Depends(runtime_dep),
    settings: Settings = Depends(settings_dep),
) -> dict:
    """The owner corrects Brother. The pair goes through the same promotion
    gate as a paid answer; it is offered back only once the local model has
    shown it can use it. This is how a no-paid-provider deployment learns."""
    from app.learning.teaching import teach

    client = _personal_client(db, settings)
    if client is None:
        raise ProviderUnavailableError(
            f"the personal client '{settings.PERSONAL_CLIENT_ID}' does not exist — "
            "run: python -m app.cli bootstrap-brother"
        )
    services = runtime.for_session(db, client.client_id)
    try:
        result = teach(
            db,
            client.client_id,
            question=body.question,
            answer=body.answer,
            evidence=body.evidence,
            actor=f"admin:{session.get('sub')}"[:120],
            settings=settings,
            local_provider=runtime.providers.local,
            retriever=services.retriever,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    audit.record(
        db,
        actor=str(session.get("sub")),
        action=audit.ADMIN_ACTION,
        actor_type="admin",
        resource_type="solution",
        resource_id=result.solution_id,
        detail={"action": "teach", "status": result.outcome.status.value},
    )
    return result.as_dict()
