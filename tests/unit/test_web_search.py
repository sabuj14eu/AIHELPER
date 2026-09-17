"""Reading a SearXNG answer.

The backend is self-hosted SearXNG (explicit decision, 2026-09-17): no
commercial API, no key, no per-query cost, a fixed endpoint on the compose
network. These tests pin the two things about it that are easy to get wrong
and impossible to notice from the code:

* SearXNG calls the snippet `content`, not `snippet`, and it answers **HTML**
  unless the request says `format=json` *and* the instance lists `json` under
  `search.formats`. Both halves are needed; either one missing produces a body
  the parser cannot read, and the failure looks identical in both cases.

* Phase 1 reads **snippets only**. A result URL is provenance, never a fetch
  target. Nothing in this module may open one.
"""

from __future__ import annotations

import httpx
import pytest

from app.tools.web_search import MAX_RESULTS, make_web_search_spec

# Shaped like a real SearXNG `?format=json` body, down to the keys the parser
# does not read. Trimmed, not invented: the ignored keys are here on purpose,
# because a parser that only survives the fields it knows about is not tested.
SEARXNG_BODY = {
    "query": "gold price today",
    "number_of_results": 0,
    "results": [
        {
            "url": "https://www.reuters.com/markets/commodities/gold-2026-09-17/",
            "title": "Gold holds near record before Fed decision",
            "content": "Spot gold was little changed at $4,271 an ounce ahead of the "
                       "Federal Reserve's policy decision later on Wednesday.",
            "engine": "duckduckgo",
            "parsed_url": ["https", "www.reuters.com", "/markets/commodities/", "", "", ""],
            "template": "default.html",
            "engines": ["duckduckgo", "brave"],
            "positions": [1, 2],
            "publishedDate": "2026-09-17T06:12:00",
            "score": 4.0,
            "category": "general",
        },
        {
            "url": "https://www.kitco.com/news/2026-09-17/silver-63",
            "title": "Silver pushes through $63",
            "content": "Silver traded at $63.10, its highest in three weeks.",
            "engine": "brave",
            "score": 2.0,
            "category": "general",
        },
    ],
    "answers": [],
    "corrections": [],
    "infoboxes": [],
    "suggestions": [],
    "unresponsive_engines": [],
}


@pytest.fixture
def enabled(settings):
    settings.WEB_SEARCH_ENABLED = True
    settings.WEB_SEARCH_URL = "http://searxng:8080/search"
    settings.WEB_SEARCH_API_KEY = None
    return settings


def _search(settings, handler, **kwargs):
    """Run the tool against a fake SearXNG. ``handler`` sees the request."""
    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        spec = make_web_search_spec(settings, client)
        return spec.handler(**kwargs)
    finally:
        client.close()


def _ok(request):
    return httpx.Response(200, json=SEARXNG_BODY)


class TestTheRequestSearxngNeeds:
    def test_it_asks_for_json_because_searxng_defaults_to_html(self, enabled):
        """The bug this pins: without `format=json` the 200 body is a web page.

        It parses as "non-JSON body", which reads like the instance is broken
        when in fact the request was wrong — so the fix gets aimed at the
        wrong end. The parameter goes on every request.
        """
        seen = {}

        def handler(request):
            seen["params"] = dict(request.url.params)
            return _ok(request)

        result = _search(enabled, handler, query="gold price today")
        assert result.ok
        assert seen["params"]["format"] == "json"
        assert seen["params"]["q"] == "gold price today"

    def test_no_authorization_header_when_there_is_no_key(self, enabled):
        """SearXNG needs no credential, and sending an empty bearer to a
        self-hosted service is a habit worth not forming."""
        seen = {}

        def handler(request):
            seen["headers"] = request.headers
            return _ok(request)

        _search(enabled, handler, query="gold price today")
        assert "authorization" not in seen["headers"]


class TestReadingTheBody:
    def test_the_snippet_comes_from_content(self, enabled):
        """SearXNG's key is `content`. Reading only `snippet` yields results
        with titles, URLs and nothing to read — which still looks like success."""
        result = _search(enabled, _ok, query="gold price today")
        assert result.ok
        first = result.value[0]
        assert first["snippet"].startswith("Spot gold was little changed")
        assert first["title"] == "Gold holds near record before Fed decision"
        assert first["url"].startswith("https://www.reuters.com/")

    def test_every_result_carries_its_provenance(self, enabled):
        """Source, time of retrieval, and publication date where the engine
        gave one. A snippet without these is a claim with no author."""
        result = _search(enabled, _ok, query="gold price today")
        first = result.value[0]
        assert first["engine"] == "duckduckgo"
        assert first["published"] == "2026-09-17T06:12:00"
        assert first["fetched_at"] and first["fetched_at"] == result.meta["fetched_at"]

    def test_the_result_set_is_marked_untrusted_and_snippets_only(self, enabled):
        result = _search(enabled, _ok, query="gold price today")
        assert result.meta["untrusted"] is True
        assert result.meta["snippets_only"] is True
        assert result.meta["count"] == 2

    def test_the_same_page_from_two_engines_is_one_source(self, enabled):
        """Two engines agreeing is not two witnesses. Counting the same URL
        twice would make one claim look corroborated."""
        duplicated = {
            "results": [
                {"url": "https://example.com/a", "title": "A", "content": "x", "engine": "ddg"},
                {"url": "https://example.com/a/", "title": "A", "content": "x", "engine": "brave"},
                {"url": "https://example.com/b", "title": "B", "content": "y", "engine": "ddg"},
            ]
        }
        result = _search(
            enabled,
            lambda request: httpx.Response(200, json=duplicated),
            query="anything at all",
        )
        assert [r["url"] for r in result.value] == [
            "https://example.com/a",
            "https://example.com/b",
        ]

    def test_a_result_without_a_url_is_dropped(self, enabled):
        body = {"results": [{"title": "no link", "content": "orphan"}, *SEARXNG_BODY["results"]]}
        result = _search(
            enabled, lambda request: httpx.Response(200, json=body), query="gold price today"
        )
        assert all(r["url"] for r in result.value)
        assert result.meta["count"] == 2

    def test_the_limit_is_capped_however_it_is_asked_for(self, enabled):
        body = {"results": [
            {"url": f"https://example.com/{i}", "title": str(i), "content": "c"}
            for i in range(50)
        ]}
        result = _search(
            enabled,
            lambda request: httpx.Response(200, json=body),
            query="anything at all",
            limit=100,
        )
        assert len(result.value) == MAX_RESULTS


class TestWhenItGoesWrong:
    def test_an_html_body_is_reported_as_a_body_not_as_a_crash(self, enabled):
        """What a SearXNG instance that does not list `json` under
        `search.formats` actually returns: HTTP 200, and a web page."""
        result = _search(
            enabled,
            lambda request: httpx.Response(200, text="<!DOCTYPE html><html>…</html>"),
            query="gold price today",
        )
        assert not result.ok
        assert "non-JSON" in result.error

    def test_the_limiter_saying_429_is_reported_not_swallowed(self, enabled):
        """SearXNG's bot limiter reads a server-side caller as a bot. It is
        off in deploy/searxng/settings.yml; if it is ever on, this is the
        failure, and it must not arrive as an empty result set that looks
        like the web simply had nothing to say."""
        result = _search(
            enabled, lambda request: httpx.Response(429, text="Too Many Requests"),
            query="gold price today",
        )
        assert not result.ok and "failed" in result.error

    def test_a_timeout_says_so(self, enabled):
        def handler(request):
            raise httpx.ReadTimeout("slow", request=request)

        result = _search(enabled, handler, query="gold price today")
        assert not result.ok and "timed out" in result.error

    def test_an_unexpected_shape_is_refused(self, enabled):
        result = _search(
            enabled, lambda request: httpx.Response(200, json={"results": "nope"}),
            query="gold price today",
        )
        assert not result.ok and "unexpected shape" in result.error

    def test_disabled_is_the_default_and_answers_before_any_request(self, settings):
        def handler(request):  # pragma: no cover - must never run
            raise AssertionError("a disabled tool reached the network")

        settings.WEB_SEARCH_ENABLED = False
        result = _search(settings, handler, query="gold price today")
        assert not result.ok and "disabled" in result.error

    def test_enabled_without_an_endpoint_names_the_missing_setting(self, settings):
        def handler(request):  # pragma: no cover - must never run
            raise AssertionError("no endpoint, yet something was requested")

        settings.WEB_SEARCH_ENABLED = True
        settings.WEB_SEARCH_URL = None
        result = _search(settings, handler, query="gold price today")
        assert not result.ok and "WEB_SEARCH_URL" in result.error

    def test_a_two_character_query_is_not_sent(self, enabled):
        def handler(request):  # pragma: no cover - must never run
            raise AssertionError("a meaningless query was sent to a third party")

        result = _search(enabled, handler, query="go")
        assert not result.ok
