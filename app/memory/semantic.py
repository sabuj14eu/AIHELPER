"""Vector storage and similarity search.

Two backends behind one interface:

* :class:`QdrantVectorStore` — the production backend.
* :class:`DatabaseVectorStore` — a brute-force cosine scan over a Postgres or
  SQLite table. It is durable (unlike an in-process dict), it is honest about
  its limits (linear in the number of points for a client, fine into the tens
  of thousands, not a Qdrant replacement), and it means the system keeps
  working when Qdrant is down instead of losing memory entirely.

Client isolation is enforced in **both** backends by filtering on client_id in
the query itself, not by post-filtering results. See tests/security.
"""

from __future__ import annotations

import abc
import contextlib
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.database.models import VectorPoint
from app.memory.embeddings import cosine

log = get_logger("semantic")


@dataclass
class SearchHit:
    id: str
    ref_type: str
    ref_id: str
    score: float
    payload: dict

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "ref_type": self.ref_type,
            "ref_id": self.ref_id,
            "score": round(self.score, 4),
            "payload": self.payload,
        }


class VectorStore(abc.ABC):
    backend: str = "unknown"

    @abc.abstractmethod
    def upsert(
        self,
        *,
        collection: str,
        point_id: str,
        client_id: str,
        vector: list[float],
        ref_type: str,
        ref_id: str,
        payload: dict | None = None,
    ) -> None:
        ...

    @abc.abstractmethod
    def search(
        self,
        *,
        collection: str,
        client_id: str,
        vector: list[float],
        limit: int = 5,
        min_score: float = 0.0,
        ref_type: str | None = None,
        extra_filter: dict | None = None,
    ) -> list[SearchHit]:
        ...

    @abc.abstractmethod
    def delete_ref(self, *, collection: str, client_id: str, ref_type: str, ref_id: str) -> int:
        ...

    @abc.abstractmethod
    def count(self, *, collection: str, client_id: str | None = None) -> int:
        ...

    def healthy(self) -> bool:
        return True


class DatabaseVectorStore(VectorStore):
    """Durable brute-force cosine search inside the relational database."""

    backend = "database"

    def __init__(self, session: Session):
        self.session = session

    def upsert(
        self,
        *,
        collection: str,
        point_id: str,
        client_id: str,
        vector: list[float],
        ref_type: str,
        ref_id: str,
        payload: dict | None = None,
    ) -> None:
        existing = self.session.get(VectorPoint, point_id)
        if existing is not None:
            if existing.client_id != client_id:
                # Never let one client's write land on another's point.
                raise PermissionError("vector point belongs to a different client")
            existing.vector = vector
            existing.payload = payload or {}
            existing.collection = collection
            existing.ref_type = ref_type
            existing.ref_id = ref_id
            return
        self.session.add(
            VectorPoint(
                id=point_id,
                collection=collection,
                client_id=client_id,
                ref_type=ref_type,
                ref_id=ref_id,
                vector=vector,
                payload=payload or {},
            )
        )

    def search(
        self,
        *,
        collection: str,
        client_id: str,
        vector: list[float],
        limit: int = 5,
        min_score: float = 0.0,
        ref_type: str | None = None,
        extra_filter: dict | None = None,
    ) -> list[SearchHit]:
        stmt = select(VectorPoint).where(
            VectorPoint.collection == collection,
            VectorPoint.client_id == client_id,  # isolation, in the query
        )
        if ref_type:
            stmt = stmt.where(VectorPoint.ref_type == ref_type)
        hits: list[SearchHit] = []
        for point in self.session.scalars(stmt):
            if extra_filter and not _payload_matches(point.payload or {}, extra_filter):
                continue
            score = cosine(vector, point.vector or [])
            if score < min_score:
                continue
            hits.append(
                SearchHit(
                    id=point.id,
                    ref_type=point.ref_type,
                    ref_id=point.ref_id,
                    score=score,
                    payload=point.payload or {},
                )
            )
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]

    def delete_ref(self, *, collection: str, client_id: str, ref_type: str, ref_id: str) -> int:
        result = self.session.execute(
            delete(VectorPoint).where(
                VectorPoint.collection == collection,
                VectorPoint.client_id == client_id,
                VectorPoint.ref_type == ref_type,
                VectorPoint.ref_id == ref_id,
            )
        )
        return int(result.rowcount or 0)

    def count(self, *, collection: str, client_id: str | None = None) -> int:
        stmt = select(VectorPoint).where(VectorPoint.collection == collection)
        if client_id:
            stmt = stmt.where(VectorPoint.client_id == client_id)
        return len(list(self.session.scalars(stmt)))


def _payload_matches(payload: dict, wanted: dict) -> bool:
    return all(payload.get(key) == value for key, value in wanted.items())


class QdrantVectorStore(VectorStore):
    """Qdrant backend. Collections are created on first write."""

    backend = "qdrant"

    def __init__(self, client, dim: int):
        self.client = client
        self.dim = dim
        self._ensured: set[str] = set()

    def _ensure(self, collection: str) -> None:
        if collection in self._ensured:
            return
        from qdrant_client.models import Distance, VectorParams

        try:
            if not self.client.collection_exists(collection):
                self.client.create_collection(
                    collection_name=collection,
                    vectors_config=VectorParams(size=self.dim, distance=Distance.COSINE),
                )
                # Payload indexes make the client_id filter cheap at scale.
                for field in ("client_id", "ref_type", "ref_id"):
                    # An index is an optimisation; a server that refuses one
                    # still stores and filters correctly, just more slowly.
                    with contextlib.suppress(Exception):
                        self.client.create_payload_index(
                            collection_name=collection, field_name=field, field_schema="keyword"
                        )
        finally:
            self._ensured.add(collection)

    @staticmethod
    def _point_uuid(point_id: str) -> str:
        # Qdrant ids must be a UUID or an unsigned integer; our ids are strings.
        return str(uuid.uuid5(uuid.NAMESPACE_URL, point_id))

    def upsert(
        self,
        *,
        collection: str,
        point_id: str,
        client_id: str,
        vector: list[float],
        ref_type: str,
        ref_id: str,
        payload: dict | None = None,
    ) -> None:
        from qdrant_client.models import PointStruct

        self._ensure(collection)
        body = dict(payload or {})
        body.update({"client_id": client_id, "ref_type": ref_type, "ref_id": ref_id, "point_id": point_id})
        self.client.upsert(
            collection_name=collection,
            points=[PointStruct(id=self._point_uuid(point_id), vector=vector, payload=body)],
        )

    def _filter(self, client_id: str, ref_type: str | None, extra: dict | None):
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        must = [FieldCondition(key="client_id", match=MatchValue(value=client_id))]
        if ref_type:
            must.append(FieldCondition(key="ref_type", match=MatchValue(value=ref_type)))
        for key, value in (extra or {}).items():
            must.append(FieldCondition(key=key, match=MatchValue(value=value)))
        return Filter(must=must)

    def search(
        self,
        *,
        collection: str,
        client_id: str,
        vector: list[float],
        limit: int = 5,
        min_score: float = 0.0,
        ref_type: str | None = None,
        extra_filter: dict | None = None,
    ) -> list[SearchHit]:
        self._ensure(collection)
        results = self.client.query_points(
            collection_name=collection,
            query=vector,
            limit=limit,
            score_threshold=min_score or None,
            query_filter=self._filter(client_id, ref_type, extra_filter),
            with_payload=True,
        ).points
        hits: list[SearchHit] = []
        for point in results:
            payload = dict(point.payload or {})
            # Belt and braces: never return a point whose payload says it
            # belongs to somebody else, whatever the filter did.
            if payload.get("client_id") != client_id:
                log.error("qdrant_filter_leak", collection=collection)
                continue
            hits.append(
                SearchHit(
                    id=payload.get("point_id", str(point.id)),
                    ref_type=payload.get("ref_type", ""),
                    ref_id=payload.get("ref_id", ""),
                    score=float(point.score),
                    payload=payload,
                )
            )
        return hits

    def delete_ref(self, *, collection: str, client_id: str, ref_type: str, ref_id: str) -> int:
        self._ensure(collection)
        self.client.delete(
            collection_name=collection,
            points_selector=self._filter(client_id, ref_type, {"ref_id": ref_id}),
        )
        return 1

    def count(self, *, collection: str, client_id: str | None = None) -> int:
        self._ensure(collection)
        if client_id:
            return int(
                self.client.count(
                    collection_name=collection,
                    count_filter=self._filter(client_id, None, None),
                    exact=True,
                ).count
            )
        return int(self.client.count(collection_name=collection, exact=True).count)

    def healthy(self) -> bool:
        try:
            self.client.get_collections()
            return True
        except Exception:
            return False
