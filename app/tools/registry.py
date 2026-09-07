"""Tool registry.

Every tool declares name, description, permissions, input schema, output
schema and risk level, and the registry refuses to register one that does not.

There is deliberately no generic executor: no ``run_command``, no ``eval``, no
``exec``, no filesystem write, no arbitrary HTTP. A tool is a named Python
function with a validated signature, and that is the only way code runs on
behalf of a request.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.errors import PermissionDeniedError, ToolError
from app.core.logging import get_logger
from app.database.enums import RiskLevel

log = get_logger("tools")

# Permission names. A client's allowed_tools list is checked against tool
# names; these permissions are the coarser capability grouping.
PERM_COMPUTE = "tool:compute"
PERM_READ_DOCUMENTS = "tool:read_documents"
PERM_READ_MEMORY = "tool:read_memory"
PERM_NETWORK = "tool:network"
PERM_SYSTEM_INFO = "tool:system_info"

DEFAULT_PERMISSIONS = {PERM_COMPUTE, PERM_READ_DOCUMENTS, PERM_READ_MEMORY, PERM_SYSTEM_INFO}


@dataclass
class ToolResult:
    ok: bool
    value: Any = None
    display: str = ""
    error: str | None = None
    meta: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "value": self.value,
            "display": self.display,
            "error": self.error,
            "meta": self.meta,
        }


@dataclass
class ToolSpec:
    name: str
    description: str
    permissions: set[str]
    input_schema: dict
    output_schema: dict
    risk: RiskLevel
    handler: Callable[..., ToolResult]
    enabled: bool = True
    # A tool that can fully answer a request on its own (level 0 of the
    # routing ladder) rather than merely assisting the model.
    answers_directly: bool = True

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "permissions": sorted(self.permissions),
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "risk": self.risk.value,
            "enabled": self.enabled,
            "answers_directly": self.answers_directly,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if not spec.name or not spec.description:
            raise ToolError("a tool must declare a name and a description")
        if not spec.permissions:
            raise ToolError(f"tool '{spec.name}' declares no permissions")
        if not spec.input_schema or not spec.output_schema:
            raise ToolError(f"tool '{spec.name}' must declare input and output schemas")
        if spec.name in self._tools:
            raise ToolError(f"tool '{spec.name}' is already registered")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def list(self, *, include_disabled: bool = True) -> list[ToolSpec]:
        return [
            spec
            for spec in sorted(self._tools.values(), key=lambda s: s.name)
            if include_disabled or spec.enabled
        ]

    def available_to(
        self, allowed_tools: list[str] | None, granted_permissions: set[str] | None = None
    ) -> list[ToolSpec]:
        """Tools this caller may use.

        ``allowed_tools`` of None means the client has not been narrowed and
        gets the default set; an empty list means the client gets nothing.
        """
        permissions = DEFAULT_PERMISSIONS if granted_permissions is None else granted_permissions
        out = []
        for spec in self.list(include_disabled=False):
            if allowed_tools is not None and spec.name not in allowed_tools:
                continue
            if not spec.permissions.issubset(permissions):
                continue
            out.append(spec)
        return out

    def invoke(
        self,
        name: str,
        arguments: dict,
        *,
        allowed_tools: list[str] | None = None,
        granted_permissions: set[str] | None = None,
        context: dict | None = None,
    ) -> ToolResult:
        spec = self._tools.get(name)
        if spec is None:
            raise ToolError(f"unknown tool '{name}'")
        if not spec.enabled:
            raise ToolError(f"tool '{name}' is disabled")
        if allowed_tools is not None and name not in allowed_tools:
            raise PermissionDeniedError(f"client is not permitted to use tool '{name}'")
        permissions = DEFAULT_PERMISSIONS if granted_permissions is None else granted_permissions
        missing = spec.permissions - permissions
        if missing:
            raise PermissionDeniedError(
                f"tool '{name}' requires permissions not granted: {', '.join(sorted(missing))}"
            )
        validate_against_schema(arguments, spec.input_schema, where=f"{name}.input")
        try:
            result = spec.handler(**arguments, **(context or {}))
        except ToolError:
            raise
        except TypeError as exc:
            raise ToolError(f"tool '{name}' rejected its arguments: {exc}") from exc
        except Exception as exc:  # a tool bug must not take down the request
            log.warning("tool_failed", tool=name, error=type(exc).__name__)
            return ToolResult(ok=False, error=f"{type(exc).__name__}: {exc}")
        log.info("tool_invoked", tool=name, ok=result.ok, risk=spec.risk.value)
        return result


# --------------------------------------------------------------------------
# A deliberately small JSON-Schema subset. Keeping this in-house avoids a
# dependency and, more importantly, keeps the accepted surface small enough to
# read in one sitting.
# --------------------------------------------------------------------------
_TYPES = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "object": dict,
    "array": list,
}


def validate_against_schema(value: Any, schema: dict, where: str = "value") -> None:
    expected = schema.get("type")
    if expected:
        python_type = _TYPES.get(expected)
        if python_type is None:
            raise ToolError(f"{where}: unsupported schema type '{expected}'")
        if expected == "boolean" and isinstance(value, bool):
            pass
        elif expected in ("number", "integer") and isinstance(value, bool):
            raise ToolError(f"{where}: expected {expected}, got boolean")
        elif not isinstance(value, python_type):
            raise ToolError(f"{where}: expected {expected}, got {type(value).__name__}")

    if expected == "object":
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                raise ToolError(f"{where}: missing required property '{key}'")
        if schema.get("additionalProperties") is False:
            unexpected = set(value) - set(properties)
            if unexpected:
                raise ToolError(f"{where}: unexpected properties {sorted(unexpected)}")
        for key, sub_schema in properties.items():
            if key in value:
                validate_against_schema(value[key], sub_schema, where=f"{where}.{key}")

    if expected == "array":
        items = schema.get("items")
        max_items = schema.get("maxItems")
        if max_items is not None and len(value) > max_items:
            raise ToolError(f"{where}: at most {max_items} items allowed")
        if items:
            for index, item in enumerate(value):
                validate_against_schema(item, items, where=f"{where}[{index}]")

    if expected == "string":
        max_length = schema.get("maxLength")
        if max_length is not None and len(value) > max_length:
            raise ToolError(f"{where}: at most {max_length} characters allowed")
        enum = schema.get("enum")
        if enum and value not in enum:
            raise ToolError(f"{where}: must be one of {enum}")

    if expected in ("number", "integer"):
        if "minimum" in schema and value < schema["minimum"]:
            raise ToolError(f"{where}: must be >= {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            raise ToolError(f"{where}: must be <= {schema['maximum']}")
