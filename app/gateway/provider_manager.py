"""Executing a paid call, with every guard in front of it.

Order of operations, and none of it is optional:

1. classification gate (RESTRICTED never leaves — checked again here, not
   only in the policy layer, because this is the last place before the wire);
2. redaction, if configured;
3. budget pre-check against the *redacted* prompt, per provider;
4. the call itself;
5. cost recorded from the provider's own reported token counts, whether the
   call succeeded or failed;
6. an audit row naming the provider, the model, the reason and the cost —
   never the content.

If the first provider fails, the next enabled one is tried, and each gets its
own budget check. A failed call still spent input tokens, so it is still
recorded.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.audit import BUDGET_TRIPPED, EXTERNAL_BLOCKED, EXTERNAL_CALL, PRIVACY_BLOCK, record
from app.core.config import Settings
from app.core.errors import ProviderTimeoutError, ProviderUnavailableError
from app.core.logging import get_logger
from app.cost.tracker import CostTracker
from app.database.enums import Classification, EscalationBlockReason, EscalationReason
from app.privacy.classification import may_leave_system
from app.privacy.redaction import RedactionResult, redact
from app.providers.base import CompletionRequest, CompletionResponse, Provider, estimate_tokens

log = get_logger("provider_manager")


@dataclass
class PaidCallResult:
    ok: bool
    response: CompletionResponse | None = None
    provider: str | None = None
    model: str | None = None
    cost_usd: float = 0.0
    blocked_reason: EscalationBlockReason | None = None
    detail: str = ""
    redaction: dict = field(default_factory=dict)
    attempts: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "provider": self.provider,
            "model": self.model,
            "cost_usd": round(self.cost_usd, 6),
            "blocked_reason": self.blocked_reason.value if self.blocked_reason else None,
            "detail": self.detail,
            "redaction": self.redaction,
            "attempts": self.attempts,
        }


class PaidProviderManager:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        cost_tracker: CostTracker,
    ):
        self.session = session
        self.settings = settings
        self.cost = cost_tracker

    # ---------------------------------------------------------- preparation
    def prepare(self, request: CompletionRequest) -> tuple[CompletionRequest, RedactionResult | None]:
        """Redact the outgoing prompt, if configured."""
        if not self.settings.REDACT_BEFORE_ESCALATION:
            return request, None
        combined = "\n".join(m.content for m in request.messages)
        result = redact(combined)
        if not result.redacted:
            return request, result
        # Redact each message independently so roles are preserved.
        redacted_messages = []
        for message in request.messages:
            text = message.content
            for token, original in result.placeholders.items():
                text = text.replace(original, token)
            redacted_messages.append(type(message)(role=message.role, content=text))
        prepared = CompletionRequest(
            messages=redacted_messages,
            model=request.model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            timeout=request.timeout,
            stop=list(request.stop),
            response_format=request.response_format,
            request_id=request.request_id,
        )
        return prepared, result

    # ----------------------------------------------------------------- call
    def call(
        self,
        providers: list[Provider],
        request: CompletionRequest,
        *,
        client_id: str,
        request_id: str,
        task_type: str,
        classification: Classification,
        escalation_reason: EscalationReason,
        client_max_classification: str | None = None,
        client_daily_budget: float | None = None,
    ) -> PaidCallResult:
        # 1. The last privacy gate before the wire.
        allowed, detail = may_leave_system(
            classification,
            allowed=self.settings.external_allowed,
            client_max=client_max_classification,
        )
        if not allowed:
            record(
                self.session,
                actor=client_id,
                action=PRIVACY_BLOCK,
                request_id=request_id,
                result="blocked",
                detail={"classification": classification.value, "reason": detail},
            )
            log.warning("escalation_blocked_by_privacy", classification=classification.value)
            return PaidCallResult(
                ok=False,
                blocked_reason=EscalationBlockReason.CLASSIFICATION_BLOCKED,
                detail=detail,
            )

        if not providers:
            return PaidCallResult(
                ok=False,
                blocked_reason=EscalationBlockReason.NOT_CONFIGURED,
                detail="no paid provider is enabled",
            )

        # 2. Redaction.
        prepared, redaction = self.prepare(request)
        redaction_summary = redaction.summary() if redaction else {"redacted": False, "counts": {}}

        attempts: list[dict] = []
        last_block: EscalationBlockReason | None = None
        last_detail = ""

        for provider in providers:
            model = prepared.model or provider.default_model()
            input_tokens = estimate_tokens("\n".join(m.content for m in prepared.messages))
            max_output = prepared.max_tokens or self.settings.PAID_MAX_TOKENS

            # 3. Budget, per provider, before the call.
            decision = self.cost.check(
                provider=provider.name,
                model=model,
                input_tokens=input_tokens,
                max_output_tokens=max_output,
                client_id=client_id,
                client_daily_budget=client_daily_budget,
            )
            if not decision.allowed:
                attempts.append(
                    {"provider": provider.name, "outcome": "blocked", "reason": decision.reason.value if decision.reason else None}
                )
                last_block = decision.reason
                last_detail = decision.detail
                record(
                    self.session,
                    actor=client_id,
                    action=BUDGET_TRIPPED,
                    request_id=request_id,
                    result="blocked",
                    detail={
                        "provider": provider.name,
                        "model": model,
                        "reason": decision.reason.value if decision.reason else None,
                        "detail": decision.detail,
                        "projected_cost": decision.projected_cost,
                    },
                )
                log.warning(
                    "paid_call_blocked_by_budget",
                    provider=provider.name,
                    reason=decision.reason.value if decision.reason else None,
                )
                continue

            # 4. The call.
            try:
                response = provider.complete(
                    CompletionRequest(
                        messages=prepared.messages,
                        model=model,
                        max_tokens=max_output,
                        temperature=prepared.temperature,
                        timeout=prepared.timeout,
                        stop=list(prepared.stop),
                        response_format=prepared.response_format,
                        request_id=request_id,
                    )
                )
            except (ProviderTimeoutError, ProviderUnavailableError) as exc:
                # The request left the building and consumed input tokens even
                # though it produced nothing. Record the spend.
                self.cost.record(
                    request_id=request_id,
                    client_id=client_id,
                    provider=provider.name,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=0,
                    task_type=str(task_type),
                    reason_for_escalation=escalation_reason.value,
                    succeeded=False,
                )
                attempts.append(
                    {"provider": provider.name, "outcome": "error", "error": exc.code}
                )
                last_block = EscalationBlockReason.PROVIDER_FAILED
                last_detail = exc.message
                log.warning("paid_provider_failed", provider=provider.name, error=exc.code)
                continue

            # 5. Cost, from the provider's own numbers.
            cost_record = self.cost.record(
                request_id=request_id,
                client_id=client_id,
                provider=provider.name,
                model=response.model,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                task_type=str(task_type),
                reason_for_escalation=escalation_reason.value,
                succeeded=True,
            )

            # Put the caller's own values back into the answer.
            if redaction is not None and redaction.redacted:
                response.text = redaction.restore(response.text)

            # 6. Audit: metadata only, never the prompt or the answer.
            record(
                self.session,
                actor=client_id,
                action=EXTERNAL_CALL,
                resource_type="provider",
                resource_id=provider.name,
                request_id=request_id,
                detail={
                    "model": response.model,
                    "classification": classification.value,
                    "escalation_reason": escalation_reason.value,
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                    "cost_usd": cost_record.estimated_cost,
                    "redaction": redaction_summary,
                    "task_type": str(task_type),
                },
            )
            attempts.append({"provider": provider.name, "outcome": "ok"})
            return PaidCallResult(
                ok=True,
                response=response,
                provider=provider.name,
                model=response.model,
                cost_usd=cost_record.estimated_cost,
                redaction=redaction_summary,
                attempts=attempts,
            )

        record(
            self.session,
            actor=client_id,
            action=EXTERNAL_BLOCKED,
            request_id=request_id,
            result="blocked",
            detail={
                "reason": last_block.value if last_block else None,
                "detail": last_detail,
                "attempts": attempts,
            },
        )
        return PaidCallResult(
            ok=False,
            blocked_reason=last_block or EscalationBlockReason.PROVIDER_FAILED,
            detail=last_detail or "every paid provider failed or was blocked",
            redaction=redaction_summary,
            attempts=attempts,
        )
