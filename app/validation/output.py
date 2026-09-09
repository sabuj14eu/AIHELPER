"""Structural checks on a model's output.

These answer "did the model actually produce an answer, in the shape we
asked for?" — before anything tries to judge whether the answer is *right*.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.local_ai.prompts import INSUFFICIENT_MARKER

# The prompt asks for the literal INSUFFICIENT_MARKER, but a real small model
# does not reproduce it byte for byte: measured against llama3.2:3b it wrote
# "INSUFFICIENT CONTEXT" (a space, not an underscore) in 15 of 20 refusals, and
# an exact-string match let every one of those pass as an answer. Matching the
# two words with any separator, case-insensitively, catches the refusal the
# model actually emits; the marker's meaning does not depend on its spelling.
_INSUFFICIENT = re.compile(
    r"(?i)\b" + r"[\s_\-]*".join(re.escape(part) for part in INSUFFICIENT_MARKER.split("_")) + r"\b"
)

# Phrases a model emits when it is declining rather than answering.
REFUSAL_PATTERNS = [
    re.compile(r"(?i)\bI (?:can(?:no|')t|am unable to|cannot) (?:help|assist|answer|provide)"),
    re.compile(r"(?i)\bas an (?:AI|artificial intelligence)\b.{0,60}\b(?:cannot|can't|unable)"),
    re.compile(r"(?i)\bI (?:don'?t|do not) have (?:enough|sufficient|any) (?:information|context|data)"),
    re.compile(r"(?i)\bI'?m (?:not able|unable) to\b"),
    re.compile(r"(?i)\bno (?:relevant )?information (?:is )?(?:available|provided|found)\b"),
]

HEDGE_PATTERNS = [
    re.compile(r"(?i)\bI'?m not (?:sure|certain)\b"),
    re.compile(r"(?i)\bit'?s (?:hard|difficult) to say\b"),
    re.compile(r"(?i)\b(?:might|may|could) (?:be|possibly)\b"),
    re.compile(r"(?i)\bI (?:think|believe|guess)\b"),
    re.compile(r"(?i)\bwithout more (?:information|context|detail)\b"),
    re.compile(r"(?i)\bpresumably\b|\bprobably\b|\bpossibly\b"),
]


@dataclass
class OutputCheck:
    text: str
    empty: bool = False
    too_short: bool = False
    declared_insufficient: bool = False
    refused: bool = False
    truncated: bool = False
    repetitive: bool = False
    format_ok: bool = True
    format_error: str | None = None
    parsed: object | None = None
    hedge_count: int = 0
    word_count: int = 0
    failures: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        """A hard gate. If this is False the answer cannot be returned at all."""
        return not (
            self.empty
            or self.declared_insufficient
            or self.refused
            or not self.format_ok
            or self.repetitive
        )

    def as_dict(self) -> dict:
        return {
            "usable": self.usable,
            "empty": self.empty,
            "too_short": self.too_short,
            "declared_insufficient": self.declared_insufficient,
            "refused": self.refused,
            "truncated": self.truncated,
            "repetitive": self.repetitive,
            "format_ok": self.format_ok,
            "format_error": self.format_error,
            "hedge_count": self.hedge_count,
            "word_count": self.word_count,
            "failures": list(self.failures),
        }


def _extract_json(text: str) -> tuple[object | None, str | None]:
    stripped = text.strip()
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", stripped)
    if fence:
        stripped = fence.group(1).strip()
    try:
        return json.loads(stripped), None
    except json.JSONDecodeError as exc:
        # A model often wraps JSON in prose; try the outermost braces.
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(stripped[start : end + 1]), None
            except json.JSONDecodeError:
                pass
        return None, f"not valid JSON: {exc.msg}"


def _is_repetitive(text: str, min_words: int = 40) -> bool:
    """Detect a degenerate loop: the same 6-gram repeated many times."""
    words = text.split()
    if len(words) < min_words:
        return False
    grams: dict[tuple[str, ...], int] = {}
    for i in range(len(words) - 5):
        gram = tuple(words[i : i + 6])
        grams[gram] = grams.get(gram, 0) + 1
    if not grams:
        return False
    worst = max(grams.values())
    # Four or more repeats of an identical 6-gram is a loop, not emphasis.
    return worst >= 4


def check_output(
    text: str,
    *,
    response_format: str = "text",
    finish_reason: str | None = None,
    min_words: int = 1,
) -> OutputCheck:
    result = OutputCheck(text=text or "", word_count=len((text or "").split()))
    stripped = (text or "").strip()

    if not stripped:
        result.empty = True
        result.failures.append("empty_output")
        return result

    if _INSUFFICIENT.search(stripped):
        result.declared_insufficient = True
        result.failures.append("model_declared_insufficient_context")

    if any(p.search(stripped) for p in REFUSAL_PATTERNS):
        result.refused = True
        result.failures.append("model_refused")

    result.hedge_count = sum(len(p.findall(stripped)) for p in HEDGE_PATTERNS)

    if result.word_count < min_words:
        result.too_short = True
        result.failures.append("too_short")

    if finish_reason in ("length", "max_tokens"):
        result.truncated = True
        result.failures.append("truncated")

    if _is_repetitive(stripped):
        result.repetitive = True
        result.failures.append("repetitive_output")

    if response_format == "json":
        parsed, error = _extract_json(stripped)
        if error:
            result.format_ok = False
            result.format_error = error
            result.failures.append("format_json_invalid")
        else:
            result.parsed = parsed

    return result
