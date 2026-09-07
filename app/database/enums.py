"""Vocabulary shared by the database, the gateway and the API.

These strings appear in stored rows, so they are part of the contract:
add new members freely, never rename or repurpose an existing one.
"""

from __future__ import annotations

from enum import StrEnum


class TaskType(StrEnum):
    GENERAL = "general"
    ARITHMETIC = "arithmetic"
    DATE = "date"
    STRUCTURED_DATA = "structured_data"
    DOCUMENT_QA = "document_qa"
    SUMMARIZATION = "summarization"
    CLASSIFICATION = "classification"
    EXTRACTION = "extraction"
    RESEARCH = "research"
    CODE = "code"
    REASONING = "reasoning"


class Classification(StrEnum):
    """Sensitivity of the data in a request. Ordered least to most sensitive."""

    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"

    @property
    def rank(self) -> int:
        return _CLASSIFICATION_RANK[self]


_CLASSIFICATION_RANK = {
    Classification.PUBLIC: 0,
    Classification.INTERNAL: 1,
    Classification.CONFIDENTIAL: 2,
    Classification.RESTRICTED: 3,
}


class Route(StrEnum):
    """Which level of the local-first ladder produced the answer."""

    TOOL = "tool"              # level 0 — deterministic, zero tokens
    MEMORY = "memory"          # level 1 — served from stored knowledge
    LOCAL = "local"            # level 2 — local Ollama model
    PAID = "paid"              # level 4 — external provider
    FAILED = "failed"          # nothing produced an acceptable answer


class EscalationReason(StrEnum):
    """Exactly one of these is recorded for every paid API request.

    This is the field that answers 'why are we paying for AI?'.
    """

    LOCAL_MODEL_UNAVAILABLE = "LOCAL_MODEL_UNAVAILABLE"
    LOCAL_TIMEOUT = "LOCAL_TIMEOUT"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    VALIDATION_FAILURE = "VALIDATION_FAILURE"
    NO_KNOWLEDGE_FOUND = "NO_KNOWLEDGE_FOUND"
    TASK_TOO_COMPLEX = "TASK_TOO_COMPLEX"
    USER_REQUESTED_PREMIUM_MODEL = "USER_REQUESTED_PREMIUM_MODEL"


class EscalationBlockReason(StrEnum):
    """Why an escalation that was wanted did not happen."""

    NOT_CONFIGURED = "NOT_CONFIGURED"
    DISABLED = "DISABLED"
    DAILY_BUDGET_EXHAUSTED = "DAILY_BUDGET_EXHAUSTED"
    MONTHLY_BUDGET_EXHAUSTED = "MONTHLY_BUDGET_EXHAUSTED"
    REQUEST_COST_CAP = "REQUEST_COST_CAP"
    REQUEST_TOO_LARGE = "REQUEST_TOO_LARGE"
    CLASSIFICATION_BLOCKED = "CLASSIFICATION_BLOCKED"
    TASK_TYPE_DENIED = "TASK_TYPE_DENIED"
    CLIENT_NOT_PERMITTED = "CLIENT_NOT_PERMITTED"
    PROVIDER_FAILED = "PROVIDER_FAILED"


class SolutionStatus(StrEnum):
    CANDIDATE = "CANDIDATE"
    VALIDATED = "VALIDATED"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class MemoryStatus(StrEnum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class MemoryKind(StrEnum):
    FACT = "fact"
    PREFERENCE = "preference"
    SOLUTION = "solution"
    NOTE = "note"


class DocumentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
