"""Application settings.

Every knob the operator can turn lives here and is driven by environment
variables. Nothing in this file may contain a secret default: paid providers
are OFF unless explicitly enabled, and budgets always have a finite value.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Published in this file and in .env.example, so it is a known value, not a
# secret. Production refuses to start with it (see the validator below).
DEFAULT_AUTH_SECRET = "change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("AI_HELPER_ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------ app
    APP_NAME: str = "AI Helper"
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: Literal["json", "console"] = "json"

    # ------------------------------------------------------------- services
    DATABASE_URL: str = "sqlite+pysqlite:///./ai_helper.db"
    QDRANT_URL: str = "http://qdrant:6333"
    QDRANT_API_KEY: str | None = None
    QDRANT_ENABLED: bool = True
    OLLAMA_URL: str = "http://ollama:11434"
    OLLAMA_ENABLED: bool = True
    N8N_URL: str | None = "http://n8n:5678"

    # -------------------------------------------------------------- models
    DEFAULT_LOCAL_MODEL: str = "llama3.2:3b"
    SMALL_LOCAL_MODEL: str = "llama3.2:1b"
    STRONG_LOCAL_MODEL: str = "qwen2.5:7b"
    EMBEDDING_MODEL: str = "nomic-embed-text"
    EMBEDDING_DIM: int = 768
    LOCAL_TIMEOUT_SECONDS: float = 60.0
    LOCAL_MAX_TOKENS: int = 1024

    # ----------------------------------------------------- paid providers
    # Disabled by default. This is a hard requirement, not a preference.
    OPENAI_ENABLED: bool = False
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"

    ANTHROPIC_ENABLED: bool = False
    ANTHROPIC_API_KEY: str | None = None
    ANTHROPIC_MODEL: str = "claude-sonnet-5"
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com/v1"

    PAID_PROVIDER_ORDER: str = "anthropic,openai"
    PAID_TIMEOUT_SECONDS: float = 90.0
    PAID_MAX_TOKENS: int = 2048

    # -------------------------------------------------------- cost control
    AI_DAILY_API_BUDGET: float = 5.00
    AI_MONTHLY_API_BUDGET: float = 50.00
    AI_MAX_COST_PER_REQUEST: float = 0.50
    AI_MAX_INPUT_TOKENS_PER_REQUEST: int = 24_000
    # Task types that may NEVER escalate to a paid provider (comma separated).
    PAID_TASK_DENYLIST: str = ""

    # ---------------------------------------------------------- escalation
    CONFIDENCE_THRESHOLD: float = 0.62
    ESCALATION_ENABLED: bool = True
    ALLOW_USER_REQUESTED_PREMIUM: bool = False

    # ------------------------------------------------------------- privacy
    # Classifications that may be sent to an external provider.
    # RESTRICTED is never in this list; the code enforces that independently.
    EXTERNAL_ALLOWED_CLASSIFICATIONS: str = "PUBLIC,INTERNAL"
    REDACT_BEFORE_ESCALATION: bool = True

    # ------------------------------------------------------------ security
    AUTH_SECRET: str = DEFAULT_AUTH_SECRET
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD_HASH: str | None = None
    SESSION_TTL_MINUTES: int = 720
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_BURST: int = 20
    MAX_REQUEST_CHARS: int = 32_000
    # NOTE: there is deliberately no ALLOW_ANONYMOUS setting. Every endpoint
    # except the health probes and the docs requires an API key, and that is
    # not configurable — a switch that appears to relax it, whether or not it
    # is wired up, is an invitation to relax it.

    # ------------------------------------------------------------- memory
    # Similarity thresholds. A semantic embedder and a lexical one live on
    # different scales — a real embedding model scores unrelated text around
    # 0.3-0.5, a hashed bag-of-words scores it near 0.0 — so one number cannot
    # serve both. The pair in use is chosen from the embedder that is active.
    #
    # Measured on nomic-embed-text (2026-09-09, audit/REAL_MODEL_GATE.md):
    # a question scores its own paraphrase 0.57-0.97 (median 0.85), but the
    # DOCUMENT CHUNK that answers it only 0.47-0.69 (median 0.59) — a short
    # question against a long multi-fact passage is asymmetric retrieval and
    # sits lower than question-to-question. Unrelated text reaches 0.44
    # question-to-question and 0.57 (p90 0.49) against an unrelated chunk. At
    # the former default of 0.72 no handbook chunk was ever retrieved (0/10)
    # and memory items were missed (4/6), so document QA could not work at
    # all. 0.55 retrieves 8/10 chunks and every measured paraphrase, admits
    # 2/56 unrelated chunks — and an admitted wrong chunk is evidence the model
    # declines (a veto, then escalation), never an answer served.
    MEMORY_SIMILARITY_THRESHOLD: float = 0.55
    # Reuse serves a learned answer AS the answer, so it stays far stricter.
    # It cannot be validated as a separator on cosine alone — a one-detail
    # variant of a learned question scores like a paraphrase — and lowering it
    # admits more of those for almost no paraphrase gained; `calibrate` reports
    # that admission on every run. Do not lower it to buy recall.
    SOLUTION_REUSE_THRESHOLD: float = 0.80
    # Measured on the hashing embedder over a sample of question/passage
    # pairs: genuinely related pairs score 0.18-0.40, unrelated pairs 0.00-0.11.
    # 0.15 sits in that gap. Re-measure before changing it — a threshold set by
    # taste rather than by the distribution either drops real matches or admits
    # noise, and both cost money at the escalation step.
    LEXICAL_MEMORY_SIMILARITY_THRESHOLD: float = 0.15
    # Reuse is a stronger claim than retrieval (the stored answer is offered as
    # the answer), so it keeps a wider margin, and is corroborated by lexical
    # overlap in Retriever._similar_solutions before it is acted on.
    LEXICAL_SOLUTION_REUSE_THRESHOLD: float = 0.55
    MEMORY_TOP_K: int = 5
    KNOWLEDGE_TOP_K: int = 5
    CHUNK_SIZE: int = 900
    CHUNK_OVERLAP: int = 150
    MAX_UPLOAD_BYTES: int = 20 * 1024 * 1024

    # ----------------------------------------------------------- learning
    PROMOTION_REQUIRES_REPRODUCTION: bool = True
    PROMOTION_MIN_CONFIDENCE: float = 0.70
    AUTO_PROMOTE: bool = False
    SOLUTION_TTL_DAYS: int = 180

    # --------------------------------------------------------------- tools
    TOOLS_ENABLED: bool = True
    WEB_SEARCH_ENABLED: bool = False
    WEB_SEARCH_URL: str | None = None
    WEB_SEARCH_API_KEY: str | None = None

    # ---------------------------------------------------------- workers
    WORKER_CONCURRENCY: int = 2

    @model_validator(mode="after")
    def _production_must_not_run_on_defaults(self) -> Settings:
        """Refuse to start a production deployment on placeholder secrets.

        AUTH_SECRET signs the admin session cookie. Its default is published in
        this file and in .env.example, so a production instance still carrying
        it can have an admin session forged by anyone who has read the repo.
        A warning in a log nobody reads is not a control; refusing to start is.
        """
        if self.ENVIRONMENT != "production":
            return self
        problems: list[str] = []
        if self.AUTH_SECRET in (DEFAULT_AUTH_SECRET, "", None) or len(self.AUTH_SECRET) < 32:
            problems.append(
                "AUTH_SECRET is the placeholder or is shorter than 32 characters — "
                "an admin session cookie signed with it can be forged. "
                "Generate one with: openssl rand -hex 32"
            )
        if self.DEBUG:
            problems.append("DEBUG must be false in production")
        if problems:
            raise ValueError(
                "refusing to start in production:\n  - " + "\n  - ".join(problems)
            )
        return self

    @field_validator("EXTERNAL_ALLOWED_CLASSIFICATIONS")
    @classmethod
    def _no_restricted_externally(cls, v: str) -> str:
        parts = [p.strip().upper() for p in v.split(",") if p.strip()]
        if "RESTRICTED" in parts:
            raise ValueError(
                "RESTRICTED may never be listed in EXTERNAL_ALLOWED_CLASSIFICATIONS"
            )
        return ",".join(parts)

    # ------------------------------------------------------------ derived
    @property
    def external_allowed(self) -> set[str]:
        return {
            p.strip().upper()
            for p in self.EXTERNAL_ALLOWED_CLASSIFICATIONS.split(",")
            if p.strip()
        }

    @property
    def paid_provider_order(self) -> list[str]:
        return [p.strip().lower() for p in self.PAID_PROVIDER_ORDER.split(",") if p.strip()]

    @property
    def paid_task_denylist(self) -> set[str]:
        return {p.strip().lower() for p in self.PAID_TASK_DENYLIST.split(",") if p.strip()}

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    def any_paid_provider_configured(self) -> bool:
        return bool(
            (self.OPENAI_ENABLED and self.OPENAI_API_KEY)
            or (self.ANTHROPIC_ENABLED and self.ANTHROPIC_API_KEY)
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Used by tests after mutating the environment."""
    get_settings.cache_clear()
