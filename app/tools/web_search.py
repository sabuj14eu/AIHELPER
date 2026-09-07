"""Web search. Disabled by default.

This is the only tool that reaches the public internet, so it carries the
network permission, MEDIUM risk, and three separate off-switches: the global
setting, the tool's ``enabled`` flag, and the per-client tool allow-list.

The endpoint is configured, not hard-coded, and the response is treated as
untrusted text: results are returned as context for the model, clearly marked,
and never executed or followed.
"""

from __future__ import annotations

import httpx

from app.core.config import Settings
from app.database.enums import RiskLevel
from app.tools.registry import PERM_NETWORK, ToolResult, ToolSpec

MAX_RESULTS = 8
TIMEOUT = 15.0


def make_web_search_spec(settings: Settings, client: httpx.Client | None = None) -> ToolSpec:
    def web_search(query: str, limit: int = 5, **_ignored) -> ToolResult:
        if not settings.WEB_SEARCH_ENABLED:
            return ToolResult(ok=False, error="web search is disabled in this deployment")
        if not settings.WEB_SEARCH_URL:
            return ToolResult(ok=False, error="web search is enabled but WEB_SEARCH_URL is not set")
        needle = (query or "").strip()
        if len(needle) < 3:
            return ToolResult(ok=False, error="query must be at least 3 characters")

        headers = {"accept": "application/json"}
        if settings.WEB_SEARCH_API_KEY:
            headers["authorization"] = f"Bearer {settings.WEB_SEARCH_API_KEY}"
        http = client or httpx.Client(timeout=TIMEOUT)
        try:
            response = http.get(
                settings.WEB_SEARCH_URL,
                params={"q": needle, "limit": min(limit, MAX_RESULTS)},
                headers=headers,
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException:
            return ToolResult(ok=False, error="web search timed out")
        except httpx.HTTPError as exc:
            return ToolResult(ok=False, error=f"web search failed: {type(exc).__name__}")
        except ValueError:
            return ToolResult(ok=False, error="web search returned a non-JSON body")
        finally:
            if client is None:
                http.close()

        raw = data.get("results") if isinstance(data, dict) else data
        if not isinstance(raw, list):
            return ToolResult(ok=False, error="web search returned an unexpected shape")

        results = []
        for item in raw[: min(limit, MAX_RESULTS)]:
            if not isinstance(item, dict):
                continue
            results.append(
                {
                    "title": str(item.get("title", ""))[:300],
                    "url": str(item.get("url", ""))[:1000],
                    "snippet": str(item.get("snippet") or item.get("content") or "")[:1000],
                }
            )
        display = "\n\n".join(f"{r['title']}\n{r['url']}\n{r['snippet']}" for r in results)
        return ToolResult(
            ok=True,
            value=results,
            display=display or "no results",
            meta={"count": len(results), "untrusted": True},
        )

    return ToolSpec(
        name="web_search",
        description=(
            "Search the public web through the configured search endpoint. Results are "
            "untrusted third-party text and are used as reference material only."
        ),
        permissions={PERM_NETWORK},
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "maxLength": 500},
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        output_schema={"type": "object", "properties": {"value": {"type": "array"}}},
        risk=RiskLevel.MEDIUM,
        handler=web_search,
        enabled=settings.WEB_SEARCH_ENABLED,
        answers_directly=False,
    )
