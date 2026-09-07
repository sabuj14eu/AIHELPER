"""Cost control.

This module is the only thing standing between a bug and a bill. Its rules:

* Nothing is spent without a pre-flight check (:meth:`CostTracker.check`).
* Every completed paid call is recorded (:meth:`CostTracker.record`), whether
  it succeeded or not — a failed call still consumed input tokens.
* The pre-flight check is pessimistic: it assumes the response will be the
  full ``max_tokens``, so a budget can be approached but not overshot by a
  request the system chose to make.
* When a budget is reached, paid providers stop. The system keeps working
  locally. There is no "just this once" path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.logging import get_logger
from app.cost.pricing import estimate_cost, price_for
from app.database.enums import EscalationBlockReason
from app.database.models import CostRecord

log = get_logger("cost")


def _day_bounds(when: datetime | None = None) -> tuple[datetime, datetime]:
    now = when or datetime.now(UTC)
    start = datetime.combine(now.date(), time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)


def _month_bounds(when: datetime | None = None) -> tuple[datetime, datetime]:
    now = when or datetime.now(UTC)
    start = datetime.combine(date(now.year, now.month, 1), time.min, tzinfo=UTC)
    if now.month == 12:
        nxt = date(now.year + 1, 1, 1)
    else:
        nxt = date(now.year, now.month + 1, 1)
    return start, datetime.combine(nxt, time.min, tzinfo=UTC)


@dataclass
class BudgetDecision:
    allowed: bool
    reason: EscalationBlockReason | None = None
    detail: str = ""
    projected_cost: float = 0.0
    spent_today: float = 0.0
    spent_this_month: float = 0.0

    def as_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason.value if self.reason else None,
            "detail": self.detail,
            "projected_cost": round(self.projected_cost, 6),
            "spent_today": round(self.spent_today, 4),
            "spent_this_month": round(self.spent_this_month, 4),
        }


@dataclass
class SpendSummary:
    today: float
    month: float
    daily_budget: float
    monthly_budget: float
    calls_today: int
    calls_month: int

    @property
    def daily_remaining(self) -> float:
        return max(0.0, self.daily_budget - self.today)

    @property
    def monthly_remaining(self) -> float:
        return max(0.0, self.monthly_budget - self.month)

    @property
    def paid_disabled_by_budget(self) -> bool:
        return self.daily_remaining <= 0 or self.monthly_remaining <= 0

    def as_dict(self) -> dict:
        return {
            "spent_today": round(self.today, 4),
            "spent_this_month": round(self.month, 4),
            "daily_budget": self.daily_budget,
            "monthly_budget": self.monthly_budget,
            "daily_remaining": round(self.daily_remaining, 4),
            "monthly_remaining": round(self.monthly_remaining, 4),
            "calls_today": self.calls_today,
            "calls_this_month": self.calls_month,
            "paid_disabled_by_budget": self.paid_disabled_by_budget,
        }


class CostTracker:
    def __init__(self, session: Session, settings: Settings):
        self.session = session
        self.settings = settings

    # -------------------------------------------------------------- queries
    def _spend_between(self, start: datetime, end: datetime) -> tuple[float, int]:
        stmt = select(
            func.coalesce(func.sum(CostRecord.estimated_cost), 0.0), func.count(CostRecord.id)
        ).where(CostRecord.created_at >= start, CostRecord.created_at < end)
        total, count = self.session.execute(stmt).one()
        return float(total or 0.0), int(count or 0)

    def spend_today(self) -> float:
        return self._spend_between(*_day_bounds())[0]

    def spend_this_month(self) -> float:
        return self._spend_between(*_month_bounds())[0]

    def summary(self) -> SpendSummary:
        today, calls_today = self._spend_between(*_day_bounds())
        month, calls_month = self._spend_between(*_month_bounds())
        return SpendSummary(
            today=today,
            month=month,
            daily_budget=self.settings.AI_DAILY_API_BUDGET,
            monthly_budget=self.settings.AI_MONTHLY_API_BUDGET,
            calls_today=calls_today,
            calls_month=calls_month,
        )

    def client_spend_today(self, client_id: str) -> float:
        start, end = _day_bounds()
        stmt = select(func.coalesce(func.sum(CostRecord.estimated_cost), 0.0)).where(
            CostRecord.created_at >= start,
            CostRecord.created_at < end,
            CostRecord.client_id == client_id,
        )
        return float(self.session.execute(stmt).scalar_one() or 0.0)

    # ---------------------------------------------------------- enforcement
    def project(self, provider: str, model: str, input_tokens: int, max_output_tokens: int) -> float:
        """Worst-case cost of a call we have not made yet."""
        return estimate_cost(provider, model, input_tokens, max_output_tokens)

    def check(
        self,
        *,
        provider: str,
        model: str,
        input_tokens: int,
        max_output_tokens: int,
        client_id: str | None = None,
        client_daily_budget: float | None = None,
    ) -> BudgetDecision:
        """Pre-flight budget check. Called before every paid request."""
        settings = self.settings

        if input_tokens > settings.AI_MAX_INPUT_TOKENS_PER_REQUEST:
            return BudgetDecision(
                allowed=False,
                reason=EscalationBlockReason.REQUEST_TOO_LARGE,
                detail=(
                    f"{input_tokens} input tokens exceeds the per-request limit of "
                    f"{settings.AI_MAX_INPUT_TOKENS_PER_REQUEST}"
                ),
            )

        projected = self.project(provider, model, input_tokens, max_output_tokens)
        today, _ = self._spend_between(*_day_bounds())
        month, _ = self._spend_between(*_month_bounds())

        base = BudgetDecision(
            allowed=True,
            projected_cost=projected,
            spent_today=today,
            spent_this_month=month,
        )

        if projected > settings.AI_MAX_COST_PER_REQUEST:
            base.allowed = False
            base.reason = EscalationBlockReason.REQUEST_COST_CAP
            base.detail = (
                f"projected ${projected:.4f} exceeds the per-request cap of "
                f"${settings.AI_MAX_COST_PER_REQUEST:.2f}"
            )
            return base

        if month + projected > settings.AI_MONTHLY_API_BUDGET:
            base.allowed = False
            base.reason = EscalationBlockReason.MONTHLY_BUDGET_EXHAUSTED
            base.detail = (
                f"${month:.4f} spent this month; ${projected:.4f} more would exceed the "
                f"${settings.AI_MONTHLY_API_BUDGET:.2f} monthly budget"
            )
            return base

        if today + projected > settings.AI_DAILY_API_BUDGET:
            base.allowed = False
            base.reason = EscalationBlockReason.DAILY_BUDGET_EXHAUSTED
            base.detail = (
                f"${today:.4f} spent today; ${projected:.4f} more would exceed the "
                f"${settings.AI_DAILY_API_BUDGET:.2f} daily budget"
            )
            return base

        if client_daily_budget is not None and client_id:
            client_today = self.client_spend_today(client_id)
            if client_today + projected > client_daily_budget:
                base.allowed = False
                base.reason = EscalationBlockReason.DAILY_BUDGET_EXHAUSTED
                base.detail = (
                    f"client '{client_id}' has spent ${client_today:.4f} today; its own daily "
                    f"budget is ${client_daily_budget:.2f}"
                )
                return base

        return base

    # ------------------------------------------------------------ recording
    def record(
        self,
        *,
        request_id: str,
        client_id: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        task_type: str | None = None,
        reason_for_escalation: str | None = None,
        succeeded: bool = True,
    ) -> CostRecord:
        cost = estimate_cost(provider, model, input_tokens, output_tokens)
        record = CostRecord(
            request_id=request_id,
            client_id=client_id,
            provider=provider,
            model=model,
            task_type=task_type,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=cost,
            reason_for_escalation=reason_for_escalation,
            succeeded=succeeded,
        )
        self.session.add(record)
        self.session.flush()
        log.info(
            "paid_call_recorded",
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            escalation_reason=reason_for_escalation,
            succeeded=succeeded,
        )
        return record

    # ----------------------------------------------------------- reporting
    def by_provider(self, days: int = 30) -> list[dict]:
        start = datetime.now(UTC) - timedelta(days=days)
        stmt = (
            select(
                CostRecord.provider,
                CostRecord.model,
                func.count(CostRecord.id),
                func.coalesce(func.sum(CostRecord.estimated_cost), 0.0),
                func.coalesce(func.sum(CostRecord.input_tokens), 0),
                func.coalesce(func.sum(CostRecord.output_tokens), 0),
            )
            .where(CostRecord.created_at >= start)
            .group_by(CostRecord.provider, CostRecord.model)
            .order_by(func.sum(CostRecord.estimated_cost).desc())
        )
        return [
            {
                "provider": provider,
                "model": model,
                "calls": int(calls),
                "cost_usd": round(float(cost), 4),
                "input_tokens": int(inp),
                "output_tokens": int(out),
            }
            for provider, model, calls, cost, inp, out in self.session.execute(stmt)
        ]

    def by_escalation_reason(self, days: int = 30) -> list[dict]:
        """Answers 'why are we paying for AI?'."""
        start = datetime.now(UTC) - timedelta(days=days)
        stmt = (
            select(
                CostRecord.reason_for_escalation,
                func.count(CostRecord.id),
                func.coalesce(func.sum(CostRecord.estimated_cost), 0.0),
            )
            .where(CostRecord.created_at >= start)
            .group_by(CostRecord.reason_for_escalation)
            .order_by(func.sum(CostRecord.estimated_cost).desc())
        )
        return [
            {"reason": reason or "UNKNOWN", "calls": int(calls), "cost_usd": round(float(cost), 4)}
            for reason, calls, cost in self.session.execute(stmt)
        ]

    def price_sheet(self, provider: str, model: str) -> dict:
        price = price_for(provider, model)
        return {
            "provider": provider,
            "model": model,
            "input_per_mtok": price.input_per_mtok,
            "output_per_mtok": price.output_per_mtok,
        }
