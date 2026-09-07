"""Request and response models for the public API.

These are the contract future applications integrate against, so they are
explicit and additive: new optional fields may be added, existing ones are
never renamed or repurposed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=32_000)
    task_type: str | None = Field(
        default=None,
        description="Override the classifier: general, document_qa, summarization, …",
    )
    agent: str | None = Field(default=None, description="general, research, document, developer")
    conversation_id: str | None = None
    document_ids: list[str] = Field(default_factory=list, max_length=50)
    namespace: str | None = Field(default=None, max_length=120)
    classification: Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"] | None = Field(
        default=None,
        description="Raise the sensitivity of this request. It can never be lowered here.",
    )
    response_format: Literal["text", "json"] = "text"
    model: str | None = Field(default=None, max_length=120)
    premium: bool = Field(
        default=False,
        description="Ask for a paid model directly. Honoured only if the deployment allows it.",
    )
    max_tokens: int | None = Field(default=None, ge=1, le=8192)
    user_ref: str | None = Field(default=None, max_length=120)
    store_conversation: bool = True
    source: str | None = Field(default=None, max_length=64)


class SourceRef(BaseModel):
    source: str
    ref: str
    score: float


class TokenCounts(BaseModel):
    input: int = 0
    output: int = 0


class ChatResponse(BaseModel):
    request_id: str
    answer: str
    route: str
    task_type: str
    classification: str
    provider: str | None = None
    model: str | None = None
    agent: str | None = None
    confidence: float | None = None
    memory_hit: bool = False
    tool_used: str | None = None
    escalation_reason: str | None = None
    escalation_blocked_reason: str | None = None
    cost_usd: float = 0.0
    latency_ms: int = 0
    tokens: TokenCounts = Field(default_factory=TokenCounts)
    conversation_id: str | None = None
    solution_id: str | None = None
    success: bool = True
    sources: list[SourceRef] = Field(default_factory=list)
    validation: dict = Field(default_factory=dict)
    retrieval: dict = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class TaskRequest(ChatRequest):
    """A chat request that is run in the background."""

    model_config = ConfigDict(extra="forbid")


class TaskCreated(BaseModel):
    task_id: str
    status: str
    kind: str


class TaskStatus(BaseModel):
    task_id: str
    kind: str
    status: str
    progress: float = 0.0
    result: dict | None = None
    error: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class DocumentOut(BaseModel):
    id: str
    filename: str
    namespace: str
    mime_type: str
    size_bytes: int
    status: str
    chunk_count: int
    classification: str
    error: str | None = None
    created_at: datetime | None = None


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    chunks: int
    indexed: int
    duplicate: bool = False
    size_bytes: int = 0


class MemoryWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=8000)
    source: str = Field(min_length=1, max_length=120)
    confidence: float = Field(ge=0.0, le=1.0)
    kind: Literal["fact", "preference", "solution", "note"] = "fact"
    sensitivity: Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"] = "INTERNAL"
    key: str | None = Field(default=None, max_length=200)
    namespace: str | None = Field(default=None, max_length=120)
    owner_ref: str | None = Field(default=None, max_length=120)
    ttl_days: int | None = Field(default=None, ge=1, le=3650)
    meta: dict = Field(default_factory=dict)


class MemoryOut(BaseModel):
    id: str
    kind: str
    content: str
    source: str
    confidence: float
    status: str
    sensitivity: str
    namespace: str
    key: str | None = None
    expires_at: datetime | None = None
    created_at: datetime | None = None


class MemorySearchResult(BaseModel):
    query: str
    hits: list[dict]
    embedder: str
    semantic: bool


class ModelOut(BaseModel):
    name: str
    installed: bool
    resolved_to: str | None = None
    role: str


class ModelsResponse(BaseModel):
    local_available: bool
    models: list[ModelOut]
    embedder: str
    embedder_semantic: bool
    providers: list[dict]


class ComponentHealth(BaseModel):
    name: str
    status: str
    detail: str = ""


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    components: list[ComponentHealth]
    checked_at: datetime


class UsageResponse(BaseModel):
    window_days: int
    total_requests: int
    local_requests: int
    tool_requests: int
    memory_requests: int
    api_fallback_requests: int
    failed_requests: int
    fallback_percentage: float
    local_success_rate: float
    answered_locally: int
    memory_hits: int
    promoted_solutions: int
    rejected_solutions: int
    candidate_solutions: int
    escalation_reasons: list[dict]
    estimated_money_saved_usd: float
    api_cost_today: float
    api_cost_month: float


class CostResponse(BaseModel):
    spent_today: float
    spent_this_month: float
    daily_budget: float
    monthly_budget: float
    daily_remaining: float
    monthly_remaining: float
    calls_today: int
    calls_this_month: int
    paid_disabled_by_budget: bool
    by_provider: list[dict]
    by_escalation_reason: list[dict]


class SolutionOut(BaseModel):
    id: str
    question: str
    task_type: str
    status: str
    status_reason: str | None = None
    provider: str
    model: str
    confidence: float
    failure_reason: str | None = None
    reuse_count: int = 0
    created_at: datetime | None = None
    promoted_at: datetime | None = None


class ErrorResponse(BaseModel):
    error: str
    code: str
    detail: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None
