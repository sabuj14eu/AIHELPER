"""The Gateway: local-first routing for every AI request."""

from app.gateway.escalation import (
    EscalationIntent,
    EscalationPermission,
    may_escalate,
    why_escalate,
)
from app.gateway.provider_manager import PaidCallResult, PaidProviderManager
from app.gateway.router import GatewayRequest, GatewayResponse, GatewayRouter
from app.gateway.task_classifier import classify

__all__ = [
    "GatewayRouter",
    "GatewayRequest",
    "GatewayResponse",
    "classify",
    "why_escalate",
    "may_escalate",
    "EscalationIntent",
    "EscalationPermission",
    "PaidProviderManager",
    "PaidCallResult",
]
