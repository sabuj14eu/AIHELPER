"""Question normalisation, fingerprinting and similarity.

Two mechanisms, used together:

* **Fingerprint** — a hash of the normalised question. Exact and cheap. It
  catches the literally-repeated question, which is the most common case and
  the one that must never be paid for twice. It is embedder-independent, so it
  keeps working when the embedding model changes.
* **Vector similarity** — catches the paraphrase. Its threshold depends on
  which embedder is running (see app/memory/thresholds.py).

Normalisation deliberately does NOT stem or drop negations: "is X allowed" and
"is X not allowed" must never collide into the same fingerprint.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")
# Only cosmetic punctuation is removed. Nothing that can flip meaning goes.
# En and em dashes are punctuation; the plain hyphen is NOT removed, because it
# is part of dates (2026-01-01) and of words (well-known) where deleting it
# would silently change the token.
_TRIM_PUNCT = re.compile(r"[\"'`´“”‘’()\[\]{}.,;:!?–—…]+")
# Leading pleasantries are stripped only when they cannot be part of the
# question itself. "please" is safe bare; a greeting is stripped only when it
# is set off by punctuation, so "Hello, what is X?" loses its greeting while
# "Hello world program in Python" keeps every word. Dropping a content word
# would fuse two different questions onto one fingerprint, which is the same
# class of mistake as normalising away a negation.
_FILLERS = re.compile(
    r"^\s*(?:please\b[\s,]*|(?:hi|hello|hey|ok|okay|so)\b\s*[,:;\-–—]+\s*)",
    re.IGNORECASE,
)


def normalise(text: str) -> str:
    """Lowercase, strip accents-preserving unicode form, squeeze whitespace."""
    if not text:
        return ""
    value = unicodedata.normalize("NFKC", text).strip().lower()
    value = _FILLERS.sub("", value)
    value = _TRIM_PUNCT.sub(" ", value)
    return _WHITESPACE.sub(" ", value).strip()


def fingerprint(text: str, *, salt: str = "") -> str:
    """Stable id for a normalised question, optionally scoped by client."""
    normalised = normalise(text)
    return hashlib.sha256(f"{salt}\x00{normalised}".encode()).hexdigest()[:32]


def jaccard(a: str, b: str) -> float:
    """Token-set overlap. A cheap sanity check independent of any embedder."""
    tokens_a = set(normalise(a).split())
    tokens_b = set(normalise(b).split())
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
