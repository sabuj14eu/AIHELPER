"""The local provider. Free, default, and always tried first."""

from __future__ import annotations

from app.core.config import Settings
from app.core.errors import ProviderUnavailableError
from app.database.enums import TaskType
from app.local_ai.model_manager import ModelManager
from app.local_ai.ollama_client import OllamaClient
from app.providers.base import (
    CompletionRequest,
    CompletionResponse,
    HealthStatus,
    Provider,
    estimate_tokens,
)


class OllamaProvider(Provider):
    name = "ollama"
    kind = "local"

    def __init__(self, client: OllamaClient, model_manager: ModelManager, settings: Settings):
        self.client = client
        self.models = model_manager
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return self.settings.OLLAMA_ENABLED

    def default_model(self) -> str:
        return self.settings.DEFAULT_LOCAL_MODEL

    def resolve_model(self, task_type: TaskType | str, requested: str | None = None) -> str | None:
        return self.models.select(task_type, requested)

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        if not self.enabled:
            raise ProviderUnavailableError("Ollama is disabled by configuration")
        model = request.model or self.models.select(TaskType.GENERAL)
        if not model:
            raise ProviderUnavailableError("No local model is installed")
        result = self.client.chat(
            model,
            [{"role": m.role, "content": m.content} for m in request.messages],
            max_tokens=request.max_tokens or self.settings.LOCAL_MAX_TOKENS,
            temperature=request.temperature,
            timeout=request.timeout or self.settings.LOCAL_TIMEOUT_SECONDS,
            stop=request.stop or None,
            json_mode=request.response_format == "json",
        )
        # Ollama does not always report counts; estimate rather than record zero,
        # so latency/throughput dashboards are not silently wrong.
        input_tokens = result["input_tokens"] or estimate_tokens(
            "".join(m.content for m in request.messages)
        )
        output_tokens = result["output_tokens"] or estimate_tokens(result["text"])
        return CompletionResponse(
            text=result["text"],
            provider=self.name,
            model=result["model"],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=result["latency_ms"],
            finish_reason=result["finish_reason"],
            raw=result["raw"],
        )

    def health(self) -> HealthStatus:
        if not self.enabled:
            return HealthStatus(self.name, "local", available=False, enabled=False, detail="disabled")
        try:
            models = self.models.installed_models(refresh=True)
        except Exception as exc:  # a health probe must never raise
            return HealthStatus(
                self.name, "local", available=False, enabled=True, detail=type(exc).__name__
            )
        if not models:
            return HealthStatus(
                self.name,
                "local",
                available=False,
                enabled=True,
                detail="unreachable or no models installed",
            )
        return HealthStatus(self.name, "local", available=True, enabled=True, models=models)

    def estimate_cost(self, input_tokens: int, output_tokens: int, model: str | None = None) -> float:
        return 0.0  # local inference costs no money
