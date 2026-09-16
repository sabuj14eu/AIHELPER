"""The live connectors: news risk by the platform's rule, the trading mirror,
their intent matchers, and how the router hands live readings to the model."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.database.enums import Route
from app.gateway.router import GatewayRequest
from app.tools import build_registry
from app.tools.dispatcher import try_dispatch
from app.tools.live import (
    ELEVATED,
    HIGH,
    LOW,
    UNKNOWN,
    FeedReading,
    currency_in,
    make_market_news_spec,
    make_trading_status_spec,
    news_verdict,
    normalise_events,
)

NOW = datetime.now(UTC).replace(microsecond=0)  # the tools read the real clock


def ff(title, minutes, impact="High", country="USD", **extra):
    return {
        "title": title,
        "country": country,
        "date": (NOW + timedelta(minutes=minutes)).isoformat(),
        "impact": impact,
        **extra,
    }


def feed_transport(rows, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "user-agent" in request.headers
        return httpx.Response(status, json=rows)

    return httpx.Client(transport=httpx.MockTransport(handler))


class TestNewsVerdict:
    def reading(self, *rows, age_minutes=1):
        return FeedReading(
            events=normalise_events(list(rows)),
            fetched_at=NOW - timedelta(minutes=age_minutes),
            source="test",
        )

    def test_a_missing_calendar_is_unknown_never_low(self):
        verdict = news_verdict(None, now=NOW, max_age=timedelta(hours=3), error="timeout")
        assert verdict["state"] == UNKNOWN and "timeout" in verdict["reason"]

    def test_an_empty_week_is_unknown(self):
        verdict = news_verdict(self.reading(), now=NOW, max_age=timedelta(hours=3))
        assert verdict["state"] == UNKNOWN and "proves nothing" in verdict["reason"]

    def test_a_reading_past_its_max_age_is_unknown(self):
        reading = self.reading(ff("CPI", 30), age_minutes=200)
        verdict = news_verdict(reading, now=NOW, max_age=timedelta(hours=3), error="HTTPStatusError")
        assert verdict["state"] == UNKNOWN and "past the 3h" in verdict["reason"]

    def test_a_dead_feed_is_unknown(self):
        reading = self.reading(ff("Old NFP", -60 * 30))
        verdict = news_verdict(reading, now=NOW, max_age=timedelta(hours=3))
        assert verdict["state"] == UNKNOWN and "dead feed" in verdict["reason"]

    @pytest.mark.parametrize(
        "minutes,expected", [(30, HIGH), (60, HIGH), (61, ELEVATED), (240, ELEVATED), (241, LOW)]
    )
    def test_the_platform_windows(self, minutes, expected):
        reading = self.reading(ff("FOMC", minutes))
        verdict = news_verdict(reading, now=NOW, max_age=timedelta(hours=3))
        assert verdict["state"] == expected
        assert verdict["minutes_to_next"] == minutes

    def test_only_high_impact_events_move_the_verdict(self):
        reading = self.reading(ff("Minor speech", 10, impact="Low"), ff("CPI", 300))
        verdict = news_verdict(reading, now=NOW, max_age=timedelta(hours=3))
        assert verdict["state"] == LOW and verdict["next"]["title"] == "CPI"

    def test_past_events_do_not_count(self):
        reading = self.reading(ff("Earlier", -20), ff("Later", 500))
        assert news_verdict(reading, now=NOW, max_age=timedelta(hours=3))["state"] == LOW

    def test_rows_without_title_or_time_are_dropped_not_guessed(self):
        events = normalise_events([{"title": "", "date": NOW.isoformat()}, {"title": "x"}, ff("ok", 5)])
        assert [e["title"] for e in events] == ["ok"]


class TestMarketNewsTool:
    def test_reports_state_source_freshness_and_events(self, settings):
        settings.MARKET_NEWS_ENABLED = True
        spec = make_market_news_spec(
            settings, feed_transport([ff("CPI m/m", 90, forecast="0.3%", previous="0.2%"),
                                      ff("BoE Rate", 200, country="GBP"),
                                      ff("Speech", 30, impact="Medium")])
        )
        result = spec.handler()
        assert result.ok and result.value["state"] == ELEVATED
        assert "Market news risk: ELEVATED" in result.display
        assert "fetched" in result.display and "age" in result.display
        assert "CPI m/m" in result.display and "forecast 0.3%" in result.display
        assert result.value["upcoming_high"][0]["title"] == "CPI m/m"
        assert result.meta["live"] and result.meta["untrusted"]

        usd_only = spec.handler(currency="USD")
        assert "BoE Rate" not in usd_only.display and "CPI m/m" in usd_only.display

    def test_a_failed_fetch_with_no_reading_is_unknown(self, settings):
        settings.MARKET_NEWS_ENABLED = True
        spec = make_market_news_spec(settings, feed_transport([], status=503))
        result = spec.handler()
        assert result.ok and result.value["state"] == UNKNOWN
        assert "HTTPStatusError" in result.display

    def test_a_fresh_cache_survives_a_failed_refresh_but_not_forever(self, settings, monkeypatch):
        settings.MARKET_NEWS_ENABLED = True
        settings.MARKET_NEWS_REFRESH_SECONDS = 0
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(200, json=[ff("CPI", 90)])
            return httpx.Response(500)

        spec = make_market_news_spec(settings, httpx.Client(transport=httpx.MockTransport(handler)))
        first = spec.handler()
        assert first.value["state"] == ELEVATED
        # Refresh fails: the last good reading stands while it is young enough…
        second = spec.handler()
        assert second.value["state"] == ELEVATED and second.value["error"] == "HTTPStatusError"
        # …and is UNKNOWN once older than the maximum age.
        settings.MARKET_NEWS_MAX_AGE_HOURS = 0.0
        third = spec.handler()
        assert third.value["state"] == UNKNOWN

    def test_disabled_is_an_honest_error(self, settings):
        settings.MARKET_NEWS_ENABLED = False
        result = make_market_news_spec(settings, feed_transport([])).handler()
        assert not result.ok and "disabled" in result.error

    def test_intents(self, settings):
        settings.MARKET_NEWS_ENABLED = True
        intent = make_market_news_spec(settings, feed_transport([])).intent
        assert intent("news today?").direct
        assert intent("any high impact news this week").arguments == {"hours": 168}
        assert intent("what is the calendar for gold").arguments == {"currency": "USD"}
        assert intent("EUR news").arguments == {"currency": "EUR"}
        context = intent("should we be careful trading gold with the news this afternoon?")
        assert context is not None and not context.direct
        assert intent("what is the capital of France?") is None

    def test_currency_words(self):
        assert currency_in("gold and silver") == "USD"
        assert currency_in("the pound") == "GBP"
        assert currency_in("nothing here") is None


def platform_transport(*, fail: set[str] = frozenset(), stats_overrides: dict | None = None):
    return httpx.Client(
        transport=httpx.MockTransport(platform_handler(fail=fail, stats_overrides=stats_overrides))
    )


def platform_handler(*, fail: set[str] = frozenset(), stats_overrides: dict | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"].startswith("Bearer bb_")
        path = request.url.path
        if any(f in path for f in fail):
            return httpx.Response(500)
        if path.endswith("/portfolio"):
            return httpx.Response(200, json={"balance": 10000.0, "equity": 10042.1, "free_margin": 9000.0,
                                             "floating_pnl": 42.1, "accounts": 2, "online": 1})
        if path.endswith("/stats"):
            body = {"count": 37, "low_sample": True, "min_sample": 100,
                    "win_rate": 54.1, "profit_factor": 1.21, "total_profit": 312.5}
            body.update(stats_overrides or {})
            return httpx.Response(200, json=body)
        if path.endswith("/trades"):
            assert request.url.params["status"] == "open"
            return httpx.Response(200, json=[{"symbol": "GOLD", "direction": "BUY", "lots": 0.1,
                                              "entry": 4460.2, "sl": 4440.0, "tp": 4500.0, "status": "open",
                                              "profit": 12.3, "session": "asia",
                                              "open_time": "2026-09-16T09:12:00+00:00"}])
        if path.endswith("/signals"):
            return httpx.Response(200, json=[{"signal_id": "SS-BUY-1", "system": "BSv18", "symbol": "GOLD",
                                              "tf": "M15", "direction": "BUY", "status": "executed",
                                              "grade": "A", "rr": 1.8, "created_at": "2026-09-16T11:02:00+00:00"}])
        return httpx.Response(404)

    return handler


class TestTradingStatusTool:
    def configure(self, settings):
        settings.TRADING_STATUS_ENABLED = True
        settings.TRADING_PLATFORM_URL = "https://platform.example"
        settings.TRADING_PLATFORM_API_KEY = "bb_test_key_not_real"

    def test_unconfigured_is_inert(self, settings):
        settings.TRADING_STATUS_ENABLED = True
        spec = make_trading_status_spec(settings, platform_transport())
        result = spec.handler()
        assert not result.ok and "not configured" in result.error
        assert spec.intent("bot status") is None

    def test_reports_every_section_with_freshness_and_the_sample_size(self, settings):
        self.configure(settings)
        result = make_trading_status_spec(settings, platform_transport()).handler()
        assert result.ok, result.error
        assert "DEMO" in result.display and "platform.example" in result.display
        assert "1 of 2 online" in result.display
        assert "GOLD BUY 0.1 lots" in result.display
        assert "SS-BUY-1" in result.display
        assert "n=37" in result.display and "LOW SAMPLE" in result.display
        assert "bb_test_key_not_real" not in result.display
        assert not result.meta["partial"]

    def test_the_win_rate_carries_its_unit(self, settings):
        """54.1 next to "profit factor 1.21" is a number the reader has to guess at.

        The platform's analytics.core_stats returns win_rate as a percentage.
        """
        self.configure(settings)
        result = make_trading_status_spec(settings, platform_transport()).handler()
        assert "win rate 54.1%" in result.display

    def test_a_null_statistic_reads_unknown_rather_than_vanishing(self, settings):
        """The platform sends profit_factor: null when there were no losing trades.

        Dropping the key made that look like "the platform did not report it".
        Absence is not zero and it is not silence, and Brother does not guess
        which of the two the platform meant.
        """
        self.configure(settings)
        result = make_trading_status_spec(
            settings, platform_transport(stats_overrides={"profit_factor": None})
        ).handler()
        assert "profit factor UNKNOWN" in result.display

    def test_a_failed_section_is_unknown_not_missing(self, settings):
        self.configure(settings)
        result = make_trading_status_spec(settings, platform_transport(fail={"stats"})).handler()
        assert result.ok and result.meta["partial"]
        assert "Stats: UNKNOWN (HTTP 500)" in result.display
        assert "1 of 2 online" in result.display

    def test_all_sections_failing_is_a_failure_without_the_key(self, settings):
        self.configure(settings)
        result = make_trading_status_spec(
            settings, platform_transport(fail={"portfolio", "stats", "trades", "signals"})
        ).handler()
        assert not result.ok and "HTTP 500" in result.error
        assert "bb_test_key_not_real" not in result.error

    def test_intents(self, settings):
        self.configure(settings)
        intent = make_trading_status_spec(settings, platform_transport()).intent
        assert intent("bot status").direct
        assert intent("how is the bot doing?").direct
        assert intent("show open trades").direct
        assert intent("last signals").direct
        why = intent("why did the bot skip the last gold signal?")
        assert why is not None and not why.direct
        plan = intent("Gold now 4351 so what is your trading plan boss today big news day")
        assert plan is not None and not plan.direct
        assert intent("what is 2 + 2") is None


class TestDispatchAndRouting:
    @pytest.fixture
    def live_registry(self, settings):
        settings.MARKET_NEWS_ENABLED = True
        settings.TRADING_STATUS_ENABLED = True
        settings.TRADING_PLATFORM_URL = "https://platform.example"
        settings.TRADING_PLATFORM_API_KEY = "bb_test_key_not_real"

        platform = platform_handler()

        def handler(request: httpx.Request) -> httpx.Response:
            if "faireconomy" in request.url.host:
                return httpx.Response(200, json=[ff("CPI m/m", 45)])
            return platform(request)

        return build_registry(settings, http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    def test_a_short_news_question_is_answered_at_level_zero(self, live_registry):
        dispatch = try_dispatch("news today?", live_registry)
        assert dispatch.matched and dispatch.tool == "market_news"
        assert "Market news risk: HIGH" in dispatch.answer

    def test_a_reasoning_question_gets_the_reading_as_context_instead(self, live_registry):
        dispatch = try_dispatch(
            "should we be careful trading gold this session given the news?", live_registry
        )
        assert not dispatch.matched
        # "trading" and "news" both matched: the model gets both readings.
        assert {i.source for i in dispatch.context_items} == {"tool:market_news", "tool:trading_status"}
        news = next(i for i in dispatch.context_items if i.source == "tool:market_news")
        assert news.ref == "HIGH"

    def test_a_narrowed_client_cannot_reach_a_live_tool(self, live_registry):
        dispatch = try_dispatch("news today?", live_registry, allowed_tools=["calculator"])
        assert not dispatch.matched and dispatch.context_items == []

    def test_the_router_hands_live_readings_to_the_model_and_cites_them(
        self, runtime, db, client_row, local_provider, paid_provider, live_registry
    ):
        from app.agents.builtin import TRADING

        runtime.tools = live_registry
        services = runtime.for_session(db, client_row.client_id)
        response = services.router.handle(
            GatewayRequest(
                message="why should we be careful with the bot today given the news?",
                client=client_row,
                agent=TRADING,
            )
        )
        assert response.route is Route.LOCAL, response.notes
        sources = {s["source"] for s in response.sources}
        assert {"tool:market_news", "tool:trading_status"} <= sources
        assert any(n.startswith("live data supplied by") for n in response.notes)
        prompt = local_provider.calls[-1].messages[-1].content
        assert "Market news risk: HIGH" in prompt and "1 of 2 online" in prompt
        assert paid_provider.call_count == 0

    def test_direct_status_is_free_and_cites_the_tool(self, runtime, db, client_row, local_provider, live_registry):
        runtime.tools = live_registry
        services = runtime.for_session(db, client_row.client_id)
        response = services.router.handle(GatewayRequest(message="bot status", client=client_row))
        assert response.route is Route.TOOL and response.tool_used == "trading_status"
        assert "1 of 2 online" in response.answer
        assert local_provider.calls == []

    def test_brother_agents_prefer_the_strong_local_model_when_installed(
        self, runtime, db, client_row, settings, local_provider
    ):
        from app.agents.builtin import BROTHER, GENERAL

        seen: list = []
        original = local_provider.resolve_model

        def recording(task_type, requested=None):
            seen.append(requested)
            return original(task_type, requested)

        local_provider.resolve_model = recording
        services = runtime.for_session(db, client_row.client_id)
        services.router.handle(GatewayRequest(message="What is the capital of France?", client=client_row, agent=BROTHER))
        services.router.handle(GatewayRequest(message="What is the capital of France?", client=client_row, agent=GENERAL))
        assert seen == [settings.STRONG_LOCAL_MODEL, None]
        assert json.dumps(BROTHER.as_dict())  # serialisable for /api/v1/agents
