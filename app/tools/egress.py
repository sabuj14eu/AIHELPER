"""Whether this request may reach the public internet.

A web search is an **egress path**. The question text goes to a third party,
and that is the same class of act as sending it to a paid provider — which the
privacy architecture has governed since 1.0, through `may_leave_system`.

Until now, nothing connected the two. Tools were gated on *permissions* and on
the client's allow-list, never on *what the data is*. `may_leave_system` was
called from exactly one place: `escalation.may_escalate`. So the rule that says
"RESTRICTED data may never be sent to an external provider" would not have been
consulted when Brother typed a RESTRICTED question into a search box.

This module is that missing connection. It does not invent a second privacy
policy — a second policy is how two policies drift apart. It calls the same
function, with the same allowed set and the same per-client ceiling, so a
change to the egress rule changes both paths at once or neither.

**Granting is explicit and cannot happen by accident.** `tool:network` is not
in `DEFAULT_PERMISSIONS`, so the floor is "no". It is granted only when the
client's `allowed_tools` *names* a network tool — a list someone wrote on
purpose. A client with `allowed_tools = None` inherits every ordinary tool and
still gets no network, because inheriting everything is not the same as
choosing this.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.database.enums import Classification
from app.privacy.classification import may_leave_system
from app.tools.registry import DEFAULT_PERMISSIONS, PERM_NETWORK, ToolRegistry


@dataclass(frozen=True)
class EgressDecision:
    allowed: bool
    reason: str

    def as_dict(self) -> dict:
        return {"network_allowed": self.allowed, "reason": self.reason}


def network_tool_names(registry: ToolRegistry) -> set[str]:
    """Every tool that would reach outside, including disabled ones.

    Disabled ones count: the question here is "would granting this let the
    request leave?", and a tool that is off today can be on tomorrow.
    """
    return {
        spec.name
        for spec in registry.list(include_disabled=True)
        if PERM_NETWORK in spec.permissions
    }


def may_use_network(
    *,
    classification: Classification | str,
    settings: Settings,
    client_allowed_tools: list[str] | None,
    client_max_classification: str | None,
    registry: ToolRegistry,
) -> EgressDecision:
    """May this request use a tool that reaches the public internet?

    Both halves must say yes, and they are asked in this order on purpose:
    the *data* question first, then the *permission* question. "We would never
    send this" is a stronger and more useful statement than "this client is not
    configured for it", and the reason string is read by a human.
    """
    sensitivity = Classification(str(classification).upper())

    permitted, why = may_leave_system(
        sensitivity,
        allowed=settings.external_allowed,
        client_max=client_max_classification,
    )
    if not permitted:
        return EgressDecision(False, f"web search refused: {why}")

    if client_allowed_tools is None:
        return EgressDecision(
            False,
            "web search refused: this client has no explicit tool list, and "
            "inheriting every tool is not the same as choosing to allow the "
            "internet — name a network tool in its allowed_tools to grant it",
        )
    granted = set(client_allowed_tools) & network_tool_names(registry)
    if not granted:
        return EgressDecision(
            False, "web search refused: this client's tool list names no network tool"
        )
    return EgressDecision(True, f"network permitted via {', '.join(sorted(granted))}")


def permissions_for(
    *,
    classification: Classification | str,
    settings: Settings,
    client_allowed_tools: list[str] | None,
    client_max_classification: str | None,
    registry: ToolRegistry,
) -> tuple[set[str], EgressDecision]:
    """The permission set for this request, and why the network bit is set.

    The default set is the floor and is never widened by anything but this
    decision, so there is exactly one place where a request gains the ability
    to leave the machine.
    """
    decision = may_use_network(
        classification=classification,
        settings=settings,
        client_allowed_tools=client_allowed_tools,
        client_max_classification=client_max_classification,
        registry=registry,
    )
    permissions = set(DEFAULT_PERMISSIONS)
    if decision.allowed:
        permissions.add(PERM_NETWORK)
    return permissions, decision
