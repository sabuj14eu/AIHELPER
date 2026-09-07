"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from app import __version__
from app.api.jobs import JobRunner
from app.api.ratelimit import TokenBucketLimiter
from app.api.routes import admin, chat, documents, health, memory, models, solutions, tasks
from app.core.config import Settings, get_settings
from app.core.errors import AIHelperError
from app.core.ids import new_request_id
from app.core.logging import client_id_var, configure_logging, get_logger, request_id_var
from app.database.session import create_all, get_engine
from app.runtime import Runtime, set_runtime

log = get_logger("main")

DESCRIPTION = """
A self-hosted, local-first AI gateway.

Every request walks the same ladder: deterministic tools, then memory and
documents, then the local model, then validation — and only if none of those
produced a validated answer, and only if the client, the data classification
and the budget all allow it, a paid provider.

Answers that a paid provider had to supply are captured, and promoted into
local knowledge only after they validate *and* the local model demonstrates it
can use them. That is the mechanism by which paid usage falls over time.
"""


def register_jobs(runner: JobRunner) -> None:
    """Job handlers. Each opens its own session; none holds a request's."""

    def chat_job(client_id: str, payload: dict) -> dict:
        from app.api.deps import resolve_agent
        from app.database.models import Client
        from app.database.session import session_scope
        from app.gateway.router import GatewayRequest
        from app.runtime import get_runtime

        with session_scope() as session:
            client = session.get(Client, client_id)
            if client is None:
                raise ValueError(f"client '{client_id}' no longer exists")
            services = get_runtime().for_session(session, client_id)
            result = services.router.handle(
                GatewayRequest(
                    message=payload["message"],
                    client=client,
                    task_type=payload.get("task_type"),
                    conversation_id=payload.get("conversation_id"),
                    document_ids=payload.get("document_ids") or [],
                    namespace=payload.get("namespace"),
                    classification=payload.get("classification"),
                    response_format=payload.get("response_format", "text"),
                    model=payload.get("model"),
                    premium=bool(payload.get("premium")),
                    user_ref=payload.get("user_ref"),
                    max_tokens=payload.get("max_tokens"),
                    store_conversation=bool(payload.get("store_conversation", True)),
                    agent=resolve_agent(payload.get("agent")),
                )
            )
            return result.as_dict()

    runner.register(tasks.CHAT_JOB, chat_job)


def create_app(settings: Settings | None = None, *, runtime: Runtime | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        create_all(get_engine(settings))
        application.state.jobs.recover_orphans()
        log.info(
            "startup",
            version=__version__,
            environment=settings.ENVIRONMENT,
            embedder=application.state.runtime.embedder.id,
            vector_backend=application.state.runtime.vector_backend,
            paid_providers_enabled=application.state.runtime.providers.any_paid_enabled(),
        )
        yield
        application.state.jobs.shutdown(wait=True)
        application.state.runtime.close()
        log.info("shutdown")

    application = FastAPI(
        title="AI Helper",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
    )

    active_runtime = runtime or Runtime(settings)
    set_runtime(active_runtime)
    application.state.settings = settings
    application.state.runtime = active_runtime
    application.state.limiter = TokenBucketLimiter(
        settings.RATE_LIMIT_PER_MINUTE, settings.RATE_LIMIT_BURST
    )
    application.state.jobs = JobRunner(settings.WORKER_CONCURRENCY)
    application.state.templates = Jinja2Templates(
        directory=str(Path(__file__).parent / "templates")
    )
    register_jobs(application.state.jobs)

    # ------------------------------------------------------------ middleware
    @application.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or new_request_id()
        request_id_var.set(request_id)
        client_id_var.set(None)
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    # ------------------------------------------------------- error handling
    @application.exception_handler(AIHelperError)
    async def domain_error(request: Request, exc: AIHelperError):
        # The message is written for the caller; the detail never carries a
        # prompt, an answer or a credential.
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.message,
                "code": exc.code,
                "detail": exc.detail,
                "request_id": request_id_var.get(),
            },
            headers={"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None,
        )

    @application.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.error("unhandled_error", error=type(exc).__name__, path=request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": "an internal error occurred",
                "code": "internal_error",
                "detail": {},
                "request_id": request_id_var.get(),
            },
        )

    # ----------------------------------------------------------------- routes
    application.include_router(health.router)
    application.include_router(chat.router)
    application.include_router(tasks.router)
    application.include_router(documents.router)
    application.include_router(memory.router)
    application.include_router(models.router)
    application.include_router(solutions.router)
    from app.api.routes import usage

    application.include_router(usage.router)
    application.include_router(admin.api_router)
    application.include_router(admin.ui_router)

    @application.get("/", tags=["meta"], summary="What this service is")
    def root() -> dict:
        return {
            "name": settings.APP_NAME,
            "version": __version__,
            "local_first": True,
            "docs": "/docs",
            "health": "/health",
            "admin": "/admin",
        }

    return application


def __getattr__(name: str):
    """``app.main:app`` builds the application on first access, not on import.

    Creating it at import time would open connections to Ollama and Qdrant as a
    side effect of importing the module — which is wrong for a test run, for
    the CLI, and for anything that merely wants to read a symbol from here.
    Uvicorn's ``app.main:app`` still works: the attribute lookup builds it.
    """
    if name == "app":
        application = create_app()
        globals()["app"] = application
        return application
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
