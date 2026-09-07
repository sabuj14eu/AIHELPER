"""Generic agent profiles. Application-specific agents are out of scope in V1."""

from app.agents.base import AgentRegistry, AgentSpec, narrowed_tools
from app.agents.builtin import build_agent_registry

__all__ = ["AgentSpec", "AgentRegistry", "build_agent_registry", "narrowed_tools"]
