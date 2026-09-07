"""Anthropic provider. Disabled unless ANTHROPIC_ENABLED=true and a key is set."""

from __future__ import annotations

import time

import httpx

from app.core.config import Settings
from app.core.errors import ProviderTimeoutError, ProviderUnavailableError
from app.cost.pricing import estimate_cost
from app.providers.base import (
    CompletionRequest,
    CompletionResponse,
    HealthStatus,
    Provider,
    estimate_tokens,
)

ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(Provider):
    name = "anthropic"
    kind = "paid"

    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self._client = client

    @property
    def enabled(self) -> bool:
        return bool(self.settings.ANTHROPIC_ENABLED and self.settings.ANTHROPIC_API_KEY)

    def default_model(self) -> str:
        return self.settings.ANTHROPIC_MODEL

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.settings.ANTHROPIC_BASE_URL,
                timeout=self.settings.PAID_TIMEOUT_SECONDS,
            )
        return self._client

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        if not self.enabled:
            raise ProviderUnavailableError("Anthropic provider is disabled")
        model = request.model or self.default_model()
        # The Messages API takes the system prompt out of band.
        system_parts = [m.content for m in request.messages if m.role == "system"]
        turns = [
            {"role": m.role, "content": m.content}
            for m in request.messages
            if m.role in ("user", "assistant")
        ]
        if not turns:
            turns = [{"role": "user", "content": ""}]

        payload: dict = {
            "model": model,
            "messages": turns,
            "max_tokens": request.max_tokens or self.settings.PAID_MAX_TOKENS,
            "temperature": request.temperature,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        if request.stop:
            payload["stop_sequences"] = request.stop

        started = time.perf_counter()
        try:
            response = self._http().post(
                "/messages",
                json=payload,
                headers={
                    "x-api-key": self.settings.ANTHROPIC_API_KEY or "",
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                timeout=request.timeout or self.settings.PAID_TIMEOUT_SECONDS,
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Anthropic request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"Anthropic unreachable: {type(exc).__name__}") from exc
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        if response.status_code >= 400:
            raise ProviderUnavailableError(
                "Anthropic returned an error", detail={"status": response.status_code}
            )
        try:
            data = response.json()
            blocks = data.get("content") or []
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        except (ValueError, AttributeError, TypeError) as exc:
            raise ProviderUnavailableError("Anthropic returned a malformed response") from exc

        usage = data.get("usage") or {}
        return CompletionResponse(
            text=text,
            provider=self.name,
            model=data.get("model", model),
            input_tokens=int(usage.get("input_tokens") or estimate_tokens(str(turns))),
            output_tokens=int(usage.get("output_tokens") or estimate_tokens(text)),
            latency_ms=elapsed_ms,
            finish_reason=data.get("stop_reason"),
            raw={"id": data.get("id"), "usage": usage},
        )

    def health(self) -> HealthStatus:
        if not self.settings.ANTHROPIC_ENABLED:
            return HealthStatus(self.name, "paid", available=False, enabled=False, detail="disabled")
        if not self.settings.ANTHROPIC_API_KEY:
            return HealthStatus(
                self.name, "paid", available=False, enabled=False, detail="enabled but no API key"
            )
        return HealthStatus(
            self.name,
            "paid",
            available=True,
            enabled=True,
            detail="configured (not probed)",
            models=[self.default_model()],
        )

    def estimate_cost(self, input_tokens: int, output_tokens: int, model: str | None = None) -> float:
        return estimate_cost(self.name, model or self.default_model(), input_tokens, output_tokens)
