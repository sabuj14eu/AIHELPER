"""The learning loop in numbers — cumulative, and including the zeros.

`knowledge-status` answers "what does Brother hold?". This answers the
question that actually gets asked: **is this working?** They are not the same
question, and the second one is only answerable if the failures are counted
too. A report that shows candidates and promotions and nothing else cannot
distinguish a system that is learning from one that is producing rejects.

So every stage of the pipeline appears, in order, with what fell out at each:

    searched -> answered -> validated -> checked against what is known
    -> captured -> awaiting approval -> promoted -> indexed -> retrievable

The last two are the ones most worth reading, because they are where a loop
that *looks* finished quietly stops: a row can be PROMOTED and still not be in
the vector index, and a row can be in the index and still not come back for the
question it answers. "Promoted" is a status; "retrieval confirmed" is the only
one of these numbers that means Brother can actually use what it learned.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.enums import SolutionStatus
from app.database.models import SolutionCandidate
from app.learning.origin import SolutionOrigin, origin_of


def _research_record(row: SolutionCandidate) -> dict:
    return (row.validation_result or {}).get("research") or {}


def learning_report(session: Session, client_id: str, *, retriever=None) -> dict:
    """Everything learned for this client, by origin, by stage, by source tier.

    ``retriever`` is optional: without it the retrieval check is reported as
    NOT RUN rather than as zero. A gate that did not run is never a PASS, and
    it is never a fail either — saying "0 retrievable" when nothing was asked
    would be the more misleading of the two.
    """
    rows = list(
        session.scalars(
            select(SolutionCandidate).where(SolutionCandidate.client_id == client_id)
        )
    )

    by_origin = {origin.value: 0 for origin in SolutionOrigin}
    by_status = {status.value: 0 for status in SolutionStatus}
    web = [r for r in rows if origin_of(r.provider) is SolutionOrigin.SELF_WEB]
    by_tier: dict[str, int] = {}
    relations = {"new": 0, "duplicate": 0, "update": 0, "contradiction": 0}
    trading = {"source_fact": 0, "trading_interpretation": 0, "observation": 0, "general_rule": 0}

    for row in rows:
        by_origin[origin_of(row.provider).value] += 1
        by_status[row.status] = by_status.get(row.status, 0) + 1
        check = (row.validation_result or {}).get("knowledge_check") or {}
        relation = check.get("relation")
        if relation in relations:
            relations[relation] += 1
        kind = ((row.validation_result or {}).get("trading") or {}).get("claim_kind")
        if kind in trading:
            trading[kind] += 1

    for row in web:
        tier = _research_record(row).get("source_tier")
        if tier is not None:
            by_tier[f"tier_{tier}"] = by_tier.get(f"tier_{tier}", 0) + 1

    promoted = [r for r in rows if r.status == SolutionStatus.PROMOTED.value]
    awaiting = [r for r in rows if r.status == SolutionStatus.CANDIDATE.value]

    # Indexed, and then actually retrievable. Two different claims: the first
    # is "a vector exists", the second is "asking the question brings it back",
    # and only the second means the loop closed.
    indexed: int | None = None
    retrievable: int | None = None
    if retriever is not None and promoted:
        indexed = 0
        retrievable = 0
        for row in promoted:
            try:
                hits = retriever.similar_promoted(row.question, limit=5)
            except Exception:
                indexed = retrievable = None
                break
            if any(found.id == row.id for found, _score in hits):
                indexed += 1
                retrievable += 1

    return {
        "client_id": client_id,
        "total": len(rows),
        "by_origin": by_origin,
        "by_status": by_status,
        "relation_to_existing_knowledge": relations,
        "trading_claims": trading,
        "web_research": {
            "candidates": len(web),
            "by_source_tier": by_tier,
            "awaiting_approval": len(
                [r for r in web if r.status == SolutionStatus.CANDIDATE.value]
            ),
            "promoted": len([r for r in web if r.status == SolutionStatus.PROMOTED.value]),
            "rejected": len([r for r in web if r.status == SolutionStatus.REJECTED.value]),
        },
        "awaiting_approval": len(awaiting),
        "promoted": len(promoted),
        # NOT RUN, never 0, when there was no retriever or the index could not
        # be read. "0 retrievable" and "nobody asked" are opposite findings.
        "indexed_for_retrieval": "NOT RUN" if indexed is None else indexed,
        "retrieval_confirmed": "NOT RUN" if retrievable is None else retrievable,
    }
