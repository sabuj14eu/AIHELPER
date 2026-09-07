"""Confidence scoring and the overall validation verdict.

The rule from the work order, restated because it is the whole design: an
LLM's self-reported confidence is not used, at all. Confidence here is
computed from observable properties of the exchange — structure, grounding,
retrieval quality, contradiction, tool agreement — and it is a *routing
signal*, not a claim of correctness.

Some signals are vetoes rather than weights. An empty answer, an invalid
requested format, a refusal, a safety violation or a detected contradiction
cannot be averaged away by good scores elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.database.enums import TaskType
from app.validation.factuality import FactualityReport
from app.validation.output import OutputCheck
from app.validation.safety import SafetyReport

# Weights sum to 1.0. Adjusting these changes escalation behaviour and
# therefore spend, so they live here as one visible block rather than being
# scattered through the router.
WEIGHTS = {
    "structure": 0.20,      # complete, non-truncated, non-repetitive, right format
    "decisiveness": 0.15,   # did not hedge its way out of answering
    "grounding": 0.30,      # answer vocabulary supported by retrieved context
    "retrieval": 0.20,      # quality of what retrieval found
    "tool_agreement": 0.15, # agrees with a deterministic computation, where one exists
}

# Task types where an ungrounded answer is a serious problem rather than
# normal behaviour: these are answers that are supposed to come from sources.
GROUNDING_REQUIRED = {TaskType.DOCUMENT_QA, TaskType.RESEARCH, TaskType.EXTRACTION}


@dataclass
class ValidationReport:
    passed: bool
    confidence: float
    signals: dict[str, float] = field(default_factory=dict)
    vetoes: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    output: dict = field(default_factory=dict)
    safety: dict = field(default_factory=dict)
    factuality: dict = field(default_factory=dict)
    threshold: float = 0.0

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "confidence": round(self.confidence, 3),
            "threshold": self.threshold,
            "signals": {k: round(v, 3) for k, v in self.signals.items()},
            "vetoes": list(self.vetoes),
            "findings": list(self.findings),
            "output": self.output,
            "safety": self.safety,
            "factuality": self.factuality,
        }

    @property
    def primary_failure(self) -> str | None:
        if self.vetoes:
            return self.vetoes[0]
        if not self.passed:
            return "low_confidence"
        return None


def _structure_signal(output: OutputCheck) -> float:
    score = 1.0
    if output.truncated:
        score -= 0.45
    if output.too_short:
        score -= 0.25
    if output.word_count < 3:
        score -= 0.15
    return max(0.0, min(1.0, score))


def _decisiveness_signal(output: OutputCheck) -> float:
    # Each hedge phrase costs; three or more and the model is not committing.
    return max(0.0, 1.0 - 0.25 * output.hedge_count)


def _grounding_signal(
    factuality: FactualityReport, task_type: TaskType, retrieval_score: float
) -> float:
    if not factuality.context_available:
        # No context was retrieved. For a task that is supposed to be answered
        # from sources this is a real deficiency; for general chat it is normal
        # and we neither reward nor punish it.
        return 0.15 if TaskType(task_type) in GROUNDING_REQUIRED else 0.6
    if factuality.contradiction:
        return 0.0
    # Grounding above ~0.55 is typical for a good answer that also uses
    # ordinary connective vocabulary; saturate there rather than demanding 1.0.
    return min(1.0, factuality.grounding / 0.55)


def _retrieval_signal(
    retrieval_score: float, task: TaskType, context_available: bool
) -> float:
    """Quality of what retrieval found.

    When nothing was retrieved the signal is neutral for ordinary chat — an
    everyday question has no documents behind it and must not be pushed to a
    paid provider for that reason alone — but near-zero for the task types
    that are supposed to be answered from sources.
    """
    if context_available:
        return max(0.0, min(1.0, retrieval_score))
    return 0.1 if task in GROUNDING_REQUIRED else 0.6


def _tool_agreement_signal(tool_value: str | None, answer: str) -> float:
    if tool_value is None:
        return 0.6  # no deterministic check available: neutral, not a bonus
    return 1.0 if str(tool_value).strip() and str(tool_value).strip() in (answer or "") else 0.0


def evaluate(
    answer: str,
    *,
    task_type: TaskType | str = TaskType.GENERAL,
    output: OutputCheck,
    safety: SafetyReport,
    factuality: FactualityReport,
    retrieval_score: float = 0.0,
    tool_value: str | None = None,
    threshold: float = 0.62,
) -> ValidationReport:
    try:
        task = TaskType(task_type)
    except ValueError:
        task = TaskType.GENERAL

    signals = {
        "structure": _structure_signal(output),
        "decisiveness": _decisiveness_signal(output),
        "grounding": _grounding_signal(factuality, task, retrieval_score),
        "retrieval": _retrieval_signal(retrieval_score, task, factuality.context_available),
        "tool_agreement": _tool_agreement_signal(tool_value, answer),
    }
    confidence = sum(WEIGHTS[name] * value for name, value in signals.items())

    vetoes: list[str] = []
    if output.empty:
        vetoes.append("empty_output")
    if output.declared_insufficient:
        vetoes.append("model_declared_insufficient_context")
    if output.refused:
        vetoes.append("model_refused")
    if not output.format_ok:
        vetoes.append("format_invalid")
    if output.repetitive:
        vetoes.append("repetitive_output")
    if not safety.ok:
        vetoes.append("safety_violation")
    if factuality.contradiction:
        vetoes.append("contradicts_context")
    if tool_value is not None and signals["tool_agreement"] == 0.0:
        vetoes.append("disagrees_with_deterministic_tool")

    findings = list(output.failures) + list(safety.findings) + list(factuality.findings)

    if vetoes:
        # A veto caps confidence rather than zeroing it, so the dashboard can
        # still distinguish "nearly right but contradicted" from "empty".
        confidence = min(confidence, 0.25)

    return ValidationReport(
        passed=not vetoes and confidence >= threshold,
        confidence=round(confidence, 4),
        signals=signals,
        vetoes=vetoes,
        findings=findings,
        output=output.as_dict(),
        safety=safety.as_dict(),
        factuality=factuality.as_dict(),
        threshold=threshold,
    )
