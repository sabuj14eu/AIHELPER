"""Shared fixtures.

Every test runs against a real SQLite database, the real gateway, the real
validation pipeline and the real cost tracker. Only the two providers are
fakes — see tests/fakes.py for why that boundary is where it is.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("AI_HELPER_ENV_FILE", "/nonexistent")

from sqlalchemy import create_engine, event  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.core.security import generate_api_key  # noqa: E402
from app.database import session as db_session  # noqa: E402
from app.database.enums import Classification  # noqa: E402
from app.database.models import Client  # noqa: E402
from app.memory.embeddings import HashingEmbedder  # noqa: E402
from app.providers.provider_registry import ProviderRegistry  # noqa: E402
from app.runtime import Runtime, set_runtime  # noqa: E402
from app.tools import build_registry  # noqa: E402
from tests.fakes import FakeLocalProvider, FakePaidProvider  # noqa: E402


@pytest.fixture
def settings() -> Settings:
    return Settings(
        ENVIRONMENT="test",
        DATABASE_URL="sqlite+pysqlite:///:memory:",
        OLLAMA_ENABLED=True,
        QDRANT_ENABLED=False,
        ANTHROPIC_ENABLED=True,
        ANTHROPIC_API_KEY="test-key-not-real",
        AI_DAILY_API_BUDGET=5.0,
        AI_MONTHLY_API_BUDGET=50.0,
        AUTH_SECRET="test-secret",
        AUTO_PROMOTE=True,
        PROMOTION_REQUIRES_REPRODUCTION=True,
        LOG_LEVEL="CRITICAL",
    )


@pytest.fixture
def engine(tmp_path):
    """A file-backed SQLite database, one per test.

    Not ``:memory:``: an in-memory SQLite has to be shared through a
    StaticPool, which hands every session the same DBAPI connection. Background
    job threads then interleave on one connection and produce StaleDataError
    failures that exist only in the test harness. A file gives each connection
    its own handle, which is how PostgreSQL behaves in production, so what the
    tests exercise is what actually runs.
    """
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _fast_pragmas(dbapi_connection, _record):
        # WAL for concurrent readers; synchronous=OFF because a test database
        # that is lost on power failure is not a problem worth an fsync per
        # commit. Production keeps SQLAlchemy's defaults (see session.py).
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=OFF")
        cursor.close()

    db_session.configure(engine)
    db_session.create_all(engine)
    yield engine
    db_session.reset()


@pytest.fixture
def db(engine):
    session = db_session.get_session_factory()()
    try:
        yield session
        session.commit()
    finally:
        session.close()


@pytest.fixture
def local_provider() -> FakeLocalProvider:
    return FakeLocalProvider()


@pytest.fixture
def paid_provider() -> FakePaidProvider:
    return FakePaidProvider()


@pytest.fixture
def runtime(settings, engine, local_provider, paid_provider) -> Runtime:
    """A Runtime with fake providers and the offline lexical embedder."""
    runtime = Runtime.__new__(Runtime)
    runtime.settings = settings
    registry = ProviderRegistry(local=local_provider, paid={paid_provider.name: paid_provider})
    runtime.providers = registry
    runtime.tools = build_registry(settings, lambda: registry)
    runtime.embedder = HashingEmbedder(512)
    from app.memory.thresholds import for_embedder

    runtime.thresholds = for_embedder(runtime.embedder, settings)
    runtime._qdrant = None
    set_runtime(runtime)
    yield runtime
    set_runtime(None)


def make_client(
    db,
    client_id: str = "acme",
    *,
    may_escalate: bool = True,
    allowed_tools=None,
    max_external: str = Classification.INTERNAL.value,
    default_classification: str = Classification.INTERNAL.value,
    daily_budget: float | None = None,
    is_admin: bool = False,
) -> tuple[Client, str]:
    key = generate_api_key()
    client = Client(
        client_id=client_id,
        name=client_id.title(),
        api_key_id=key.key_id,
        api_key_hash=key.hashed,
        enabled=True,
        is_admin=is_admin,
        allowed_tools=allowed_tools,
        may_escalate=may_escalate,
        default_classification=default_classification,
        max_external_classification=max_external,
        daily_budget_usd=daily_budget,
    )
    db.add(client)
    db.flush()
    return client, key.plaintext


@pytest.fixture
def client_row(db):
    client, _ = make_client(db)
    return client


@pytest.fixture
def services(runtime, db, client_row):
    return runtime.for_session(db, client_row.client_id)
