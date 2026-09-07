"""Data classification.

Every request carries a classification. It comes from one of three places, in
descending order of authority:

1. What the calling client explicitly declared. A client may raise the
   classification of its own request but never lower it below its configured
   floor.
2. The client's configured default.
3. What the detector infers from the content.

The detector is a *floor*, not a ceiling: it can only push a request to a more
sensitive class, never a less sensitive one. A pattern matcher that could
declassify data would be a hole, not a feature.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.database.enums import Classification


@dataclass
class DetectionHit:
    kind: str
    count: int
    classification: Classification


@dataclass
class ClassificationResult:
    classification: Classification
    declared: Classification | None
    detected: Classification
    hits: list[DetectionHit] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "classification": self.classification.value,
            "declared": self.declared.value if self.declared else None,
            "detected": self.detected.value,
            # Kinds and counts only. The matched values are never recorded.
            "hits": [{"kind": h.kind, "count": h.count} for h in self.hits],
        }


# Patterns that mark content as sensitive. Each maps to the LOWEST class the
# content may hold. Ordering within the file does not matter; the maximum wins.
DETECTORS: list[tuple[str, re.Pattern[str], Classification]] = [
    # Credentials and keys — always RESTRICTED.
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"), Classification.RESTRICTED),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}"), Classification.RESTRICTED),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), Classification.RESTRICTED),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), Classification.RESTRICTED),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{6,}"), Classification.RESTRICTED),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}"), Classification.RESTRICTED),
    ("api_key_assignment", re.compile(r"(?i)\b(api[_-]?key|secret|password|passwd)\s*[:=]\s*\S{6,}"), Classification.RESTRICTED),
    ("db_url", re.compile(r"(?i)\b(postgres|postgresql|mysql|mongodb)(\+\w+)?://[^\s:]+:[^\s@]+@"), Classification.RESTRICTED),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"), Classification.RESTRICTED),
    ("card_number", re.compile(r"\b(?:\d[ -]?){13,19}\b"), Classification.RESTRICTED),
    # Personal data — confidential.
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]{2,}\b"), Classification.CONFIDENTIAL),
    ("phone", re.compile(r"(?<![\w.])\+?\d[\d ()\-]{8,17}\d(?![\w.])"), Classification.CONFIDENTIAL),
    ("pl_nip", re.compile(r"\bNIP[:\s]*\d{10}\b", re.IGNORECASE), Classification.CONFIDENTIAL),
    ("pl_pesel", re.compile(r"\bPESEL[:\s]*\d{11}\b", re.IGNORECASE), Classification.CONFIDENTIAL),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), Classification.CONFIDENTIAL),
    ("ip_address", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), Classification.INTERNAL),
]

# A card-number-shaped run of digits is a common false positive (order ids,
# long integers). Luhn is applied before the hit counts.
_CARD_KINDS = {"card_number"}


def _luhn_ok(value: str) -> bool:
    digits = [int(c) for c in value if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def detect(text: str) -> tuple[Classification, list[DetectionHit]]:
    """Return the minimum classification the text requires, and why."""
    hits: list[DetectionHit] = []
    highest = Classification.PUBLIC
    if not text:
        return highest, hits
    for kind, pattern, level in DETECTORS:
        matches = pattern.findall(text)
        if kind in _CARD_KINDS:
            matches = [m if isinstance(m, str) else "".join(m) for m in matches]
            matches = [m for m in matches if _luhn_ok(m)]
        if not matches:
            continue
        hits.append(DetectionHit(kind=kind, count=len(matches), classification=level))
        if level.rank > highest.rank:
            highest = level
    return highest, hits


def classify(
    text: str,
    *,
    declared: Classification | str | None = None,
    client_default: Classification | str | None = None,
) -> ClassificationResult:
    detected, hits = detect(text)

    declared_enum: Classification | None = None
    if declared is not None:
        declared_enum = Classification(str(declared).upper())

    default_enum = (
        Classification(str(client_default).upper()) if client_default else Classification.INTERNAL
    )

    # Start from the client's default, then take the most sensitive of
    # {default, declared, detected}. Nothing here can lower a classification.
    final = default_enum
    for candidate in (declared_enum, detected):
        if candidate is not None and candidate.rank > final.rank:
            final = candidate

    return ClassificationResult(
        classification=final, declared=declared_enum, detected=detected, hits=hits
    )


def may_leave_system(
    classification: Classification,
    *,
    allowed: set[str],
    client_max: Classification | str | None = None,
) -> tuple[bool, str]:
    """The single gate for 'can this go to an external provider?'.

    RESTRICTED is refused unconditionally, before any configuration is read.
    """
    if classification is Classification.RESTRICTED:
        return False, "RESTRICTED data may never be sent to an external provider"
    if classification.value not in allowed:
        return False, (
            f"{classification.value} is not in the externally-allowed set "
            f"({', '.join(sorted(allowed)) or 'none'})"
        )
    if client_max is not None:
        ceiling = Classification(str(client_max).upper())
        if classification.rank > ceiling.rank:
            return False, (
                f"{classification.value} exceeds this client's external ceiling "
                f"of {ceiling.value}"
            )
    return True, ""
