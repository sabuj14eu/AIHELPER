"""The trusted-source list, and what a tier does and does not buy.

Brother is being built as a trading research learner, so not every page the
web returns is worth the same. The tiers say who wrote a thing — the agency
that published the number, an exchange, a professional newsroom, or the
general web — and they buy exactly two things: which sites are asked FIRST,
and a provenance record that survives long enough to answer "where did
Brother learn this?" months later.

They do not buy a shortcut. The first test in this file is the one that
matters, and it is about what a tier is NOT.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.learning.sources import (
    GENERAL_WEB_TIER,
    TrustedSources,
    load_trusted_sources,
)

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "trusted_sources.yaml"


@pytest.fixture
def sources() -> TrustedSources:
    return TrustedSources.load(CONFIG)


class TestATierIsNotAShortcut:
    def test_the_shipped_list_never_promotes_anything_by_itself(self):
        """A tier 1 domain is not a licence to skip the gates.

        Read as a property of the parsed data rather than of the text, because
        the file's own comments say the word "AUTO_PROMOTE" while explaining
        that nothing here reaches past it. What matters is that no KEY grants
        anything; if a future edit adds one, this fails before it ships.
        """
        import yaml

        data = yaml.safe_load(CONFIG.read_text())
        forbidden = {"auto_promote", "promote", "skip_validation", "trusted_absolutely"}
        assert not (set(data) & forbidden)
        for domain, body in data["domains"].items():
            extra = set(body) - {"tier", "name"}
            assert not extra, (
                f"'{domain}' carries {extra}: a listed domain says who wrote "
                "something and nothing else — not that it may bypass validation "
                "or human approval"
            )

    def test_the_module_names_no_domain(self):
        """The requirement in one assertion: add or remove a source by editing
        data, never by rewriting the research agent."""
        code = (ROOT / "app" / "learning" / "sources.py").read_text()
        # Full domains, not fragments: "cme" is a substring of "staticmethod",
        # and a guard that cries wolf gets deleted rather than obeyed.
        for domain in (
            "federalreserve.gov", "bls.gov", "bea.gov", "reuters.com",
            "cmegroup.com", "bloomberg.com",
        ):
            assert domain not in code, (
                f"`{domain}` is hard-coded in sources.py; the list is data and "
                "belongs in config/trusted_sources.yaml"
            )


class TestRatingASource:
    @pytest.mark.parametrize(
        "url,domain,tier",
        [
            ("https://www.federalreserve.gov/newsevents/pressreleases/x.htm",
             "federalreserve.gov", 1),
            ("https://www.bls.gov/news.release/cpi.nr0.htm", "bls.gov", 1),
            ("https://fred.stlouisfed.org/series/DGS10", "fred.stlouisfed.org", 2),
            ("https://www.cmegroup.com/markets/gold.html", "cmegroup.com", 2),
            ("https://www.reuters.com/markets/commodities/x", "reuters.com", 3),
            ("https://some-guy.blogspot.com/gold-to-the-moon", "some-guy.blogspot.com", 4),
        ],
    )
    def test_urls_land_in_the_tier_they_should(self, sources, url, domain, tier):
        rating = sources.rate(url)
        assert (rating.domain, rating.tier) == (domain, tier)

    def test_a_subdomain_inherits_its_parent(self, sources):
        """So that every regional or service subdomain does not have to be
        listed one by one — and go unlisted the day a new one appears."""
        assert sources.rate("https://apps.bea.gov/iTable/x").tier == 1

    def test_a_lookalike_domain_does_not_inherit_anything(self, sources):
        """`notbls.gov` and `bls.gov.evil.com` are the whole reason the match
        is on a dotted suffix rather than a substring."""
        assert sources.rate("https://notbls.gov/fake").tier == GENERAL_WEB_TIER
        assert sources.rate("https://bls.gov.evil.example/fake").tier == GENERAL_WEB_TIER

    def test_anything_unlisted_is_general_web_and_unverified(self, sources):
        rating = sources.rate("https://randomsite.example/page")
        assert rating.tier == GENERAL_WEB_TIER
        assert rating.trust == "UNVERIFIED"

    def test_a_rating_carries_every_field_an_audit_needs(self, sources):
        data = sources.rate("https://www.bls.gov/news.release/cpi.nr0.htm").as_dict()
        assert data["source_domain"] == "bls.gov"
        assert data["source_tier"] == 1
        assert data["source_trust"] == "VERIFIED"
        assert data["source_name"]
        assert data["source_url"].startswith("https://")

    def test_a_malformed_url_does_not_raise(self, sources):
        assert sources.rate("not a url at all").tier == GENERAL_WEB_TIER
        assert sources.rate("").tier == GENERAL_WEB_TIER


class TestTheLearningFloor:
    def test_general_web_alone_is_read_but_not_learned_from(self, sources):
        assert sources.may_learn_from(1)
        assert sources.may_learn_from(3)
        assert not sources.may_learn_from(GENERAL_WEB_TIER)

    def test_the_bar_is_data_so_it_can_be_moved_without_a_code_change(self):
        loose = TrustedSources({"min_tier_for_learning": 4, "tiers": {}, "domains": {}})
        assert loose.may_learn_from(4)
        strict = TrustedSources({"min_tier_for_learning": 1, "tiers": {}, "domains": {}})
        assert not strict.may_learn_from(3)


class TestRouting:
    @pytest.mark.parametrize(
        "question,first",
        [
            ("what did the FOMC decide today", "federalreserve.gov"),
            ("US CPI print this morning", "bls.gov"),
            ("nonfarm payrolls number", "bls.gov"),
            ("Q2 GDP revision", "bea.gov"),
            ("crude oil inventories this week", "eia.gov"),
            ("gold COT positioning", "cftc.gov"),
            ("where is gold trading", "lbma.org.uk"),
            ("what did the ECB say about rates", "ecb.europa.eu"),
        ],
    )
    def test_a_question_reaches_the_body_that_publishes_the_number(
        self, sources, question, first
    ):
        plan = sources.route(question)
        assert plan.is_routed
        assert plan.prefer[0] == first, f"{question!r} routed to {plan.prefer}"

    def test_the_specific_rule_wins_over_the_general_one(self, sources):
        """"PCE inflation" is a BEA release, not a BLS one. Rules are tried in
        file order, so the order in the file is load-bearing."""
        assert sources.route("PCE inflation for August").prefer[0] == "bea.gov"

    def test_an_unrouted_question_is_a_normal_outcome_not_a_failure(self, sources):
        plan = sources.route("what is the capital of France")
        assert not plan.is_routed and plan.rule is None

    def test_every_preferred_domain_in_the_file_is_a_rated_domain(self, sources):
        """A typo in a `prefer` list would route a question to a site the
        ratings do not know, and the evidence would come back tier 4 —
        silently turning a routed question into an unroutable one."""
        for name, _patterns, prefer in sources._routing:
            for domain in prefer:
                assert sources.rate(f"https://{domain}/x").tier < GENERAL_WEB_TIER, (
                    f"routing rule '{name}' prefers '{domain}', which is not in `domains`"
                )


class TestLoading:
    def test_a_missing_file_yields_an_empty_list_that_learns_from_nothing(self, tmp_path):
        """Fails in the safe direction — everything becomes tier 4, so nothing
        is learned — and says so in the log, because a silently empty list
        looks exactly like a quiet week on the web."""
        sources = TrustedSources.load(tmp_path / "nope.yaml")
        assert sources.rate("https://www.bls.gov/x").tier == GENERAL_WEB_TIER
        assert not sources.may_learn_from(GENERAL_WEB_TIER)

    def test_unreadable_yaml_does_not_raise(self, tmp_path):
        broken = tmp_path / "broken.yaml"
        broken.write_text("domains: [this is: not: valid: yaml")
        assert TrustedSources.load(broken).rate("https://x.example").tier == GENERAL_WEB_TIER

    def test_the_shipped_file_loads_and_says_what_is_in_force(self):
        summary = load_trusted_sources(str(CONFIG)).as_dict()
        assert summary["domains"] > 20
        assert summary["min_tier_for_learning"] == 3
        assert summary["updated"], "the list records when it was last verified"
