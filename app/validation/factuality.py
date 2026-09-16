"""Grounding and contradiction checks against retrieved context.

Honest scope, because this is where a validation layer is most tempted to
overclaim: without a second model there is no way to *verify* a free-text
answer. What is computable cheaply and deterministically is:

* **Grounding** — how much of the answer's substantive vocabulary actually
  appears in the retrieved context. Low grounding when context was supplied
  means the model went beyond its evidence.
* **Numeric contradiction** — numbers asserted in the answer that appear
  nowhere in the context. When a question is answered *from* documents, a
  number the documents do not contain is the classic hallucination.
* **Polarity contradiction** — the answer asserts X where the context asserts
  not-X for the same short phrase.

These are signals, not verdicts. They feed the confidence score, and low
confidence causes escalation rather than a claim of falsehood.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "than", "that", "this", "these", "those",
    "is", "are", "was", "were", "be", "been", "being", "am", "do", "does", "did", "have", "has",
    "had", "having", "can", "could", "should", "would", "will", "shall", "may", "might", "must",
    "of", "in", "on", "at", "to", "for", "with", "from", "by", "as", "into", "about", "over",
    "it", "its", "they", "them", "their", "he", "she", "you", "your", "we", "our", "i", "me",
    "not", "no", "yes", "so", "such", "there", "here", "what", "which", "who", "whom", "when",
    "where", "why", "how", "all", "any", "both", "each", "few", "more", "most", "other", "some",
    "only", "own", "same", "very", "just", "also", "up", "out", "down", "between",
}

_WORD = re.compile(r"[A-Za-zÀ-ž0-9_]+")
_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:[.,]\d+)?(?![\w])")
_NEGATION = re.compile(r"\b(?:not|never|no|cannot|can't|isn't|aren't|doesn't|don't|won't)\b", re.I)


def tokens(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text or "")]


def content_tokens(text: str) -> set[str]:
    return {w for w in tokens(text) if w not in STOPWORDS and len(w) > 2}


def numbers(text: str) -> set[str]:
    """Normalised numeric literals ('1,5' and '1.5' compare equal; '5.0' == '5')."""
    out = set()
    for raw in _NUMBER.findall(text or ""):
        value = raw.replace(",", ".")
        try:
            number = float(value)
        except ValueError:
            continue
        out.add(str(int(number)) if number == int(number) else str(number))
    return out


@dataclass
class FactualityReport:
    context_available: bool
    grounding: float = 0.0          # 0..1, fraction of answer vocabulary in context
    ungrounded_terms: list[str] = field(default_factory=list)
    unsupported_numbers: list[str] = field(default_factory=list)
    polarity_conflicts: list[str] = field(default_factory=list)
    contradiction: bool = False
    findings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "context_available": self.context_available,
            "grounding": round(self.grounding, 3),
            "ungrounded_terms": self.ungrounded_terms[:10],
            "unsupported_numbers": self.unsupported_numbers[:10],
            "polarity_conflicts": self.polarity_conflicts[:5],
            "contradiction": self.contradiction,
            "findings": list(self.findings),
        }


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text or "") if s.strip()]


def check(
    answer: str,
    context_texts: list[str] | None = None,
    *,
    question: str = "",
    strict_numbers: bool = False,
) -> FactualityReport:
    context_texts = [c for c in (context_texts or []) if c and c.strip()]
    report = FactualityReport(context_available=bool(context_texts))

    if not report.context_available:
        # Nothing to ground against. Grounding is reported as unknown (0.0)
        # and the confidence model treats "no context" separately from
        # "context present and contradicted".
        return report

    context_blob = "\n".join(context_texts)
    context_words = content_tokens(context_blob) | content_tokens(question)
    answer_words = content_tokens(answer)

    if answer_words:
        overlap = answer_words & context_words
        report.grounding = len(overlap) / len(answer_words)
        report.ungrounded_terms = sorted(answer_words - context_words)[:25]
    else:
        report.grounding = 0.0

    context_numbers = numbers(context_blob) | numbers(question)
    answer_numbers = numbers(answer)
    unsupported = sorted(answer_numbers - context_numbers)
    if unsupported:
        report.unsupported_numbers = unsupported
        if strict_numbers:
            report.contradiction = True
            report.findings.append(
                "answer asserts numbers absent from the source: " + ", ".join(unsupported[:5])
            )
        else:
            report.findings.append(
                "answer contains numbers not present in the context: " + ", ".join(unsupported[:5])
            )

    # Polarity: the same 3+ content-word phrase asserted positively in one
    # place and negatively in the other. A conflict is when the context
    # asserts the phrase ONLY with the opposite polarity: a source that says
    # both "a stale bias is invalid" and "a stale bias is not neutral" agrees
    # with an answer that quotes either sentence, and flagging that faithful
    # answer as a contradiction would reject exactly the answers grounded
    # best (found while seeding the knowledge pack, 2026-09-16).
    context_sentences = [(content_tokens(c), bool(_NEGATION.search(c))) for c in _sentences(context_blob)]
    for sentence in _sentences(answer):
        sentence_words = content_tokens(sentence)
        if len(sentence_words) < 3:
            continue
        answer_negated = bool(_NEGATION.search(sentence))
        agreeing = False
        opposing: set[str] | None = None
        for context_words_, context_negated in context_sentences:
            shared = sentence_words & context_words_
            if len(shared) < 3:
                continue
            if answer_negated == context_negated:
                agreeing = True
                break
            if opposing is None:
                opposing = shared
        if opposing is not None and not agreeing:
            report.polarity_conflicts.append(" ".join(sorted(opposing)[:4]))
    if report.polarity_conflicts:
        # A SIGNAL, NOT A VERDICT. This used to set `contradiction`, which is a
        # veto, and on 2026-09-16 it failed the first complete plan answer the
        # system ever produced. The pack says "MISSING NEWS is not low risk, it
        # is UNKNOWN"; the answer said "news risk is LOW" about a reading
        # fetched seconds earlier. Shared words: low, news, risk. One sentence
        # negated, one not -- so the check called it a contradiction, when the
        # two sentences are about different subjects and both are true.
        #
        # A bag of shared content words cannot see the subject of a sentence,
        # and no threshold fixes that: it is the wrong kind of evidence for the
        # claim. So polarity now costs confidence, heavily, and names what it
        # saw. A NUMERIC contradiction stays a veto -- "this figure is not in
        # the source" is objective, and objective findings may veto.
        report.findings.append(
            "answer and context may disagree in polarity on: "
            + "; ".join(report.polarity_conflicts[:3])
            + " (word-overlap heuristic; it cannot tell two subjects apart)"
        )
        report.grounding = min(report.grounding, 0.35)
    return report
