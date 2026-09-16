"""Two questions to ask a candidate before it joins what is already known.

Capture used to check one thing: is this exact question already in the store?
That catches the same sentence twice and nothing else. Two failures got past
it, and they fail in opposite directions:

* **The same thing, worded differently.** Retrieval serves a stored answer
  above the reuse bar, so nothing is ever captured up there. Underneath it
  sits a band -- similar enough that a second row is a second copy, not
  similar enough to answer with -- and every paraphrase asked in that band
  quietly added another near-identical row. Measured on the box: a near-miss
  at 0.6776 against a reuse bar of 0.80.

* **The opposite thing, stored beside it.** Nothing ever compared a new
  answer against what was already promoted. Validation checks an answer
  against the context *retrieved for that question*, which is not the same
  set: a stale promoted solution that contradicts the new answer need not
  rank for the new question at all. So two answers that cannot both be true
  could sit in memory together, and whichever one retrieval happened to
  surface is what Brother would say.

A duplicate is a reason not to store. **A conflict is not** -- it is the most
interesting thing that can happen to a knowledge store, because one of the two
is stale and the system has just found out. Dropping it loses the discovery;
storing it silently leaves the contradiction in place. So it is stored, marked,
and put in front of the owner, who is the only one who can say which is wrong.

Deterministic throughout (Iron Rule 2): vector similarity over an index that
already exists, and `factuality_check`, which is text analysis. No model is
asked to judge anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.database.models import SolutionCandidate
from app.validation.factuality import check as factuality_check


@dataclass
class Conflict:
    solution_id: str
    question: str
    score: float
    detail: str

    def as_dict(self) -> dict:
        return {
            "solution_id": self.solution_id,
            "question": self.question[:200],
            "score": round(self.score, 4),
            "detail": self.detail[:300],
        }


@dataclass
class KnowledgeCheck:
    duplicate: SolutionCandidate | None = None
    duplicate_score: float = 0.0
    conflicts: list[Conflict] = field(default_factory=list)

    @property
    def is_duplicate(self) -> bool:
        return self.duplicate is not None

    @property
    def has_conflict(self) -> bool:
        return bool(self.conflicts)

    def as_dict(self) -> dict:
        return {
            "duplicate_of": self.duplicate.id if self.duplicate else None,
            "duplicate_score": round(self.duplicate_score, 4),
            "conflicts": [c.as_dict() for c in self.conflicts],
        }


def check_against_known(
    retriever,
    *,
    question: str,
    answer: str,
    limit: int = 5,
) -> KnowledgeCheck:
    """Is this already known, and does it disagree with what is?

    Returns an empty check when there is no retriever or the index cannot be
    read. That is deliberate: this is a quality gate, not a safety gate, and a
    vector store being briefly unavailable must not stop the system learning.
    Losing a check costs a duplicate row; refusing to capture costs the lesson.
    """
    check = KnowledgeCheck()
    if retriever is None:
        return check

    try:
        by_question = retriever.similar_promoted(question, limit=limit)
    except Exception:
        return check
    if by_question:
        check.duplicate, check.duplicate_score = by_question[0]

    # Searched by the ANSWER, not the question. A stale solution that
    # contradicts this one may be filed under a question nothing like it --
    # that is exactly the case the question-based search cannot see.
    try:
        neighbours = retriever.similar_promoted(answer, limit=limit)
    except Exception:
        return check

    seen: set[str] = set()
    for solution, score in [*by_question, *neighbours]:
        if solution.id in seen or not (solution.answer or "").strip():
            continue
        seen.add(solution.id)
        report = factuality_check(answer, [solution.answer])
        # `contradiction` is the objective finding (a figure absent from the
        # source). `polarity_conflicts` is the heuristic one, and since 1.8.2
        # it no longer vetoes an answer -- it was wrong too often for that.
        # It is still the best signal available HERE, because the consequence
        # here is "put this in front of the owner", not "throw the answer
        # away". A signal may raise a flag; it may not pass a sentence.
        if not (report.contradiction or report.polarity_conflicts):
            continue
        detail = report.findings[0] if report.findings else "the two answers disagree"
        check.conflicts.append(
            Conflict(
                solution_id=solution.id,
                question=solution.question,
                score=score,
                detail=detail,
            )
        )
    return check
