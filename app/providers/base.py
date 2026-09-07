"""Provider abstraction.

The gateway talks to providers only through :class:`Provider`. It must remain
possible to add a provider without touching gateway code, and to delete one
without breaking the gateway.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Literal

ProviderKind = Literal["local", "paid"]


@dataclass
class Message:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass
class CompletionRequest:
    """Everything a provider needs, and nothing about how we chose it."""

    messages: list[Message]
    model: str | None = None
    max_tokens: int | None = None
    temperature: float = 0.2
    timeout: float | None = None
    stop: list[str] = field(default_factory=list)
    response_format: Literal["text", "json"] = "text"
    request_id: str | None = None

    def prompt_chars(self) -> int:
        return sum(len(m.content) for m in self.messages)


@dataclass
class CompletionResponse:
    text: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    finish_reason: str | None = None
    raw: dict = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class HealthStatus:
    name: str
    kind: ProviderKind
    available: bool
    enabled: bool
    detail: str = ""
    models: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "enabled": self.enabled,
            "available": self.available,
            "status": self._label(),
            "detail": self.detail,
            "models": self.models,
        }

    def _label(self) -> str:
        if not self.enabled:
            return "DISABLED"
        return "OK" if self.available else "UNAVAILABLE"


class Provider(abc.ABC):
    """A thing that can turn messages into text."""

    name: str = "provider"
    kind: ProviderKind = "local"

    @property
    def enabled(self) -> bool:
        return True

    @abc.abstractmethod
    def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Run a completion. Raises ProviderUnavailableError / ProviderTimeoutError."""

    @abc.abstractmethod
    def health(self) -> HealthStatus:
        """Cheap liveness probe. Must never raise."""

    def default_model(self) -> str:
        raise NotImplementedError

    def estimate_cost(self, input_tokens: int, output_tokens: int, model: str | None = None) -> float:
        """USD. Local providers are free by definition."""
        return 0.0


def estimate_tokens(text: str) -> int:
    """Rough token estimate used for budget pre-checks only.

    ~4 characters per token is the usual English approximation. It is used to
    decide whether a request MIGHT be too expensive; actual accounting always
    uses the token counts the provider reports.
    """
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)
