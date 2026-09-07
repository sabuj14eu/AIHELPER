"""Redaction before external escalation.

What this is: a mechanical reduction of the obvious identifiers before a
prompt leaves the building, so that an escalated CONFIDENTIAL-adjacent request
carries less than it otherwise would.

What this is NOT: a guarantee that redacted text is safe to send. A regex
cannot recognise that "the client on the third floor of the Warsaw office"
identifies someone. That is why RESTRICTED is blocked outright rather than
redacted, and why redaction is applied *in addition to* the classification
gate, never instead of it.

Redaction is reversible inside the process (a placeholder map is returned) so
the provider's answer can be re-hydrated for the caller. The map never leaves
the process and is never persisted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# (kind, pattern). Order matters: longer/structural patterns first, so an
# email is not half-eaten by the phone matcher.
REDACTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("KEY", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")),
    ("KEY", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("KEY", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}")),
    ("KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("TOKEN", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{6,}")),
    ("TOKEN", re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}")),
    ("DBURL", re.compile(r"(?i)\b(?:postgres|postgresql|mysql|mongodb)(?:\+\w+)?://[^\s:]+:[^\s@]+@\S+")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]{2,}\b")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("PESEL", re.compile(r"(?i)\bPESEL[:\s]*\d{11}\b")),
    ("NIP", re.compile(r"(?i)\bNIP[:\s]*\d{10}\b")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("PHONE", re.compile(r"(?<![\w.])\+?\d[\d ()\-]{8,17}\d(?![\w.])")),
    ("IP", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
]


@dataclass
class RedactionResult:
    text: str
    placeholders: dict[str, str] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def redacted(self) -> bool:
        return bool(self.placeholders)

    def restore(self, text: str) -> str:
        """Put the original values back into a provider's answer."""
        for token, original in self.placeholders.items():
            text = text.replace(token, original)
        return text

    def summary(self) -> dict:
        return {"redacted": self.redacted, "counts": dict(self.counts)}


def redact(text: str) -> RedactionResult:
    if not text:
        return RedactionResult(text="")
    placeholders: dict[str, str] = {}
    reverse: dict[str, str] = {}
    counts: dict[str, int] = {}

    def make_token(kind: str, value: str) -> str:
        if value in reverse:
            return reverse[value]
        counts[kind] = counts.get(kind, 0) + 1
        token = f"[{kind}_{counts[kind]}]"
        placeholders[token] = value
        reverse[value] = token
        return token

    out = text
    for kind, pattern in REDACTION_PATTERNS:
        out = pattern.sub(lambda m, k=kind: make_token(k, m.group(0)), out)
    return RedactionResult(text=out, placeholders=placeholders, counts=counts)
