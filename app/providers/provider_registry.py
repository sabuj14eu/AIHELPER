"""Provider registry.

Builds the set of providers from settings and hands them out by name or by
kind. The gateway never imports a concrete provider class.
"""

from __future__ import annotations

import httpx

from app.core.config import Settings
from app.core.logging import get_logger
from app.local_ai.model_manager import ModelManager
from app.local_ai.ollama_client import OllamaClient
from app.providers.anthropic_provider import AnthropicProvider
from app.providers.base import HealthStatus, Provider
from app.providers.ollama_provider import OllamaProvider
from app.providers.openai_provider import OpenAIProvider

log = get_logger("providers")


class ProviderRegistry:
    def __init__(self, local: Provider | None = None, paid: dict[str, Provider] | None = None):
        self._local = local
        self._paid: dict[str, Provider] = paid or {}

    # ---------------------------------------------------------------- build
    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        ollama_client: OllamaClient | None = None,
        http_client: httpx.Client | None = None,
    ) -> ProviderRegistry:
        client = ollama_client or OllamaClient(
            settings.OLLAMA_URL, timeout=settings.LOCAL_TIMEOUT_SECONDS
        )
        manager = ModelManager(client, settings)
        local = OllamaProvider(client, manager, settings)
        paid: dict[str, Provider] = {
            "openai": OpenAIProvider(settings, client=http_client),
            "anthropic": AnthropicProvider(settings, client=http_client),
        }
        registry = cls(local=local, paid=paid)
        registry.settings = settings
        registry.model_manager = manager
        registry.ollama_client = client
        return registry

    # ----------------------------------------------------------- accessors
    @property
    def local(self) -> Provider | None:
        return self._local

    def register_paid(self, provider: Provider) -> None:
        self._paid[provider.name] = provider

    def set_local(self, provider: Provider | None) -> None:
        self._local = provider

    def get(self, name: str) -> Provider | None:
        if self._local is not None and name == self._local.name:
            return self._local
        return self._paid.get(name)

    def paid_providers(self, order: list[str] | None = None) -> list[Provider]:
        """Enabled paid providers, in the configured preference order."""
        if order is None:
            order = list(self._paid)
        chosen: list[Provider] = []
        for name in order:
            provider = self._paid.get(name)
            if provider is not None and provider.enabled:
                chosen.append(provider)
        return chosen

    def all_providers(self) -> list[Provider]:
        return ([self._local] if self._local else []) + list(self._paid.values())

    def any_paid_enabled(self) -> bool:
        return any(p.enabled for p in self._paid.values())

    # -------------------------------------------------------------- health
    def health(self) -> list[HealthStatus]:
        out: list[HealthStatus] = []
        for provider in self.all_providers():
            try:
                out.append(provider.health())
            except Exception as exc:  # a registry health sweep never raises
                log.warning("provider_health_raised", provider=provider.name, error=type(exc).__name__)
                out.append(
                    HealthStatus(
                        provider.name,
                        provider.kind,
                        available=False,
                        enabled=provider.enabled,
                        detail=type(exc).__name__,
                    )
                )
        return out

    def close(self) -> None:
        client = getattr(self, "ollama_client", None)
        if client is not None:
            client.close()
