"""OpenAI provider. Disabled unless OPENAI_ENABLED=true and a key is set.

Implemented over plain httpx rather than the vendor SDK so the deployment
image has one fewer dependency that can drift, and so the request that leaves
the building is visible in this file.
"""

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


class OpenAIProvider(Provider):
    name = "openai"
    kind = "paid"

    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self._client = client

    @property
    def enabled(self) -> bool:
        return bool(self.settings.OPENAI_ENABLED and self.settings.OPENAI_API_KEY)

    def default_model(self) -> str:
        return self.settings.OPENAI_MODEL

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.settings.OPENAI_BASE_URL,
                timeout=self.settings.PAID_TIMEOUT_SECONDS,
            )
        return self._client

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        if not self.enabled:
            raise ProviderUnavailableError("OpenAI provider is disabled")
        model = request.model or self.default_model()
        payload: dict = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens or self.settings.PAID_MAX_TOKENS,
        }
        if request.stop:
            payload["stop"] = request.stop
        if request.response_format == "json":
            payload["response_format"] = {"type": "json_object"}

        started = time.perf_counter()
        try:
            response = self._http().post(
                "/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.settings.OPENAI_API_KEY}"},
                timeout=request.timeout or self.settings.PAID_TIMEOUT_SECONDS,
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("OpenAI request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"OpenAI unreachable: {type(exc).__name__}") from exc
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        if response.status_code >= 400:
            # The body can echo the request; never surface it verbatim.
            raise ProviderUnavailableError(
                "OpenAI returned an error", detail={"status": response.status_code}
            )
        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderUnavailableError("OpenAI returned a malformed response") from exc

        usage = data.get("usage") or {}
        return CompletionResponse(
            text=text,
            provider=self.name,
            model=data.get("model", model),
            input_tokens=int(usage.get("prompt_tokens") or estimate_tokens(str(payload["messages"]))),
            output_tokens=int(usage.get("completion_tokens") or estimate_tokens(text)),
            latency_ms=elapsed_ms,
            finish_reason=(data["choices"][0] or {}).get("finish_reason"),
            raw={"id": data.get("id"), "usage": usage},
        )

    def health(self) -> HealthStatus:
        if not self.settings.OPENAI_ENABLED:
            return HealthStatus(self.name, "paid", available=False, enabled=False, detail="disabled")
        if not self.settings.OPENAI_API_KEY:
            return HealthStatus(
                self.name, "paid", available=False, enabled=False, detail="enabled but no API key"
            )
        # Deliberately no live probe: a health check that calls a paid endpoint
        # can itself cost money. Configuration is reported; reachability is
        # learned from real traffic.
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
