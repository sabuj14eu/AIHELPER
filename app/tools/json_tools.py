"""JSON parsing, validation and field extraction. No AI tokens spent."""

from __future__ import annotations

import json
from typing import Any

from app.database.enums import RiskLevel
from app.tools.registry import PERM_COMPUTE, ToolResult, ToolSpec

MAX_JSON_CHARS = 200_000
MAX_DEPTH = 40


def _depth(value: Any, level: int = 0) -> int:
    if level > MAX_DEPTH:
        return level
    if isinstance(value, dict):
        return max((_depth(v, level + 1) for v in value.values()), default=level)
    if isinstance(value, list):
        return max((_depth(v, level + 1) for v in value), default=level)
    return level


def _get_path(data: Any, path: str) -> Any:
    """Dotted path with numeric indices: 'items.0.name'."""
    current = data
    for part in path.split("."):
        if part == "":
            continue
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError) as exc:
                raise KeyError(f"no element at '{part}'") from exc
        elif isinstance(current, dict):
            if part not in current:
                raise KeyError(f"no key '{part}'")
            current = current[part]
        else:
            raise KeyError(f"cannot descend into {type(current).__name__} at '{part}'")
    return current


def json_process(text: str, path: str | None = None, **_ignored) -> ToolResult:
    if len(text) > MAX_JSON_CHARS:
        return ToolResult(ok=False, error=f"input longer than {MAX_JSON_CHARS} characters")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return ToolResult(
            ok=False,
            error=f"invalid JSON at line {exc.lineno} column {exc.colno}: {exc.msg}",
            meta={"line": exc.lineno, "column": exc.colno},
        )
    if _depth(data) > MAX_DEPTH:
        return ToolResult(ok=False, error=f"JSON nested deeper than {MAX_DEPTH} levels")

    if path:
        try:
            data = _get_path(data, path)
        except KeyError as exc:
            return ToolResult(ok=False, error=f"path '{path}': {exc}")

    rendered = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False)
    return ToolResult(
        ok=True,
        value=rendered,
        display=rendered if len(rendered) < 4000 else rendered[:4000] + "\n…[truncated]",
        meta={
            "type": type(data).__name__,
            "keys": sorted(data)[:50] if isinstance(data, dict) else None,
            "length": len(data) if isinstance(data, (list, dict, str)) else None,
        },
    )


SPEC = ToolSpec(
    name="json_parser",
    description=(
        "Parse and validate a JSON document, optionally extracting a dotted path such as "
        "'invoice.lines.0.net'. Returns the value pretty-printed, or a precise parse error."
    ),
    permissions={PERM_COMPUTE},
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "maxLength": MAX_JSON_CHARS},
            "path": {"type": "string", "maxLength": 500},
        },
        "required": ["text"],
        "additionalProperties": False,
    },
    output_schema={"type": "object", "properties": {"value": {"type": "string"}}},
    risk=RiskLevel.LOW,
    handler=json_process,
)
