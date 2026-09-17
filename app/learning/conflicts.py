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

Web research made a third case matter. A researched answer about a moving
number -- a price, a rate, a date -- is *similar* to the stored one and is not
a copy of it: it is the same fact, later. Treating it as a duplicate throws the
newer fact away; treating it as new leaves two answers to the same question.
It is an UPDATE, and an update to promoted knowledge is a human's decision, not
a capture path's. So the answer is not one flag but one of four:

    NEW            nothing stored is close enough to be about this
    DUPLICATE      already known, and says the same thing. Do not store.
    UPDATE         about something already known, with different figures.
                   Store, hold for approval, never overwrite.
    CONTRADICTION  cannot both be true. Store, flag, human decides.

Precedence runs CONTRADICTION > UPDATE > DUPLICATE > NEW, and the order is
chosen for which mistake costs more. Over-calling UPDATE leaves an extra row
waiting for a person; over-calling DUPLICATE silently discards a newer fact,
and nobody ever finds out it happened.

Nothing here overwrites, edits or supersedes a promoted row. The strongest
thing a check can do is store a candidate and put it in front of the owner.

Deterministic throughout (Iron Rule 2): vector similarity over an index that
already exists, `factuality_check`, which is text analysis, and a regex over
figures. No model is asked to judge anything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from app.database.models import SolutionCandidate
from app.validation.factuality import check as factuality_check


class KnowledgeRelation(StrEnum):
    """How a candidate stands to what is already promoted."""

    NEW = "new"
    DUPLICATE = "duplicate"
    UPDATE = "update"
    CONTRADICTION = "contradiction"


# Only DUPLICATE is a reason not to store. The other three are all stored, and
# two of them are stored *because* a person needs to see them.
_STORE = {
    KnowledgeRelation.NEW: True,
    KnowledgeRelation.DUPLICATE: False,
    KnowledgeRelation.UPDATE: True,
    KnowledgeRelation.CONTRADICTION: True,
}
_NEEDS_HUMAN = {KnowledgeRelation.UPDATE, KnowledgeRelation.CONTRADICTION}

# Figures: a digit run, optionally with thousands separators and decimals.
# Normalised through float so that 4,271 / 4271 / 4271.0 are one figure and
# not three, which would make every reworded copy look like an update.
_FIGURE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def figures(text: str) -> set[str]:
    """The numeric facts in a piece of text.

    This is the whole of the UPDATE test, and it is deliberately blunt: it
    cannot tell a price from a port number, so it errs toward calling a
    difference an update and asking a person. The alternative -- judging which
    numbers *matter* -- is a judgement, and a judgement made here would be made
    by a model, which Iron Rule 2 forbids in a control decision.
    """
    found: set[str] = set()
    for raw in _FIGURE.findall(text or ""):
        try:
            value = float(raw.replace(",", ""))
        except ValueError:  # pragma: no cover - the regex cannot produce this
            continue
        found.add(f"{value:g}")
    return found


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
    changed_figures: list[str] = field(default_factory=list)
    """Figures present in one of the two answers and not the other."""

    @property
    def relation(self) -> KnowledgeRelation:
        """One of four, in the order of what a wrong call costs.

        A contradiction outranks everything: two answers that cannot both be
        true is the finding, whatever else is also true of them. Then UPDATE,
        because losing a newer fact is worse than holding a redundant row for
        approval. DUPLICATE is the narrowest claim of the four -- close enough
        to something stored AND carrying no figure that stored answer lacks --
        and it is the only one that discards anything.
        """
        if self.conflicts:
            return KnowledgeRelation.CONTRADICTION
        if self.duplicate is None:
            return KnowledgeRelation.NEW
        if self.changed_figures:
            return KnowledgeRelation.UPDATE
        return KnowledgeRelation.DUPLICATE

    @property
    def should_store(self) -> bool:
        return _STORE[self.relation]

    @property
    def requires_human(self) -> bool:
        """Whether promoted knowledge may not change without a person.

        An UPDATE is held exactly as a CONTRADICTION is. Neither ever edits
        the promoted row it relates to: the new one waits as a candidate and
        the old one keeps answering until someone says otherwise. Automatic
        promotion is off (AUTO_PROMOTE=false) and this does not reach past it.
        """
        return self.relation in _NEEDS_HUMAN

    @property
    def is_duplicate(self) -> bool:
        return self.relation is KnowledgeRelation.DUPLICATE

    @property
    def has_conflict(self) -> bool:
        return bool(self.conflicts)

    def summary(self) -> str:
        """One line for a person reading /admin/solutions."""
        if self.relation is KnowledgeRelation.CONTRADICTION:
            return (
                f"disagrees with {len(self.conflicts)} promoted solution(s) — "
                "one of them is out of date"
            )
        if self.relation is KnowledgeRelation.UPDATE:
            return (
                "updates a promoted solution "
                f"(similarity {self.duplicate_score:.2f}); figures differ: "
                + ", ".join(self.changed_figures[:6])
            )
        if self.relation is KnowledgeRelation.DUPLICATE:
            return f"already known (similarity {self.duplicate_score:.2f})"
        return "new"

    def as_dict(self) -> dict:
        return {
            "relation": self.relation.value,
            "requires_human": self.requires_human,
            "related_to": self.duplicate.id if self.duplicate else None,
            "duplicate_of": (
                self.duplicate.id
                if self.duplicate and self.relation is KnowledgeRelation.DUPLICATE
                else None
            ),
            "duplicate_score": round(self.duplicate_score, 4),
            "changed_figures": self.changed_figures[:20],
            "conflicts": [c.as_dict() for c in self.conflicts],
            "summary": self.summary(),
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
        # The UPDATE test. Compared both ways: a figure the new answer has and
        # the stored one lacks is news, and so is a figure the stored one has
        # and the new one dropped -- the second is how a vaguer answer would
        # otherwise quietly pass as a copy of a precise one.
        check.changed_figures = sorted(
            figures(answer) ^ figures(check.duplicate.answer or "")
        )

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
