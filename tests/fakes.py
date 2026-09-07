"""Test doubles.

These simulate provider behaviour, not gateway behaviour: the routing,
validation, budget and learning logic under test is the real code in ``app/``.

:class:`FakeLocalProvider` models the single most important property of a
small local model — it can answer an easy question, and it cannot answer a
hard one *unless the answer is in front of it*. That is what makes the
cost-saving cycle a real test rather than a rigged one: the local model only
succeeds the second time because retrieval genuinely put the learned solution
into its prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.errors import ProviderTimeoutError, ProviderUnavailableError
from app.providers.base import (
    CompletionRequest,
    CompletionResponse,
    HealthStatus,
    Provider,
    estimate_tokens,
)

HARD_MARKER = "ZUS health contribution look-back"


@dataclass
class FakeLocalProvider(Provider):
    """A local model that is only as good as its context."""

    name: str = "ollama"
    kind: str = "local"
    model: str = "fake-local:1b"
    installed: bool = True
    timeout: bool = False
    unavailable: bool = False
    # Questions containing any of these strings cannot be answered without help.
    hard_topics: list[str] = field(default_factory=lambda: [HARD_MARKER])
    calls: list[CompletionRequest] = field(default_factory=list)
    answer_override: str | None = None

    @property
    def enabled(self) -> bool:
        return True

    def default_model(self) -> str:
        return self.model

    def resolve_model(self, task_type, requested=None):
        return self.model if self.installed else None

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        self.calls.append(request)
        if self.unavailable:
            raise ProviderUnavailableError("fake local model is not running")
        if self.timeout:
            raise ProviderTimeoutError("fake local model timed out")

        prompt = "\n".join(m.content for m in request.messages)
        user_text = next((m.content for m in reversed(request.messages) if m.role == "user"), "")

        if self.answer_override is not None:
            text = self.answer_override
        elif any(topic.lower() in user_text.lower() for topic in self.hard_topics):
            has_context = "<<<CONTEXT" in user_text
            if has_context:
                # With the solution in the prompt, the small model can restate it.
                text = _quote_context(user_text)
            else:
                text = "INSUFFICIENT_CONTEXT — I do not have the rules for this."
        else:
            text = _easy_answer(user_text)

        return CompletionResponse(
            text=text,
            provider=self.name,
            model=self.model,
            input_tokens=estimate_tokens(prompt),
            output_tokens=estimate_tokens(text),
            latency_ms=5,
            finish_reason="stop",
        )

    def health(self) -> HealthStatus:
        return HealthStatus(
            self.name,
            "local",
            available=self.installed and not self.unavailable,
            enabled=True,
            models=[self.model] if self.installed else [],
        )


@dataclass
class FakePaidProvider(Provider):
    """A strong external model. Records every call so tests can count them."""

    name: str = "anthropic"
    kind: str = "paid"
    model: str = "fake-paid-large"
    is_enabled: bool = True
    fail: bool = False
    calls: list[CompletionRequest] = field(default_factory=list)
    answer: str = (
        "Under the flat tax the health contribution for a month is 4.9% of the income of the "
        "month before it, and the contribution year runs from 1 February to 31 January, so "
        "January is settled on the previous year's figures."
    )
    cost_per_call: float = 0.0

    @property
    def enabled(self) -> bool:
        return self.is_enabled

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def default_model(self) -> str:
        return self.model

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        self.calls.append(request)
        if self.fail:
            raise ProviderUnavailableError("fake paid provider is down")
        prompt = "\n".join(m.content for m in request.messages)
        return CompletionResponse(
            text=self.answer,
            provider=self.name,
            model=self.model,
            input_tokens=estimate_tokens(prompt),
            output_tokens=estimate_tokens(self.answer),
            latency_ms=40,
            finish_reason="stop",
        )

    def health(self) -> HealthStatus:
        return HealthStatus(self.name, "paid", available=self.is_enabled, enabled=self.is_enabled)

    def estimate_cost(self, input_tokens: int, output_tokens: int, model: str | None = None) -> float:
        from app.cost.pricing import estimate_cost

        return estimate_cost("anthropic", model or self.model, input_tokens, output_tokens)


def _quote_context(user_text: str) -> str:
    """Pull the first context block out of the prompt and answer from it."""
    start = user_text.find("<<<CONTEXT")
    end = user_text.find("CONTEXT>>>", start)
    if start == -1 or end == -1:
        return "INSUFFICIENT_CONTEXT"
    block = user_text[start:end]
    lines = [line for line in block.splitlines()[1:] if line.strip()]
    body = " ".join(lines).strip()
    return f"Based on the stored answer: {body}"


def _easy_answer(user_text: str) -> str:
    lowered = user_text.lower()
    if "capital of france" in lowered:
        return "The capital of France is Paris."
    if "<<<CONTEXT" in user_text:
        return _quote_context(user_text)
    return "Here is a clear, complete answer to your question, stated plainly and in full."
