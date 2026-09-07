"""Process-wide wiring.

What is expensive and shared lives here and is built once: settings, the
provider registry, the tool registry, the embedder, the Qdrant connection.
What is per-request — anything that holds a database session — is built fresh
by :meth:`Runtime.for_session`.

The embedder is resolved once at startup so that a deployment does not
silently flip between a semantic and a lexical index mid-run: vectors from two
embedders are never comparable, and a store that mixed them would return
nonsense with a confident score.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.cost.tracker import CostTracker
from app.gateway.router import GatewayRouter
from app.knowledge.ingestion import DocumentIngestor
from app.memory.embeddings import Embedder, HashingEmbedder, build_embedder
from app.memory.retrieval import Retriever
from app.memory.semantic import DatabaseVectorStore, QdrantVectorStore, VectorStore
from app.memory.thresholds import Thresholds, for_embedder
from app.providers.provider_registry import ProviderRegistry
from app.tools import build_registry
from app.tools.registry import ToolRegistry

log = get_logger("runtime")


@dataclass
class SessionServices:
    """Everything a request needs, bound to one database session."""

    session: Session
    settings: Settings
    store: VectorStore
    retriever: Retriever
    router: GatewayRouter
    cost: CostTracker
    ingestor: DocumentIngestor


class Runtime:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.providers = ProviderRegistry.from_settings(self.settings)
        self.tools: ToolRegistry = build_registry(self.settings, lambda: self.providers)
        self.embedder: Embedder = self._build_embedder()
        self.thresholds: Thresholds = for_embedder(self.embedder, self.settings)
        self._qdrant = self._connect_qdrant()

    # ------------------------------------------------------------- startup
    def _build_embedder(self) -> Embedder:
        manager = getattr(self.providers, "model_manager", None)
        client = getattr(self.providers, "ollama_client", None)
        if not self.settings.OLLAMA_ENABLED:
            return HashingEmbedder(512)
        return build_embedder(manager, client, configured_dim=self.settings.EMBEDDING_DIM)

    def _connect_qdrant(self):
        if not self.settings.QDRANT_ENABLED:
            return None
        try:
            from qdrant_client import QdrantClient

            client = QdrantClient(
                url=self.settings.QDRANT_URL,
                api_key=self.settings.QDRANT_API_KEY,
                timeout=10.0,
            )
            client.get_collections()
            log.info("qdrant_connected", url=self.settings.QDRANT_URL)
            return client
        except Exception as exc:
            # Not fatal. The database-backed store keeps semantic memory
            # working, durably, at lower scale — and /health says which is in use.
            log.warning(
                "qdrant_unavailable",
                error=type(exc).__name__,
                falling_back_to="database vector store",
            )
            return None

    def recheck_qdrant(self) -> bool:
        """Try to reconnect. Called by the health endpoint, not per request."""
        if self._qdrant is None and self.settings.QDRANT_ENABLED:
            self._qdrant = self._connect_qdrant()
        return self._qdrant is not None

    @property
    def vector_backend(self) -> str:
        return "qdrant" if self._qdrant is not None else "database"

    # --------------------------------------------------------- per request
    def vector_store(self, session: Session) -> VectorStore:
        if self._qdrant is not None:
            return QdrantVectorStore(self._qdrant, self.embedder.dim)
        return DatabaseVectorStore(session)

    def retriever(self, session: Session, client_id: str) -> Retriever:
        return Retriever(
            session,
            client_id,
            embedder=self.embedder,
            store=self.vector_store(session),
            thresholds=self.thresholds,
            settings=self.settings,
        )

    def for_session(self, session: Session, client_id: str) -> SessionServices:
        store = self.vector_store(session)
        retriever = Retriever(
            session,
            client_id,
            embedder=self.embedder,
            store=store,
            thresholds=self.thresholds,
            settings=self.settings,
        )
        cost = CostTracker(session, self.settings)
        router = GatewayRouter(
            session,
            settings=self.settings,
            registry=self.providers,
            tools=self.tools,
            retriever=retriever,
            cost_tracker=cost,
        )
        ingestor = DocumentIngestor(
            session,
            client_id,
            retriever=retriever,
            chunk_size=self.settings.CHUNK_SIZE,
            chunk_overlap=self.settings.CHUNK_OVERLAP,
            max_bytes=self.settings.MAX_UPLOAD_BYTES,
        )
        return SessionServices(
            session=session,
            settings=self.settings,
            store=store,
            retriever=retriever,
            router=router,
            cost=cost,
            ingestor=ingestor,
        )

    # --------------------------------------------------------------- info
    def describe(self) -> dict:
        return {
            "embedder": self.embedder.id,
            "embedder_semantic": self.embedder.semantic,
            "embedding_dim": self.embedder.dim,
            "vector_backend": self.vector_backend,
            "thresholds": self.thresholds.as_dict(),
            "tools": self.tools.names(),
            "providers": [h.as_dict() for h in self.providers.health()],
        }

    def close(self) -> None:
        self.providers.close()
        if self._qdrant is not None:
            with contextlib.suppress(Exception):
                self._qdrant.close()


_runtime: Runtime | None = None


def get_runtime() -> Runtime:
    global _runtime
    if _runtime is None:
        _runtime = Runtime()
    return _runtime


def set_runtime(runtime: Runtime | None) -> None:
    global _runtime
    _runtime = runtime
