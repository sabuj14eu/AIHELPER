"""Assemble the tool registry from settings."""

from __future__ import annotations

from app.core.config import Settings
from app.tools import calculator, dates, documents, json_tools, system, web_search
from app.tools.registry import ToolRegistry


def build_registry(settings: Settings, registry_provider=None) -> ToolRegistry:
    registry = ToolRegistry()
    if not settings.TOOLS_ENABLED:
        return registry
    registry.register(calculator.SPEC)
    registry.register(dates.SPEC)
    registry.register(json_tools.SPEC)
    registry.register(documents.LIST_SPEC)
    registry.register(documents.SEARCH_SPEC)
    registry.register(documents.MEMORY_SPEC)
    registry.register(system.make_system_spec(settings, registry_provider))
    registry.register(web_search.make_web_search_spec(settings))
    return registry
