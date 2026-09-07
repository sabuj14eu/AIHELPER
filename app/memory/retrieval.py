"""Unified retrieval — level 1 of the routing ladder.

This is the module that decides whether the system already knows the answer,
and it is therefore the module that determines how much the deployment spends.

Sources, in the order they are consulted:

1. **Promoted solutions**, exact fingerprint match. The same question asked
   twice must never be paid for twice.
2. **Promoted solutions**, vector similarity. Catches the paraphrase.
3. **Long-term memory** for this client.
4. **Document chunks** for this client.

Everything returned carries provenance and a score, and everything is scoped
to the calling client. A CANDIDATE or REJECTED solution is never returned:
only PROMOTED rows are offered back to the model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.logging import get_logger
from app.database.enums import MemoryStatus, SolutionStatus, TaskType
from app.database.models import DocumentChunk, MemoryItem, SolutionCandidate
from app.learning.similarity import fingerprint, jaccard
from app.local_ai.prompts import ContextItem
from app.memory.embeddings import Embedder
from app.memory.semantic import VectorStore
from app.memory.thresholds import Thresholds

log = get_logger("retrieval")

REF_SOLUTION = "solution"
REF_MEMORY = "memory"
REF_CHUNK = "chunk"


def collection_name(kind: str, embedder: Embedder) -> str:
    """Vectors from different embedders are never mixed."""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in embedder.id)
    return f"{kind}__{safe}"


@dataclass
class RetrievalResult:
    items: list[ContextItem] = field(default_factory=list)
    top_score: float = 0.0
    solution: SolutionCandidate | None = None
    solution_score: float = 0.0
    exact_match: bool = False
    memory_hit: bool = False
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def has_context(self) -> bool:
        return bool(self.items)

    def context_texts(self) -> list[str]:
        return [item.content for item in self.items]

    def as_dict(self) -> dict:
        return {
            "memory_hit": self.memory_hit,
            "exact_match": self.exact_match,
            "top_score": round(self.top_score, 4),
            "solution_id": self.solution.id if self.solution else None,
            "solution_score": round(self.solution_score, 4),
            "counts": dict(self.counts),
            "sources": [
                {"source": i.source, "ref": i.ref, "score": round(i.score, 4)} for i in self.items
            ],
        }


class Retriever:
    def __init__(
        self,
        session: Session,
        client_id: str,
        *,
        embedder: Embedder,
        store: VectorStore,
        thresholds: Thresholds,
        settings: Settings,
    ):
        self.session = session
        self.client_id = client_id
        self.embedder = embedder
        self.store = store
        self.thresholds = thresholds
        self.settings = settings

    # -------------------------------------------------------------- indexing
    def index_solution(self, solution: SolutionCandidate) -> None:
        vector = self.embedder.embed_one(solution.question)
        self.store.upsert(
            collection=collection_name("solutions", self.embedder),
            point_id=f"sol:{solution.id}",
            client_id=solution.client_id,
            vector=vector,
            ref_type=REF_SOLUTION,
            ref_id=solution.id,
            payload={"status": solution.status, "task_type": solution.task_type},
        )

    def unindex_solution(self, solution_id: str) -> None:
        self.store.delete_ref(
            collection=collection_name("solutions", self.embedder),
            client_id=self.client_id,
            ref_type=REF_SOLUTION,
            ref_id=solution_id,
        )

    def index_memory(self, item: MemoryItem) -> None:
        vector = self.embedder.embed_one(item.content)
        self.store.upsert(
            collection=collection_name("memory", self.embedder),
            point_id=f"mem:{item.id}",
            client_id=item.client_id,
            vector=vector,
            ref_type=REF_MEMORY,
            ref_id=item.id,
            payload={"kind": item.kind, "namespace": item.namespace},
        )

    def index_chunk(self, chunk: DocumentChunk) -> None:
        vector = self.embedder.embed_one(chunk.content)
        self.store.upsert(
            collection=collection_name("knowledge", self.embedder),
            point_id=f"chunk:{chunk.id}",
            client_id=chunk.client_id,
            vector=vector,
            ref_type=REF_CHUNK,
            ref_id=chunk.id,
            payload={"document_id": chunk.document_id, "namespace": chunk.namespace},
        )

    def index_chunks(self, chunks: list[DocumentChunk]) -> int:
        if not chunks:
            return 0
        vectors = self.embedder.embed([c.content for c in chunks])
        collection = collection_name("knowledge", self.embedder)
        for chunk, vector in zip(chunks, vectors, strict=True):
            self.store.upsert(
                collection=collection,
                point_id=f"chunk:{chunk.id}",
                client_id=chunk.client_id,
                vector=vector,
                ref_type=REF_CHUNK,
                ref_id=chunk.id,
                payload={"document_id": chunk.document_id, "namespace": chunk.namespace},
            )
        return len(chunks)

    def unindex_document(self, document_id: str, chunk_ids: list[str]) -> int:
        collection = collection_name("knowledge", self.embedder)
        removed = 0
        for chunk_id in chunk_ids:
            removed += self.store.delete_ref(
                collection=collection,
                client_id=self.client_id,
                ref_type=REF_CHUNK,
                ref_id=chunk_id,
            )
        return removed

    # ------------------------------------------------------------- retrieval
    def find_exact_solution(self, question: str) -> SolutionCandidate | None:
        """Fingerprint match on a promoted solution. Embedder-independent."""
        fp = fingerprint(question, salt=self.client_id)
        stmt = (
            select(SolutionCandidate)
            .where(
                SolutionCandidate.client_id == self.client_id,
                SolutionCandidate.fingerprint == fp,
                SolutionCandidate.status == SolutionStatus.PROMOTED.value,
            )
            .order_by(SolutionCandidate.promoted_at.desc())
            .limit(1)
        )
        solution = self.session.scalars(stmt).first()
        if solution is not None and _expired(solution.expires_at):
            return None
        return solution

    def _similar_solutions(self, vector: list[float], limit: int) -> list[tuple[SolutionCandidate, float]]:
        hits = self.store.search(
            collection=collection_name("solutions", self.embedder),
            client_id=self.client_id,
            vector=vector,
            limit=limit,
            min_score=self.thresholds.solution_reuse,
            ref_type=REF_SOLUTION,
            extra_filter={"status": SolutionStatus.PROMOTED.value},
        )
        out: list[tuple[SolutionCandidate, float]] = []
        for hit in hits:
            solution = self.session.get(SolutionCandidate, hit.ref_id)
            if solution is None or solution.client_id != self.client_id:
                continue
            if solution.status != SolutionStatus.PROMOTED.value or _expired(solution.expires_at):
                continue
            out.append((solution, hit.score))
        return out

    def retrieve(
        self,
        question: str,
        *,
        task_type: TaskType | str = TaskType.GENERAL,
        namespace: str | None = None,
        top_k: int | None = None,
        include_solutions: bool = True,
    ) -> RetrievalResult:
        result = RetrievalResult()
        top_k = top_k or self.settings.MEMORY_TOP_K
        counts = {"solutions": 0, "memory": 0, "chunks": 0}

        # 1. Exact repeat of a question we already paid to answer.
        if include_solutions:
            exact = self.find_exact_solution(question)
            if exact is not None:
                result.solution = exact
                result.solution_score = 1.0
                result.exact_match = True
                result.memory_hit = True
                result.items.append(
                    ContextItem(
                        source="promoted_solution",
                        ref=exact.id,
                        content=exact.answer,
                        score=1.0,
                        note="exact match on a previously validated answer",
                    )
                )
                counts["solutions"] += 1

        vector: list[float] | None = None
        try:
            vector = self.embedder.embed_one(question)
        except Exception as exc:
            # Retrieval must degrade, never fail the request.
            log.warning("embedding_failed", error=type(exc).__name__)

        if vector is not None and include_solutions and result.solution is None:
            # 2. Paraphrase of a question we already paid to answer.
            for solution, score in self._similar_solutions(vector, limit=2):
                # A vector hit is corroborated by lexical overlap before it is
                # trusted enough to answer from: a single similarity number is
                # one witness, and one witness is how you get a confident
                # answer to a question nobody asked.
                lexical = jaccard(question, solution.question)
                if lexical < 0.25:
                    log.info(
                        "solution_similarity_uncorroborated",
                        vector_score=round(score, 3),
                        lexical=round(lexical, 3),
                    )
                    continue
                if result.solution is None:
                    result.solution = solution
                    result.solution_score = score
                    result.memory_hit = True
                result.items.append(
                    ContextItem(
                        source="promoted_solution",
                        ref=solution.id,
                        content=solution.answer,
                        score=score,
                        note=f"similar question, score {score:.2f}",
                    )
                )
                counts["solutions"] += 1

        if vector is not None:
            # 3. Long-term memory.
            for hit in self.store.search(
                collection=collection_name("memory", self.embedder),
                client_id=self.client_id,
                vector=vector,
                limit=top_k,
                min_score=self.thresholds.memory,
                ref_type=REF_MEMORY,
            ):
                item = self.session.get(MemoryItem, hit.ref_id)
                if item is None or item.client_id != self.client_id:
                    continue
                if item.status != MemoryStatus.ACTIVE.value or _expired(item.expires_at):
                    continue
                if namespace and item.namespace != namespace:
                    continue
                result.items.append(
                    ContextItem(
                        source="memory",
                        ref=item.id,
                        content=item.content,
                        score=hit.score,
                        note=f"{item.kind} from {item.source}",
                    )
                )
                counts["memory"] += 1
                result.memory_hit = True

            # 4. Documents.
            for hit in self.store.search(
                collection=collection_name("knowledge", self.embedder),
                client_id=self.client_id,
                vector=vector,
                limit=self.settings.KNOWLEDGE_TOP_K,
                min_score=self.thresholds.memory,
                ref_type=REF_CHUNK,
            ):
                chunk = self.session.get(DocumentChunk, hit.ref_id)
                if chunk is None or chunk.client_id != self.client_id:
                    continue
                if namespace and chunk.namespace != namespace:
                    continue
                result.items.append(
                    ContextItem(
                        source="document",
                        ref=f"{chunk.document_id}#{chunk.ordinal}",
                        content=chunk.content,
                        score=hit.score,
                        note=f"document chunk, score {hit.score:.2f}",
                    )
                )
                counts["chunks"] += 1

        result.items.sort(key=lambda i: i.score, reverse=True)
        result.top_score = result.items[0].score if result.items else 0.0
        result.counts = counts
        return result


def _expired(when: datetime | None) -> bool:
    if when is None:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return when <= datetime.now(UTC)
