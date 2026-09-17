"""Which sources are trusted, and which are asked first — read from data.

Everything specific lives in `config/trusted_sources.yaml`: the domains, the
tiers, the routing rules, the bar below which evidence is not learned from.
Nothing in this module names a domain, and nothing outside it reads the file.
Adding a source later is an edit to a YAML file and a test, never a change to
the research agent. (The same rule the accounting engine learned the hard way:
rates are data, never code.)

**A tier says who wrote it, not whether it is true.** Tier 1 is the body that
produced the number; it is still validated, still becomes a CANDIDATE, and
still waits for a person. What the tier actually buys is two things:

* **order** — a question about a scheduled release asks the body that
  publishes it before it asks the open web, so the best available evidence is
  in the prompt rather than whatever a search engine ranked first, and
* **provenance** — the tier is recorded on every candidate, so that "where did
  Brother learn this?" has an answer months later instead of a guess.

Deterministic throughout (Iron Rule 2): a dictionary lookup and a list of
regular expressions. Routing a question to a source is a control decision and
no model takes part in it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from app.core.logging import get_logger

log = get_logger("sources")

GENERAL_WEB_TIER = 4
UNKNOWN_TRUST = "UNVERIFIED"


@dataclass(frozen=True)
class SourceRating:
    """What is known about where a snippet came from."""

    url: str
    domain: str
    tier: int
    trust: str
    name: str = ""

    def as_dict(self) -> dict:
        return {
            "source_url": self.url,
            "source_domain": self.domain,
            "source_tier": self.tier,
            "source_trust": self.trust,
            "source_name": self.name,
        }


@dataclass(frozen=True)
class RoutingPlan:
    """Which sites to ask first for this question, and under which rule."""

    rule: str | None
    prefer: tuple[str, ...]

    @property
    def is_routed(self) -> bool:
        return bool(self.prefer)


class TrustedSources:
    """The loaded source list. Built once and shared; the file is small."""

    def __init__(self, data: dict, *, path: Path | None = None):
        self.path = path
        self.version = data.get("version")
        self.updated = str(data.get("updated") or "")
        self.min_tier_for_learning = int(data.get("min_tier_for_learning", 3))

        self._tiers: dict[int, dict] = {
            int(number): dict(body or {}) for number, body in (data.get("tiers") or {}).items()
        }
        self._domains: dict[str, dict] = {
            str(domain).lower().strip(): dict(body or {})
            for domain, body in (data.get("domains") or {}).items()
        }
        self._routing: list[tuple[str, list[re.Pattern], tuple[str, ...]]] = []
        for rule in data.get("routing") or []:
            patterns = [re.compile(p, re.I) for p in rule.get("match") or []]
            prefer = tuple(str(d).lower() for d in rule.get("prefer") or [])
            if patterns and prefer:
                self._routing.append((str(rule.get("name") or "unnamed"), patterns, prefer))

    # --------------------------------------------------------------- loading
    @classmethod
    def load(cls, path: str | Path) -> TrustedSources:
        """Read the file. A missing or broken file is not silently empty.

        This is a safety-adjacent gate: with no list, every source is tier 4
        and nothing is learned, which is the safe direction — but it must be
        loud, because a silently empty list looks exactly like "the web had
        nothing useful today" for as long as nobody checks.
        """
        import yaml

        file = Path(path)
        try:
            data = yaml.safe_load(file.read_text()) or {}
        except FileNotFoundError:
            log.error("trusted_sources_missing", path=str(file))
            data = {}
        except Exception as exc:
            log.error("trusted_sources_unreadable", path=str(file), error=type(exc).__name__)
            data = {}
        sources = cls(data, path=file)
        log.info(
            "trusted_sources_loaded",
            path=str(file),
            domains=len(sources._domains),
            rules=len(sources._routing),
            min_tier=sources.min_tier_for_learning,
        )
        return sources

    # ----------------------------------------------------------------- rating
    @staticmethod
    def domain_of(url: str) -> str:
        """The host, lowercased, with a leading www. removed."""
        host = (urlsplit(str(url or "")).hostname or "").lower()
        return host[4:] if host.startswith("www.") else host

    def _entry_for(self, domain: str) -> tuple[str, dict] | None:
        """The listed domain this host belongs to, if any.

        Matched by suffix, so a service or regional subdomain resolves to its
        parent without every one being listed — and going unlisted the day a
        new one appears. The dot is required: a listed `example.gov` must not
        swallow `notexample.gov`, nor `example.gov.evil.test`.
        """
        if not domain:
            return None
        if domain in self._domains:
            return domain, self._domains[domain]
        best: tuple[str, dict] | None = None
        for listed, body in self._domains.items():
            if domain.endswith("." + listed) and (best is None or len(listed) > len(best[0])):
                best = (listed, body)
        return best

    def rate(self, url: str) -> SourceRating:
        """Where this URL sits. Anything unlisted is tier 4, UNVERIFIED."""
        domain = self.domain_of(url)
        entry = self._entry_for(domain)
        if entry is None:
            return SourceRating(
                url=url, domain=domain, tier=GENERAL_WEB_TIER, trust=self.trust_of(GENERAL_WEB_TIER)
            )
        listed, body = entry
        tier = int(body.get("tier", GENERAL_WEB_TIER))
        return SourceRating(
            url=url,
            domain=listed,
            tier=tier,
            trust=self.trust_of(tier),
            name=str(body.get("name") or ""),
        )

    def trust_of(self, tier: int) -> str:
        return str(self._tiers.get(int(tier), {}).get("trust") or UNKNOWN_TRUST)

    def tier_name(self, tier: int) -> str:
        return str(self._tiers.get(int(tier), {}).get("name") or "GENERAL_WEB")

    def may_learn_from(self, tier: int) -> bool:
        """Is a source at this tier strong enough to learn from on its own?

        Tier 4 is read and reported; it does not become a candidate by itself.
        The bar is data (`min_tier_for_learning`) rather than a constant here,
        so loosening it is a recorded decision in a file, not a code change
        someone can make in passing.
        """
        return int(tier) <= self.min_tier_for_learning

    # ---------------------------------------------------------------- routing
    def route(self, question: str) -> RoutingPlan:
        """Which sites to ask first. First matching rule wins.

        No match is a normal outcome, not a failure: most questions are not
        about a scheduled release, and the open web is the right place for them.
        """
        text = question or ""
        for name, patterns, prefer in self._routing:
            if any(pattern.search(text) for pattern in patterns):
                return RoutingPlan(rule=name, prefer=prefer)
        return RoutingPlan(rule=None, prefer=())

    def as_dict(self) -> dict:
        """For /admin and for a run's record: what list was in force."""
        return {
            "version": self.version,
            "updated": self.updated,
            "domains": len(self._domains),
            "rules": [name for name, _, _ in self._routing],
            "min_tier_for_learning": self.min_tier_for_learning,
        }


@lru_cache(maxsize=4)
def load_trusted_sources(path: str) -> TrustedSources:
    """Cached by path. Restart (or clear the cache) after editing the file."""
    return TrustedSources.load(path)
