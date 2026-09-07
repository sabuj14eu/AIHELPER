"""Tool system: a closed set of named, schema-validated functions."""

from app.tools.builder import build_registry
from app.tools.registry import (
    DEFAULT_PERMISSIONS,
    PERM_COMPUTE,
    PERM_NETWORK,
    PERM_READ_DOCUMENTS,
    PERM_READ_MEMORY,
    PERM_SYSTEM_INFO,
    ToolRegistry,
    ToolResult,
    ToolSpec,
)

__all__ = [
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    "build_registry",
    "DEFAULT_PERMISSIONS",
    "PERM_COMPUTE",
    "PERM_NETWORK",
    "PERM_READ_DOCUMENTS",
    "PERM_READ_MEMORY",
    "PERM_SYSTEM_INFO",
]
