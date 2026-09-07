"""Agent framework.

An agent is a *named routing profile*, not a second brain. It contributes
three things and nothing else:

* a system-prompt fragment,
* a default task type,
* a narrowed set of tools it is allowed to reach.

Everything an agent does still goes down the same Gateway ladder, is still
validated, still budget-checked and still privacy-gated. This is deliberate:
an agent framework that could bypass the Gateway would be a second, unaudited
path to a paid provider.

Application-specific agents (accounting, trading, delivery, spa) are **not**
implemented here, by the work order. The registry below is the extension
point: adding one is a new AgentSpec, with no change to the Gateway.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.database.enums import TaskType


@dataclass(frozen=True)
class AgentSpec:
    name: str
    description: str
    default_task_type: TaskType
    system_prompt: str = ""
    allowed_tools: tuple[str, ...] | None = None   # None = the client's own set
    enabled: bool = True

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "default_task_type": self.default_task_type.value,
            "allowed_tools": list(self.allowed_tools) if self.allowed_tools else None,
            "enabled": self.enabled,
        }


class AgentRegistry:
    def __init__(self, specs: list[AgentSpec] | None = None):
        self._agents: dict[str, AgentSpec] = {}
        for spec in specs or []:
            self.register(spec)

    def register(self, spec: AgentSpec) -> None:
        if spec.name in self._agents:
            raise ValueError(f"agent '{spec.name}' is already registered")
        self._agents[spec.name] = spec

    def get(self, name: str) -> AgentSpec | None:
        spec = self._agents.get(name)
        return spec if spec is not None and spec.enabled else None

    def list(self) -> list[AgentSpec]:
        return sorted(self._agents.values(), key=lambda s: s.name)

    def names(self) -> list[str]:
        return sorted(name for name, spec in self._agents.items() if spec.enabled)


def narrowed_tools(spec: AgentSpec, client_allowed: list[str] | None) -> list[str] | None:
    """An agent may only ever narrow the client's tool set, never widen it."""
    if spec.allowed_tools is None:
        return client_allowed
    if client_allowed is None:
        return list(spec.allowed_tools)
    return [name for name in spec.allowed_tools if name in client_allowed]
