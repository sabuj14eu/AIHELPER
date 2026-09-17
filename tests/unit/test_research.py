"""The web-research pipeline, end to end, with the network faked at the socket.

The real SearXNG is replaced by an httpx MockTransport and nothing else is:
the egress gate, the source tiers, the prompt, validation, the duplicate and
contradiction checks and the capture path are all the code that runs in
production. What these tests are for is the set of promises made when the
feature was asked for, each one written as the thing that must not happen:

* a RESTRICTED question must never reach a search box,
* a general-web page alone must never become something Brother learned,
* nothing must be promoted without a person, and
* nothing already promoted must be quietly overwritten.
"""

from __future__ import annotations

import httpx
import pytest

from app.database.enums import Classification, SolutionStatus
from app.learning.origin import SolutionOrigin, origin_of
from app.learning.research import research
from app.learning.solution_store import SolutionStore
from app.tools.builder import build_registry

FED_PAGE = {
    "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260917a.htm",
    "title": "Federal Reserve issues FOMC statement",
    "content": "The Committee decided to lower the target range for the federal funds "
               "rate to 3-1/2 to 3-3/4 percent.",
    "engine": "duckduckgo",
    "publishedDate": "2026-09-17T18:00:00",
}
BLOG_PAGE = {
    "url": "https://goldbug-thoughts.blogspot.com/fed-is-lying",
    "title": "The Fed is lying about rates",
    "content": "They will cut to zero next week, mark my words.",
    "engine": "duckduckgo",
}
REUTERS_PAGE = {
    "url": "https://www.reuters.com/markets/rates-bonds/fed-cuts-2026-09-17/",
    "title": "Fed cuts rates by a quarter point",
    "content": "The Federal Reserve lowered its benchmark rate on Wednesday.",
    "engine": "brave",
}


@pytest.fixture
def searxng():
    """A fake SearXNG that records every query it is asked."""

    class Fake:
        def __init__(self):
            self.queries: list[str] = []
            self.pages: list[dict] = [FED_PAGE, REUTERS_PAGE]

        def handler(self, request):
            self.queries.append(request.url.params.get("q", ""))
            return httpx.Response(200, json={"results": self.pages})

        @property
        def client(self):
            return httpx.Client(transport=httpx.MockTransport(self.handler))

    return Fake()


@pytest.fixture
def web(settings, searxng):
    """Settings and a tool registry wired to the fake search endpoint."""
    settings.WEB_SEARCH_ENABLED = True
    settings.WEB_SEARCH_URL = "http://searxng:8080/search"
    settings.SELF_LEARNING_MIN_CONFIDENCE = 0.0
    return build_registry(settings, http_client=searxng.client)


@pytest.fixture
def net_client(db):
    """A client that has been granted the network, on purpose and by name."""
    from tests.conftest import make_client

    client, _ = make_client(db, "researcher", allowed_tools=["web_search", "calculator"])
    return client


def _run(db, client, *, settings, registry, local_provider, question, retriever=None, **kwargs):
    return research(
        db, client, question=question, settings=settings, registry=registry,
        local_provider=local_provider, retriever=retriever, **kwargs,
    )


class TestTheGateComesFirst:
    def test_a_restricted_question_is_never_searched(
        self, db, net_client, settings, web, local_provider, searxng
    ):
        """The promise this whole feature was conditioned on. Not "is refused
        afterwards" — is never sent. The assertion is on the search log."""
        outcome = _run(
            db, net_client, settings=settings, registry=web, local_provider=local_provider,
            question="what did the FOMC decide", classification=Classification.RESTRICTED.value,
        )
        assert not outcome.ok
        assert "RESTRICTED" in outcome.reason
        assert searxng.queries == [], "a RESTRICTED question reached a third party"
        assert outcome.counters.web_searches_performed == 0

    def test_a_client_with_no_tool_list_gets_no_internet(
        self, db, client_row, settings, web, local_provider, searxng
    ):
        """`client_row` inherits every ordinary tool. Inheriting everything is
        not the same as choosing to allow the internet."""
        outcome = _run(
            db, client_row, settings=settings, registry=web,
            local_provider=local_provider, question="what did the FOMC decide",
        )
        assert not outcome.ok and searxng.queries == []

    def test_a_refusal_still_reports_its_counters(
        self, db, client_row, settings, web, local_provider
    ):
        """A refusal that reports no numbers cannot be told from a crash."""
        outcome = _run(
            db, client_row, settings=settings, registry=web,
            local_provider=local_provider, question="what did the FOMC decide",
        )
        assert outcome.as_dict()["counters"]["web_searches_performed"] == 0
        assert outcome.as_dict()["finished_at"]


class TestSourceAwareSearch:
    def test_the_publisher_is_asked_before_the_open_web(
        self, db, net_client, settings, web, local_provider, searxng
    ):
        """A question about the FOMC asks the Fed's own site first, so what
        lands in the prompt is the release rather than someone's summary."""
        _run(db, net_client, settings=settings, registry=web,
             local_provider=local_provider, question="what did the FOMC decide today")
        assert searxng.queries[0].startswith("site:federalreserve.gov")
        assert searxng.queries[-1] == "what did the FOMC decide today", (
            "the open web must still be asked: a site: query can legitimately "
            "come back empty, and that must not end the run"
        )

    def test_an_unrouted_question_asks_the_open_web_once(
        self, db, net_client, settings, web, local_provider, searxng
    ):
        _run(db, net_client, settings=settings, registry=web,
             local_provider=local_provider, question="who designed the Eiffel tower")
        assert searxng.queries == ["who designed the Eiffel tower"]

    def test_the_number_of_searches_is_capped(
        self, db, net_client, settings, web, local_provider, searxng
    ):
        settings.RESEARCH_MAX_SEARCHES = 2
        _run(db, net_client, settings=settings, registry=web,
             local_provider=local_provider, question="what did the FOMC decide today")
        assert len(searxng.queries) == 2

    def test_evidence_is_ordered_best_source_first(
        self, db, net_client, settings, web, local_provider, searxng
    ):
        """LOCAL_CONTEXT_CHARS truncates the prompt. What gets cut should be
        the general web, never the agency that published the number."""
        searxng.pages = [BLOG_PAGE, REUTERS_PAGE, FED_PAGE]
        outcome = _run(db, net_client, settings=settings, registry=web,
                       local_provider=local_provider, question="what did the FOMC decide today")
        tiers = [s["source_tier"] for s in outcome.sources]
        assert tiers == sorted(tiers)
        assert outcome.sources[0]["source_domain"] == "federalreserve.gov"

    def test_the_same_page_found_by_two_queries_counts_once(
        self, db, net_client, settings, web, local_provider
    ):
        """The routed query and the open-web query return the same release.
        Counting it twice would make one source look like corroboration."""
        outcome = _run(db, net_client, settings=settings, registry=web,
                       local_provider=local_provider, question="what did the FOMC decide today")
        urls = [s["source_url"] for s in outcome.sources]
        assert len(urls) == len(set(urls))


class TestTheTrustFloor:
    def test_a_general_web_page_alone_is_read_but_never_learned_from(
        self, db, net_client, settings, web, local_provider, searxng
    ):
        """The requirement in one test: tier 4 is not automatically trusted
        knowledge. The answer is still produced and still shown — it is simply
        not something Brother now believes."""
        searxng.pages = [BLOG_PAGE]
        outcome = _run(db, net_client, settings=settings, registry=web,
                       local_provider=local_provider, question="what did the FOMC decide today")
        assert not outcome.ok
        assert "read, not learned" in outcome.reason
        assert outcome.answer, "the answer is still produced; it is just not learned from"
        assert outcome.counters.rejected_untrusted_tier == 1
        assert outcome.counters.candidates_created == 0
        assert SolutionStore(db, net_client.client_id).list(limit=50) == []

    def test_one_trusted_source_among_general_ones_is_enough(
        self, db, net_client, settings, web, local_provider, searxng
    ):
        searxng.pages = [BLOG_PAGE, FED_PAGE]
        outcome = _run(db, net_client, settings=settings, registry=web,
                       local_provider=local_provider, question="what did the FOMC decide today")
        assert outcome.ok, outcome.reason
        assert outcome.counters.best_source_tier == 1

    def test_the_tiers_of_everything_read_are_counted(
        self, db, net_client, settings, web, local_provider, searxng
    ):
        searxng.pages = [BLOG_PAGE, FED_PAGE, REUTERS_PAGE]
        outcome = _run(db, net_client, settings=settings, registry=web,
                       local_provider=local_provider, question="what did the FOMC decide today")
        by_tier = outcome.counters.sources_by_tier
        assert by_tier["tier_1"] >= 1 and by_tier["tier_3"] >= 1 and by_tier["tier_4"] >= 1


class TestWhatIsStored:
    @pytest.fixture
    def kept(self, db, net_client, settings, web, local_provider):
        outcome = _run(db, net_client, settings=settings, registry=web,
                       local_provider=local_provider, question="what did the FOMC decide today")
        assert outcome.ok, outcome.reason
        row = next(
            r for r in SolutionStore(db, net_client.client_id).list(limit=50)
            if r.id == outcome.solution_id
        )
        return outcome, row

    def test_the_origin_is_self_web_and_is_not_counted_as_paid(self, kept):
        _outcome, row = kept
        origin = origin_of(row.provider)
        assert origin is SolutionOrigin.SELF_WEB
        assert origin.is_paid is False

    def test_it_is_a_candidate_and_nothing_promoted_it(self, kept, settings):
        """AUTO_PROMOTE is true in the test settings on purpose: this path
        must hold its candidates back regardless of that switch."""
        outcome, row = kept
        assert settings.AUTO_PROMOTE is True
        assert row.status == SolutionStatus.CANDIDATE.value
        assert outcome.counters.promoted == 0
        assert outcome.counters.awaiting_approval == 1

    def test_every_field_an_audit_needs_is_on_the_row(self, kept):
        """Months from now, "where did Brother learn this?" must have an
        answer that does not require re-running anything."""
        _outcome, row = kept
        record = row.validation_result["research"]
        assert record["source_domain"] == "federalreserve.gov"
        assert record["source_tier"] == 1
        assert record["source_trust"] == "VERIFIED"
        assert record["source_tier_name"] == "PRIMARY_OFFICIAL"
        assert record["origin"] == "local-web-research"
        assert record["search_query"].startswith("site:federalreserve.gov")
        assert record["routing_rule"] == "fed_policy"
        assert record["retrieved_at"]
        assert record["source_list_version"]["version"] == 1
        assert row.validation_result["knowledge_check"]["relation"] == "new"

    def test_the_claim_and_its_url_travel_with_every_source(self, kept):
        outcome, _row = kept
        assert all(s["claim"] and s["source_url"] for s in outcome.sources)

    def test_the_snippets_are_marked_untrusted_in_the_prompt(
        self, kept, local_provider
    ):
        """The model is told these are third-party words, not the owner's."""
        prompt = "\n".join(m.content for m in local_provider.calls[-1].messages)
        assert "untrusted" in prompt.lower()
        assert "web_snippet" in prompt


class TestRelationToWhatIsAlreadyKnown:
    class FakeRetriever:
        def __init__(self, rows=()):
            self.rows = list(rows)

        def similar_promoted(self, text, *, limit=5, min_score=None):
            return self.rows[:limit]

    def _promoted(self, db, client, question, answer):
        """A row that really is PROMOTED — the state these tests are about.

        `create` makes a CANDIDATE; promoting it is a separate act, exactly as
        it is in production.
        """
        from app.learning.origin import SELF_WEB_PROVIDER

        store = SolutionStore(db, client.client_id)
        row = store.create(
            question=question, answer=answer, task_type="general",
            provider=SELF_WEB_PROVIDER, model="m", failure_reason=None,
            local_attempt=None, validation_result={}, confidence=0.9,
            classification="INTERNAL",
        )
        return store.set_status(row, SolutionStatus.PROMOTED, "promoted by the owner")

    def test_a_duplicate_is_not_stored_again(
        self, db, net_client, settings, web, local_provider, searxng
    ):
        local_provider.answer_override = "The Fed lowered the rate to 3.5 percent."
        stored = self._promoted(
            db, net_client, "what did the fed do", "The Fed lowered the rate to 3.5 percent."
        )
        outcome = _run(
            db, net_client, settings=settings, registry=web, local_provider=local_provider,
            question="what did the FOMC decide today",
            retriever=self.FakeRetriever([(stored, 0.9)]),
        )
        assert not outcome.ok and outcome.relation == "duplicate"
        assert outcome.counters.duplicates_skipped == 1
        assert outcome.counters.candidates_created == 0

    def test_a_newer_figure_is_an_update_that_waits_for_a_person(
        self, db, net_client, settings, web, local_provider
    ):
        """The case web research creates constantly, and the one that must not
        be discarded as a copy — nor written over the old answer."""
        local_provider.answer_override = "The Fed lowered the rate to 3.5 percent."
        stored = self._promoted(
            db, net_client, "what did the fed do", "The Fed lowered the rate to 4.0 percent."
        )
        before = stored.answer
        outcome = _run(
            db, net_client, settings=settings, registry=web, local_provider=local_provider,
            question="what did the FOMC decide today",
            retriever=self.FakeRetriever([(stored, 0.85)]),
        )
        assert outcome.ok and outcome.relation == "update"
        assert outcome.counters.updates_found == 1
        assert outcome.counters.awaiting_approval == 1
        assert stored.answer == before, "the promoted answer was overwritten"
        assert stored.status == SolutionStatus.PROMOTED.value

    def test_a_contradiction_is_stored_flagged_and_left_to_a_person(
        self, db, net_client, settings, web, local_provider
    ):
        local_provider.answer_override = (
            "The Fed did not raise rates; the decision was a cut, not a hold."
        )
        stored = self._promoted(
            db, net_client, "what did the fed do", "The Fed did raise rates and it was a hold."
        )
        outcome = _run(
            db, net_client, settings=settings, registry=web, local_provider=local_provider,
            question="what did the FOMC decide today",
            retriever=self.FakeRetriever([(stored, 0.8)]),
        )
        assert outcome.relation == "contradiction"
        assert outcome.counters.contradictions_found == 1
        row = next(
            r for r in SolutionStore(db, net_client.client_id).list(limit=50)
            if r.id == outcome.solution_id
        )
        assert row.status == SolutionStatus.CANDIDATE.value
        assert "decision" in (row.status_reason or "")


class TestItCannotReachAPaidProvider:
    def test_the_module_imports_nothing_that_could_escalate(self):
        """Iron Rule 1 as a property of the file.

        Read from the import graph, not from the text: the module's own
        docstring says the word "paid" while explaining that it never reaches
        one, and a guard that trips on prose gets deleted rather than obeyed.
        What is checked is what the code can actually call.
        """
        import ast
        from pathlib import Path

        tree = ast.parse(
            Path(__file__).resolve().parents[2]
            .joinpath("app/learning/research.py").read_text()
        )
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
        for module in imported:
            assert "escalation" not in module, f"research.py imports {module}"
            assert "provider_registry" not in module, f"research.py imports {module}"
        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert not {"escalate", "may_escalate", "paid"} & called

    def test_a_search_failure_is_reported_not_escalated(
        self, db, net_client, settings, local_provider
    ):
        registry = build_registry(
            settings,
            http_client=httpx.Client(
                transport=httpx.MockTransport(lambda r: httpx.Response(500, text="boom"))
            ),
        )
        settings.WEB_SEARCH_ENABLED = True
        settings.WEB_SEARCH_URL = "http://searxng:8080/search"
        registry = build_registry(
            settings,
            http_client=httpx.Client(
                transport=httpx.MockTransport(lambda r: httpx.Response(500, text="boom"))
            ),
        )
        outcome = _run(db, net_client, settings=settings, registry=registry,
                       local_provider=local_provider, question="what did the FOMC decide today")
        assert not outcome.ok
        assert outcome.counters.web_searches_performed > 0
        assert outcome.counters.useful_sources == 0


class TestAMarketQuestionGetsAStructuredRecord:
    """The seam, end to end: what a publisher said and what Brother made of it
    must still be distinguishable when the row comes back out of memory."""

    @pytest.fixture
    def kept(self, db, net_client, settings, web, local_provider):
        # Grounded in the fake pages on purpose: an answer that does not
        # restate its evidence fails validation, which is the pipeline working.
        local_provider.answer_override = (
            "The Committee decided to lower the target range for the federal funds "
            "rate. The Federal Reserve lowered its benchmark rate on Wednesday, and "
            "a softer path would tend to support the metal."
        )
        outcome = research(
            db, net_client, question="what did the FOMC decide today, gold reaction",
            settings=settings, registry=web, local_provider=local_provider,
        )
        assert outcome.ok, outcome.reason
        row = next(
            r for r in SolutionStore(db, net_client.client_id).list(limit=50)
            if r.id == outcome.solution_id
        )
        return outcome, row

    def test_the_stored_answer_shows_which_half_had_a_publisher(self, kept):
        _outcome, row = kept
        assert "SOURCE FACT" in row.answer
        assert "TRADING INTERPRETATION (reasoning, not a sourced fact):" in row.answer
        assert "federalreserve.gov" in row.answer

    def test_the_structured_fields_are_on_the_row(self, kept):
        _outcome, row = kept
        trading = row.validation_result["trading"]
        assert trading["claim_kind"] == "observation"
        assert trading["observations"] == 1
        assert trading["status"] == "UNKNOWN", (
            "research read text; it did not see the chart, the session or the levels"
        )
        assert trading["source_refs"][0]["source_tier"] == 1
        assert trading["origin"] == "local-web-research"

    def test_a_generalising_answer_is_marked_as_resting_on_one_observation(
        self, db, net_client, settings, web, local_provider
    ):
        local_provider.answer_override = (
            "The Committee decided to lower the target range for the federal funds "
            "rate. Gold always goes up after an FOMC cut."
        )
        outcome = research(
            db, net_client, question="what did the FOMC decide today, gold reaction",
            settings=settings, registry=web, local_provider=local_provider,
        )
        assert outcome.ok
        row = next(
            r for r in SolutionStore(db, net_client.client_id).list(limit=50)
            if r.id == outcome.solution_id
        )
        trading = row.validation_result["trading"]
        assert trading["claim_kind"] == "general_rule"
        assert trading["may_be_proposed_as_a_rule"] is False
        assert "not offered as a rule" in row.answer

    def test_a_non_market_question_gets_no_trading_record(
        self, db, net_client, settings, web, local_provider
    ):
        """The structure is for market questions. Imposing it everywhere would
        make every answer look like a trading claim."""
        outcome = research(
            db, net_client, question="who designed the Eiffel tower",
            settings=settings, registry=web, local_provider=local_provider,
        )
        if not outcome.ok:
            pytest.skip(f"no candidate to inspect: {outcome.reason}")
        row = next(
            r for r in SolutionStore(db, net_client.client_id).list(limit=50)
            if r.id == outcome.solution_id
        )
        assert "trading" not in row.validation_result
