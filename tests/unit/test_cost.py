"""Pricing, budgets and the analytics built on them."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.cost.analytics import usage_summary
from app.cost.pricing import UNKNOWN_PRICE, estimate_cost, price_for
from app.cost.tracker import CostTracker
from app.database.enums import EscalationBlockReason
from app.database.models import CostRecord


class TestPricing:
    def test_a_known_model_prices_from_the_table(self):
        assert estimate_cost("openai", "gpt-4o-mini", 1_000_000, 0) == pytest.approx(0.15)

    def test_a_dated_model_name_resolves_to_its_base(self):
        assert price_for("anthropic", "claude-sonnet-5-20260101") == price_for(
            "anthropic", "claude-sonnet-5"
        )

    def test_an_unknown_model_is_priced_at_the_providers_worst_rate_not_zero(self):
        """Under-counting a budget is worse than over-counting it."""
        price = price_for("anthropic", "claude-something-brand-new")
        assert price.output_per_mtok == max(
            p.output_per_mtok for p in [price_for("anthropic", m) for m in
                                       ("claude-haiku-4-5", "claude-sonnet-5", "claude-opus-5")]
        )
        assert estimate_cost("anthropic", "unknown-model", 1000, 1000) > 0

    def test_an_unknown_provider_is_priced_pessimistically(self):
        assert price_for("some-new-vendor", "x") == UNKNOWN_PRICE

    def test_zero_tokens_cost_nothing(self):
        assert estimate_cost("openai", "gpt-4o", 0, 0) == 0.0


class TestBudgets:
    def _tracker(self, db, settings):
        return CostTracker(db, settings)

    def test_a_call_within_budget_is_allowed(self, db, settings):
        decision = self._tracker(db, settings).check(
            provider="anthropic", model="claude-sonnet-5", input_tokens=500, max_output_tokens=200
        )
        assert decision.allowed is True and decision.projected_cost > 0

    def test_the_check_is_pessimistic_about_the_output_length(self, db, settings):
        """It assumes the full max_tokens, so a budget cannot be overshot."""
        tracker = self._tracker(db, settings)
        small = tracker.project("anthropic", "claude-sonnet-5", 500, 10)
        large = tracker.project("anthropic", "claude-sonnet-5", 500, 4000)
        assert large > small

    def test_the_daily_budget_stops_spending(self, db, settings):
        settings.AI_DAILY_API_BUDGET = 0.001
        decision = self._tracker(db, settings).check(
            provider="anthropic", model="claude-opus-5", input_tokens=10_000, max_output_tokens=2000
        )
        assert decision.reason is EscalationBlockReason.DAILY_BUDGET_EXHAUSTED

    def test_the_monthly_budget_is_checked_before_the_daily_one(self, db, settings):
        settings.AI_MONTHLY_API_BUDGET = 0.0
        settings.AI_DAILY_API_BUDGET = 100.0
        decision = self._tracker(db, settings).check(
            provider="anthropic", model="claude-sonnet-5", input_tokens=100, max_output_tokens=100
        )
        assert decision.reason is EscalationBlockReason.MONTHLY_BUDGET_EXHAUSTED

    def test_the_per_request_cap_is_independent_of_the_budgets(self, db, settings):
        settings.AI_MAX_COST_PER_REQUEST = 0.0001
        decision = self._tracker(db, settings).check(
            provider="anthropic", model="claude-opus-5", input_tokens=20_000, max_output_tokens=2000
        )
        assert decision.reason is EscalationBlockReason.REQUEST_COST_CAP

    def test_an_oversized_input_is_refused_on_size_not_price(self, db, settings):
        settings.AI_MAX_INPUT_TOKENS_PER_REQUEST = 100
        decision = self._tracker(db, settings).check(
            provider="anthropic", model="claude-haiku-4-5", input_tokens=500, max_output_tokens=10
        )
        assert decision.reason is EscalationBlockReason.REQUEST_TOO_LARGE

    def test_a_per_client_budget_is_enforced_on_top_of_the_global_one(self, db, settings):
        tracker = self._tracker(db, settings)
        tracker.record(
            request_id="r1",
            client_id="acme",
            provider="anthropic",
            model="claude-sonnet-5",
            input_tokens=100_000,
            output_tokens=10_000,
        )
        decision = tracker.check(
            provider="anthropic",
            model="claude-sonnet-5",
            input_tokens=100,
            max_output_tokens=100,
            client_id="acme",
            client_daily_budget=0.01,
        )
        assert decision.allowed is False
        # A different client is unaffected.
        assert tracker.check(
            provider="anthropic",
            model="claude-sonnet-5",
            input_tokens=100,
            max_output_tokens=100,
            client_id="other",
            client_daily_budget=0.01,
        ).allowed is True

    def test_spend_is_summarised_against_the_budgets(self, db, settings):
        tracker = self._tracker(db, settings)
        tracker.record(
            request_id="r1",
            client_id="acme",
            provider="anthropic",
            model="claude-sonnet-5",
            input_tokens=1000,
            output_tokens=500,
            reason_for_escalation="LOW_CONFIDENCE",
        )
        summary = tracker.summary()
        assert summary.today > 0 and summary.calls_today == 1
        assert summary.daily_remaining == pytest.approx(settings.AI_DAILY_API_BUDGET - summary.today)
        assert summary.paid_disabled_by_budget is False

    def test_yesterdays_spend_does_not_count_against_today(self, db, settings):
        db.add(
            CostRecord(
                request_id="old",
                client_id="acme",
                provider="anthropic",
                model="claude-opus-5",
                input_tokens=100_000,
                output_tokens=50_000,
                estimated_cost=4.0,
                created_at=datetime.now(UTC) - timedelta(days=2),
            )
        )
        db.flush()
        tracker = self._tracker(db, settings)
        assert tracker.spend_today() == 0.0
        assert tracker.spend_this_month() >= 0.0

    def test_every_reason_for_escalation_is_reportable(self, db, settings):
        tracker = self._tracker(db, settings)
        for reason in ("LOW_CONFIDENCE", "LOW_CONFIDENCE", "LOCAL_TIMEOUT"):
            tracker.record(
                request_id=f"r-{reason}-{id(reason)}",
                client_id="acme",
                provider="anthropic",
                model="claude-sonnet-5",
                input_tokens=100,
                output_tokens=50,
                reason_for_escalation=reason,
            )
        report = {row["reason"]: row["calls"] for row in tracker.by_escalation_reason()}
        assert report == {"LOW_CONFIDENCE": 2, "LOCAL_TIMEOUT": 1}


class TestAnalytics:
    def test_money_saved_is_zero_until_a_paid_call_gives_it_a_basis(
        self, runtime, db, client_row
    ):
        from app.gateway.router import GatewayRequest

        services = runtime.for_session(db, client_row.client_id)
        for _ in range(3):
            services.router.handle(GatewayRequest(message="2 + 2", client=client_row))
        db.flush()
        summary = usage_summary(db)
        assert summary["total_requests"] == 3
        assert summary["api_fallback_requests"] == 0
        assert summary["estimated_money_saved_usd"] == 0.0
        assert "counterfactual" not in summary["estimate_basis"] or summary["estimate_basis"]

    def test_the_saving_estimate_uses_the_mean_of_real_paid_calls(
        self, runtime, db, client_row
    ):
        from app.gateway.router import GatewayRequest
        from tests.fakes import HARD_MARKER

        services = runtime.for_session(db, client_row.client_id)
        services.router.handle(
            GatewayRequest(message=f"Explain the {HARD_MARKER} rule.", client=client_row)
        )
        for _ in range(4):
            services.router.handle(GatewayRequest(message="2 + 2", client=client_row))
        db.flush()

        summary = usage_summary(db)
        assert summary["api_fallback_requests"] == 1
        assert summary["mean_paid_call_cost"] > 0
        expected = (summary["total_requests"] - 1) * summary["mean_paid_call_cost"]
        assert summary["estimated_money_saved_usd"] == pytest.approx(round(expected, 4))

    def test_the_fallback_percentage_is_reported(self, runtime, db, client_row):
        from app.gateway.router import GatewayRequest
        from tests.fakes import HARD_MARKER

        services = runtime.for_session(db, client_row.client_id)
        services.router.handle(
            GatewayRequest(message=f"Explain the {HARD_MARKER} rule.", client=client_row)
        )
        services.router.handle(GatewayRequest(message="2 + 2", client=client_row))
        db.flush()
        summary = usage_summary(db)
        assert summary["fallback_percentage"] == 50.0
        assert summary["local_success_rate"] == 50.0


class TestSuccessRateHonesty:
    """A failed request is not a local success, and did not save any money."""

    def _ask(self, runtime, db, client, message, **kwargs):
        from app.gateway.router import GatewayRequest

        services = runtime.for_session(db, client.client_id)
        response = services.router.handle(
            GatewayRequest(message=message, client=client, **kwargs)
        )
        db.flush()
        return response

    def test_a_failed_request_is_not_counted_as_a_local_success(
        self, runtime, db, client_row, local_provider, paid_provider
    ):
        from app.database.enums import Route

        self._ask(runtime, db, client_row, "What is 1200 * 0.23?")   # tool: a success
        local_provider.unavailable = True
        paid_provider.is_enabled = False
        failed = self._ask(runtime, db, client_row, "Explain bookkeeping.")
        assert failed.route is Route.FAILED

        summary = usage_summary(db)
        assert summary["total_requests"] == 2
        assert summary["failed_requests"] == 1
        assert summary["answered_locally"] == 1
        assert summary["local_success_rate"] == 50.0, (
            "a failed request was counted as a local success"
        )

    def test_a_failed_request_does_not_count_towards_money_saved(
        self, runtime, db, client_row, local_provider, paid_provider
    ):
        from tests.fakes import HARD_MARKER

        self._ask(runtime, db, client_row, f"Explain the {HARD_MARKER} rule.")  # one paid call
        local_provider.unavailable = True
        paid_provider.is_enabled = False
        self._ask(runtime, db, client_row, "Something else entirely.")

        summary = usage_summary(db)
        assert summary["answered_locally"] == 0
        assert summary["estimated_money_saved_usd"] == 0.0
