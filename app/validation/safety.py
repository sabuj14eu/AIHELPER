"""Safety checks on input and output.

Scope, stated plainly: this is a guard against the failure modes this system
can actually create — a prompt trying to redirect the assistant, a secret
leaking into an answer, and a model claiming it performed an action it has no
ability to perform. It is not a content-moderation system and does not pretend
to be one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.database.enums import Classification, RiskLevel
from app.privacy.classification import DETECTORS

# Attempts to override the system prompt or exfiltrate it. Detection is
# advisory: the real defence is that retrieved text is fenced and the system
# prompt says never to obey it (see app/local_ai/prompts.py).
INJECTION_PATTERNS = [
    re.compile(r"(?i)\bignore (?:all |any )?(?:the )?(?:previous|prior|above|earlier) (?:instructions|prompts|rules)"),
    re.compile(r"(?i)\bdisregard (?:the )?(?:system|previous) (?:prompt|instructions)"),
    re.compile(r"(?i)\b(?:reveal|print|show|output|repeat) (?:me )?(?:your|the) (?:system )?(?:prompt|instructions)"),
    re.compile(r"(?i)\byou are now\b.{0,40}\b(?:DAN|jailbroken|unrestricted|developer mode)"),
    re.compile(r"(?i)\bnew (?:system )?instructions?\s*:"),
    re.compile(r"(?i)</?(?:system|assistant)>"),
    re.compile(r"(?i)\bpretend (?:that )?you (?:are|have) no (?:rules|restrictions|guidelines)"),
]

# The system is advisory-first (work order §21). A model claiming it acted is
# a correctness failure worth flagging.
# "I", optionally contracted or with an auxiliary: I / I've / I have / I already.
_I_DID = r"(?i)\bI(?:'ve|\s+have)?(?:\s+(?:already|just|now))?\s+"

ACTION_CLAIM_PATTERNS = [
    re.compile(_I_DID + r"(?:deleted|dropped|removed|purged|wiped)\s+(?:the\s+|your\s+)?\w+"),
    re.compile(_I_DID + r"(?:sent|emailed|submitted|filed|posted|published|deployed|uploaded)\b"),
    re.compile(_I_DID + r"(?:executed|ran|run)\s+(?:the\s+)?(?:command|script|query|migration)\b"),
    re.compile(_I_DID + r"(?:placed|cancelled|canceled|modified|amended)\s+(?:the\s+|your\s+)?(?:order|trade|booking|payment)\b"),
    re.compile(_I_DID + r"(?:updated|changed|written|wrote|saved)\s+(?:the\s+|your\s+)?(?:database|record|file|record)\b"),
    re.compile(r"(?i)\btransaction (?:has been )?completed\b"),
]

_SECRET_DETECTORS = [
    (kind, pattern)
    for kind, pattern, level in DETECTORS
    if level is Classification.RESTRICTED
]


@dataclass
class SafetyReport:
    ok: bool = True
    risk: RiskLevel = RiskLevel.LOW
    injection_suspected: bool = False
    action_claimed: bool = False
    leaked_secret_kinds: list[str] = field(default_factory=list)
    oversized: bool = False
    findings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "risk": self.risk.value,
            "injection_suspected": self.injection_suspected,
            "action_claimed": self.action_claimed,
            "leaked_secret_kinds": list(self.leaked_secret_kinds),
            "oversized": self.oversized,
            "findings": list(self.findings),
        }


def check_input(text: str, *, max_chars: int) -> SafetyReport:
    report = SafetyReport()
    if text is None:
        text = ""
    if len(text) > max_chars:
        report.oversized = True
        report.ok = False
        report.risk = RiskLevel.MEDIUM
        report.findings.append(f"input exceeds {max_chars} characters")
    if any(p.search(text) for p in INJECTION_PATTERNS):
        report.injection_suspected = True
        report.risk = RiskLevel.MEDIUM
        report.findings.append("possible prompt-injection phrasing in the request")
        # Not a hard block: a user may legitimately ask about prompt injection.
        # It is recorded, it raises the risk level, and it suppresses any
        # automatic promotion of the resulting answer into memory.
    return report


def check_output(text: str, *, context_texts: list[str] | None = None) -> SafetyReport:
    report = SafetyReport()
    text = text or ""

    leaked: list[str] = []
    for kind, pattern in _SECRET_DETECTORS:
        if pattern.search(text):
            leaked.append(kind)
    if leaked:
        report.leaked_secret_kinds = leaked
        report.ok = False
        report.risk = RiskLevel.HIGH
        report.findings.append(f"output contains credential-shaped values: {', '.join(sorted(set(leaked)))}")

    if any(p.search(text) for p in ACTION_CLAIM_PATTERNS):
        report.action_claimed = True
        report.ok = False
        report.risk = RiskLevel.HIGH
        report.findings.append(
            "output claims an action was performed; this system is advisory and performs none"
        )

    # An answer that reproduces injection phrasing found in retrieved context
    # means the context steered the model.
    if context_texts:
        joined = "\n".join(context_texts)
        if any(p.search(joined) for p in INJECTION_PATTERNS) and any(
            p.search(text) for p in INJECTION_PATTERNS
        ):
            report.injection_suspected = True
            report.ok = False
            report.risk = RiskLevel.HIGH
            report.findings.append("output echoes injection phrasing present in retrieved context")

    return report
