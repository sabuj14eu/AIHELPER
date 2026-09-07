"""System information.

Read-only, and it reports the AI Helper's own state — never the host's. There
is no shell, no process listing, no environment dump. The most this can tell
anyone is which models are installed and whether the components are up, which
is the same information the /health endpoint already returns.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app import __version__
from app.core.config import Settings
from app.database.enums import RiskLevel
from app.tools.registry import PERM_SYSTEM_INFO, ToolResult, ToolSpec


def make_system_spec(settings: Settings, registry_provider=None) -> ToolSpec:
    def system_info(**_ignored) -> ToolResult:
        info = {
            "name": settings.APP_NAME,
            "version": __version__,
            "environment": settings.ENVIRONMENT,
            "utc_time": datetime.now(UTC).isoformat(),
            "local_first": True,
            "paid_providers_enabled": [
                name
                for name, on in (
                    ("openai", settings.OPENAI_ENABLED),
                    ("anthropic", settings.ANTHROPIC_ENABLED),
                )
                if on
            ],
            "default_local_model": settings.DEFAULT_LOCAL_MODEL,
        }
        if registry_provider is not None:
            try:
                info["providers"] = [h.as_dict()["status"] for h in registry_provider().health()]
            except Exception:  # informational only
                info["providers"] = ["unknown"]
        display = "\n".join(f"{k}: {v}" for k, v in info.items())
        return ToolResult(ok=True, value=info, display=display)

    return ToolSpec(
        name="system_info",
        description=(
            "Report AI Helper's own version, environment, configured local model and which "
            "providers are enabled. Reports nothing about the host machine."
        ),
        permissions={PERM_SYSTEM_INFO},
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        output_schema={"type": "object", "properties": {"value": {"type": "object"}}},
        risk=RiskLevel.LOW,
        handler=system_info,
        answers_directly=False,
    )
