"""The read-only market mirror: what it reads, and what it refuses to invent.

AI Helper is not a second trading bot. It is a read-only consumer of the
platform's market data, and these tests are mostly about the second half of
that sentence — the mirror must never soften a stale answer, never fill a
missing one, and never let a web search anywhere near a price.
"""

from __future__ import annotations

import httpx
import pytest

from app.market.mirror import (
    ENDPOINTS,
    NOT_CONFIGURED,
    OK,
    REFUSED,
    UNREACHABLE,
    MarketMirror,
)

PLATFORM = "https://platform.example/"

LIVE_SNAPSHOT = {
    "symbol": "GOLD",
    "price_source": "MT5 via mt5_reporter (broker feed), stored as closed candles",
    "quote": {"state": "UNAVAILABLE", "bid": None, "ask": None, "note": "no bid/ask/tick exists"},
    "read_only": True,
    "snapshot": {
        "meta": {"symbol": "GOLD", "session": "LONDON"},
        "freshness": {"candles": {"state": "LIVE", "age_min": 12, "limit_min": 45}},
        "market": {"last_close": 4271.5, "atr": 6.2, "structure": "HH/HL"},
    },
}


@pytest.fixture
def configured(settings):
    settings.TRADING_PLATFORM_URL = PLATFORM
    settings.TRADING_PLATFORM_API_KEY = "bb_test_key_not_real"
    return settings


def mirror_for(settings, handler) -> MarketMirror:
    return MarketMirror(settings, httpx.Client(transport=httpx.MockTransport(handler)))


def serve(payload, status=200):
    return lambda request: httpx.Response(status, json=payload)


class TestItOnlyEverReads:
    def test_every_request_is_a_get(self, configured):
        seen = []

        def handler(request):
            seen.append(request.method)
            return httpx.Response(200, json=LIVE_SNAPSHOT)

        m = mirror_for(configured, handler)
        m.snapshot("GOLD")
        m.desk("GOLD")
        m.candles("GOLD")
        m.outlook("GOLD")
        assert seen == ["GET"] * 4

    def test_no_request_carries_a_body(self, configured):
        bodies = []

        def handler(request):
            bodies.append(request.content)
            return httpx.Response(200, json=LIVE_SNAPSHOT)

        mirror_for(configured, handler).snapshot("GOLD")
        assert bodies == [b""]

    def test_an_unknown_endpoint_cannot_be_requested(self, configured):
        """The caller names an endpoint, never a URL. Nothing a caller passes
        can steer this at another host or another route."""
        m = mirror_for(configured, serve(LIVE_SNAPSHOT))
        with pytest.raises(ValueError, match="unknown market endpoint"):
            m.read("../../admin/keys", symbol="GOLD")

    def test_only_the_configured_host_is_ever_reached(self, configured):
        hosts = []

        def handler(request):
            hosts.append(request.url.host)
            return httpx.Response(200, json=LIVE_SNAPSHOT)

        m = mirror_for(configured, handler)
        for call in (m.snapshot, m.desk, m.outlook):
            call("GOLD")
        m.candles("GOLD")
        assert set(hosts) == {"platform.example"}

    def test_the_four_endpoints_are_the_only_four(self):
        assert set(ENDPOINTS) == {"snapshot", "desk", "candles", "outlook"}


class TestTheKeyNeverLeaks:
    def test_it_is_sent_as_a_bearer_header(self, configured):
        seen = {}

        def handler(request):
            seen["auth"] = request.headers.get("authorization")
            return httpx.Response(200, json=LIVE_SNAPSHOT)

        mirror_for(configured, handler).snapshot("GOLD")
        assert seen["auth"] == "Bearer bb_test_key_not_real"

    @pytest.mark.parametrize("status", [401, 403, 500])
    def test_the_key_never_appears_in_a_failure_note(self, configured, status):
        """Iron Rule 7: the platform key is read from settings and never
        enters a tool's output or error."""
        result = mirror_for(configured, serve({"detail": "nope"}, status)).snapshot("GOLD")
        assert not result.ok
        assert "bb_test_key_not_real" not in result.note
        assert "bb_test_key_not_real" not in str(result.as_dict())


class TestAbsenceIsNamed:
    def test_an_unconfigured_connector_says_so_without_calling_anything(self, settings):
        def handler(request):  # pragma: no cover - must never run
            raise AssertionError("an unconfigured mirror reached the network")

        settings.TRADING_PLATFORM_URL = ""
        settings.TRADING_PLATFORM_API_KEY = ""
        result = mirror_for(settings, handler).snapshot("GOLD")
        assert result.state == NOT_CONFIGURED
        assert "TRADING_PLATFORM_URL" in result.note

    def test_a_timeout_is_named_not_raised(self, configured):
        def handler(request):
            raise httpx.ReadTimeout("slow", request=request)

        result = mirror_for(configured, handler).snapshot("GOLD")
        assert result.state == UNREACHABLE and "timed out" in result.note

    def test_a_rejected_key_is_its_own_state(self, configured):
        """"The key is wrong" and "the platform is down" have opposite fixes."""
        result = mirror_for(configured, serve({"detail": "x"}, 401)).snapshot("GOLD")
        assert result.state == REFUSED and "rejected this API key" in result.note

    def test_the_platforms_own_400_message_is_passed_through(self, configured):
        """"unknown timeframe '7m'" is the useful half of that failure, and
        flattening it to "it failed" aims the fix at the wrong end."""
        result = mirror_for(
            configured, serve({"detail": "unknown timeframe '7m'"}, 400)
        ).candles("GOLD", "7m")
        assert result.state == REFUSED and "7m" in result.note

    def test_a_non_json_body_is_named(self, configured):
        result = mirror_for(
            configured, lambda r: httpx.Response(200, text="<html>proxy error</html>")
        ).snapshot("GOLD")
        assert result.state == UNREACHABLE and "non-JSON" in result.note

    @pytest.mark.parametrize("state", [NOT_CONFIGURED, UNREACHABLE, REFUSED])
    def test_a_failed_read_reports_freshness_unknown_never_fresh(self, configured, state):
        result = mirror_for(
            configured, serve({"detail": "x"}, 503)
        ).snapshot("GOLD")
        assert result.freshness["state"] == "UNKNOWN"
        assert result.is_usable is False


class TestFreshnessIsNeverSoftened:
    def test_a_live_read_is_usable(self, configured):
        result = mirror_for(configured, serve(LIVE_SNAPSHOT)).snapshot("GOLD")
        assert result.state == OK
        assert result.freshness["state"] == "LIVE"
        assert result.is_usable is True

    def test_a_stale_read_is_not_usable(self, configured):
        """STALE is not a degraded yes. The platform's own rule is that a
        stale feed produces NO levels; a mirror that softened that would be
        the first place the Freshness Law leaked."""
        stale = {**LIVE_SNAPSHOT, "snapshot": {
            **LIVE_SNAPSHOT["snapshot"],
            "freshness": {"candles": {"state": "STALE", "age_min": 300, "limit_min": 45}},
        }}
        result = mirror_for(configured, serve(stale)).snapshot("GOLD")
        assert result.ok
        assert result.freshness["state"] == "STALE"
        assert result.is_usable is False, "stale data must never be reasoned from"

    def test_freshness_is_never_synthesised_when_the_platform_omits_it(self, configured):
        """UNKNOWN, not fine. If the platform did not say how fresh something
        is, we do not know — and guessing fresh is the dangerous guess."""
        result = mirror_for(configured, serve({"symbol": "GOLD"})).snapshot("GOLD")
        assert result.ok
        assert result.freshness["state"] == "UNKNOWN"
        assert result.is_usable is False

    def test_a_candles_response_uses_its_own_freshness_block(self, configured):
        body = {"symbol": "GOLD", "tf": "15m", "count": 2,
                "freshness": {"state": "LIVE", "age_min": 5, "limit_min": 45},
                "candles": [{"ts": "2026-09-17T09:00:00+00:00", "close": 4271.0}]}
        result = mirror_for(configured, serve(body)).candles("GOLD")
        assert result.freshness["age_min"] == 5 and result.is_usable


class TestNothingIsInvented:
    def test_the_platforms_unavailable_quote_survives_the_mirror(self, configured):
        result = mirror_for(configured, serve(LIVE_SNAPSHOT)).snapshot("GOLD")
        quote = result.as_dict()["data"]["quote"]
        assert quote["state"] == "UNAVAILABLE"
        assert quote["bid"] is None and quote["ask"] is None

    def test_the_mirror_adds_no_price_of_its_own(self, configured):
        """It hands the platform's object back unchanged. Anything the mirror
        added to `data` would be a number with no publisher."""
        result = mirror_for(configured, serve(LIVE_SNAPSHOT)).snapshot("GOLD")
        assert result.as_dict()["data"] == LIVE_SNAPSHOT

    def test_the_source_is_named_on_every_answer(self, configured):
        for payload, status in ((LIVE_SNAPSHOT, 200), ({"detail": "x"}, 500)):
            result = mirror_for(configured, serve(payload, status)).snapshot("GOLD")
            assert result.as_dict()["mirror"]["source"] == (
                "SignalMesh platform (read-only mirror)"
            )

    def test_the_mirror_module_cannot_see_a_web_search(self):
        """The separation, read from the import graph. A web snippet saying
        "gold is around 4270" must not be able to reach a price field, and
        the way to guarantee that is for this module not to import the thing
        that produces snippets."""
        import ast
        from pathlib import Path

        tree = ast.parse(
            Path(__file__).resolve().parents[2].joinpath("app/market/mirror.py").read_text()
        )
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
        for module in imported:
            assert "web_search" not in module and "research" not in module, module


class TestTheParametersSent:
    def test_candles_sends_symbol_timeframe_and_count(self, configured):
        seen = {}

        def handler(request):
            seen.update(dict(request.url.params))
            return httpx.Response(200, json={"count": 0, "candles": []})

        mirror_for(configured, handler).candles("GOLD", "1h", 120)
        assert seen == {"symbol": "GOLD", "tf": "1h", "n": "120"}

    def test_a_none_parameter_is_dropped_rather_than_sent_as_the_string_none(
        self, configured
    ):
        seen = {}

        def handler(request):
            seen.update(dict(request.url.params))
            return httpx.Response(200, json={})

        mirror_for(configured, handler).read("snapshot", symbol="GOLD", tf=None)
        assert seen == {"symbol": "GOLD"}
