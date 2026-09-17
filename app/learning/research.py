"""Look something up on the web, and learn from it — in the background.

This is the one path in the system that reaches the public internet on
purpose, so it is written to be read: every step is named, every step is
counted, and the counts are what a person reads afterwards to decide whether
it worked. "It ran" is not a result.

**Why it is a job and not part of a request.** The local model on this box
generates at 5.35 tok/s and spends 86-117 s reading a prompt before it writes
anything. Adding a web search and a second grounded pass to a chat turn would
put a reader in front of a spinner for minutes. So the chat answers with what
it has, and this runs afterwards. Nothing waits on it.

**The ladder is not bypassed** (Iron Rule 1). This is the same ladder with the
evidence coming from a tool instead of from memory: level 0 gathers the
snippets, level 2 answers from them, level 3 validates, and the learning gates
decide what is kept. It never escalates and cannot reach a paid provider — a
test asserts the module holds no reference to one.

**What it may not do**, each enforced rather than intended:

* No RESTRICTED question is ever searched. The egress gate decides, before a
  query is built, and it is the same `may_leave_system` the paid path uses.
* Snippets only. A result URL is provenance; it is never fetched. Phase 1
  makes no outbound request other than the one to the configured endpoint.
* **A tier is who wrote it, not whether it is true.** The trusted-source list
  (`config/trusted_sources.yaml`, loaded by `sources.py`) decides which sites
  are asked FIRST and what provenance is recorded. It buys order and an audit
  trail, never a shortcut: a Federal Reserve page is validated, becomes a
  CANDIDATE and waits for a person exactly as anything else does. What it does
  buy is a floor — general-web evidence alone is read and reported, and does
  not become something Brother learned.
* Nothing is promoted. Every candidate it produces is CANDIDATE, held for a
  person, whatever AUTO_PROMOTE says — and AUTO_PROMOTE is false.
* Nothing already promoted is edited, superseded or overwritten. An UPDATE or
  a CONTRADICTION is stored beside the old answer and flagged, never in place
  of it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.logging import get_logger
from app.database.enums import TaskType
from app.database.models import Client
from app.learning.conflicts import KnowledgeRelation, check_against_known
from app.learning.fallback_capture import capture
from app.learning.origin import SELF_WEB_PROVIDER
from app.learning.sources import GENERAL_WEB_TIER, SourceRating, load_trusted_sources
from app.local_ai.prompts import ContextItem, build_system_prompt, build_user_prompt
from app.providers.base import CompletionRequest, Message
from app.tools.egress import may_use_network
from app.trading.knowledge import from_research, is_market_question
from app.validation import validate_answer

log = get_logger("research")

WEB_SEARCH_TOOL = "web_search"

# A researched answer is held to the ordinary validation bar and then to a
# confidence floor of its own. Web snippets are thinner evidence than the
# owner's pack, so the floor is the one the self-capture path uses, read from
# settings rather than written here.
RESEARCH_TASK_TYPE = TaskType.GENERAL


@dataclass
class ResearchCounters:
    """What actually happened, in numbers, including the zeros.

    Every one of these is a number a person asked for when they asked whether
    the feature works. A run that reports only "1 candidate created" cannot be
    told apart from a run that searched nothing and made it up.
    """

    web_searches_performed: int = 0
    sources_retrieved: int = 0
    useful_sources: int = 0
    # Where the evidence came from. `tier_4` being the only non-zero entry is
    # the case that must not quietly become a learned fact.
    sources_by_tier: dict[str, int] = field(default_factory=dict)
    best_source_tier: int = GENERAL_WEB_TIER
    rejected_untrusted_tier: int = 0
    candidates_created: int = 0
    rejected_by_validation: int = 0
    duplicates_skipped: int = 0
    updates_found: int = 0
    contradictions_found: int = 0
    awaiting_approval: int = 0
    promoted: int = 0
    indexed_for_retrieval: int = 0
    retrieval_confirmed: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ResearchOutcome:
    question: str
    ok: bool
    reason: str
    counters: ResearchCounters = field(default_factory=ResearchCounters)
    routing_rule: str | None = None
    queries: list[str] = field(default_factory=list)
    relation: str | None = None
    solution_id: str | None = None
    answer: str = ""
    confidence: float = 0.0
    sources: list[dict] = field(default_factory=list)
    finished_at: str = ""

    def as_dict(self) -> dict:
        return {
            "question": self.question,
            "ok": self.ok,
            "reason": self.reason,
            "routing_rule": self.routing_rule,
            "queries": self.queries,
            "relation": self.relation,
            "solution_id": self.solution_id,
            "answer": self.answer,
            "confidence": round(self.confidence, 4),
            # URLs and titles only: provenance a person can open by hand. The
            # system never opens one.
            "sources": self.sources,
            "counters": self.counters.as_dict(),
            "finished_at": self.finished_at,
        }


@dataclass
class Evidence:
    """One snippet, with where it came from and how far that is trusted."""

    rating: SourceRating
    title: str
    snippet: str
    published: str = ""
    engine: str = ""
    query: str = ""
    fetched_at: str = ""

    def as_context(self) -> ContextItem:
        """`source="web_snippet"` is deliberate: the prompt renders it, so the
        model is told these are third-party words rather than the owner's own
        knowledge — and so is anyone reading the stored context afterwards."""
        body = f"{self.title}: {self.snippet}" if self.title else self.snippet
        note = " · ".join(
            part for part in (self.rating.domain, self.published or self.engine) if part
        )
        return ContextItem(source="web_snippet", ref=self.rating.url, content=body, note=note)

    def as_dict(self) -> dict:
        return {
            **self.rating.as_dict(),
            "title": self.title[:300],
            "published": self.published,
            "engine": self.engine,
            "search_query": self.query,
            "retrieved_at": self.fetched_at,
            "claim": self.snippet[:500],
        }


def _gather(
    spec,
    *,
    question: str,
    sources,
    settings: Settings,
    counters: ResearchCounters,
) -> tuple[list[Evidence], list[str], str | None]:
    """Search the preferred sites first, then the open web.

    The order is the point. Asking `site:bls.gov CPI` before asking the open
    web puts the agency's own words in the prompt instead of whatever an
    engine ranked first — which is the difference between Brother reading a
    release and Brother reading someone's summary of it.

    The open-web pass runs even when routing found preferred sites, because a
    site-scoped query can legitimately come back empty (not every engine
    honours `site:`, and not every question has a page on the agency's site)
    and an empty routed search must not end the run.
    """
    plan = sources.route(question)
    queries: list[str] = []
    for domain in plan.prefer[: max(0, settings.RESEARCH_MAX_SEARCHES - 1)]:
        queries.append(f"site:{domain} {question}")
    queries.append(question)
    queries = queries[: settings.RESEARCH_MAX_SEARCHES]

    seen: set[str] = set()
    evidence: list[Evidence] = []
    by_tier: dict[str, int] = {}
    for query in queries:
        counters.web_searches_performed += 1
        found = spec.handler(query=query, limit=settings.RESEARCH_RESULTS_PER_SEARCH)
        if not found.ok:
            log.warning("research_search_failed", error=found.error)
            continue
        for result in found.value or []:
            url = result.get("url") or ""
            key = url.rstrip("/").lower()
            if not key or key in seen:
                continue
            seen.add(key)
            counters.sources_retrieved += 1
            snippet = (result.get("snippet") or "").strip()
            if not snippet:
                continue  # a title and a link are not evidence
            rating = sources.rate(url)
            by_tier[f"tier_{rating.tier}"] = by_tier.get(f"tier_{rating.tier}", 0) + 1
            evidence.append(
                Evidence(
                    rating=rating,
                    title=(result.get("title") or "").strip(),
                    snippet=snippet,
                    published=result.get("published") or "",
                    engine=result.get("engine") or "",
                    query=query,
                    fetched_at=result.get("fetched_at") or "",
                )
            )

    # Best tier first. LOCAL_CONTEXT_CHARS truncates the prompt, and what gets
    # truncated should be the general web, never the agency that published the
    # number. Ties keep the order they were found in.
    evidence.sort(key=lambda e: e.rating.tier)
    counters.useful_sources = len(evidence)
    counters.sources_by_tier = by_tier
    counters.best_source_tier = evidence[0].rating.tier if evidence else GENERAL_WEB_TIER
    return evidence, queries, plan.rule


def research(
    session: Session,
    client: Client,
    *,
    question: str,
    settings: Settings,
    registry,
    local_provider,
    retriever=None,
    classification: str = "INTERNAL",
    request_id: str | None = None,
) -> ResearchOutcome:
    """Search, read the snippets, answer from them, and offer the result.

    Returns an outcome with counters in every case, including refusal. A
    refusal that reports no numbers is indistinguishable from a crash.
    """
    counters = ResearchCounters()

    def done(ok: bool, reason: str, **kwargs) -> ResearchOutcome:
        return ResearchOutcome(
            question=question,
            ok=ok,
            reason=reason,
            counters=counters,
            finished_at=datetime.now(UTC).isoformat(),
            **kwargs,
        )

    question = (question or "").strip()
    if len(question) < 3:
        return done(False, "nothing to research: the question is empty")

    # --- the gate, before a query exists -------------------------------------
    egress = may_use_network(
        classification=classification,
        settings=settings,
        client_allowed_tools=client.allowed_tools,
        client_max_classification=client.max_external_classification,
        registry=registry,
    )
    if not egress.allowed:
        return done(False, egress.reason)

    spec = registry.get(WEB_SEARCH_TOOL)
    if spec is None or not spec.enabled:
        return done(False, "web search is not enabled in this deployment")

    # --- level 0: the evidence, best sources asked first ---------------------
    trusted = load_trusted_sources(settings.TRUSTED_SOURCES_FILE)
    evidence, queries, rule = _gather(
        spec, question=question, sources=trusted, settings=settings, counters=counters
    )
    sources = [e.as_dict() for e in evidence]
    if not evidence:
        # A first-class outcome, not a fault: the web had nothing to say, and
        # saying so is the honest answer (the Freshness Law's UNKNOWN).
        return done(
            False, "the search returned no usable snippets",
            routing_rule=rule, queries=queries,
        )
    items = [e.as_context() for e in evidence]

    # --- level 2: answer from the snippets, and only from them ---------------
    if local_provider is None or not getattr(local_provider, "enabled", False):
        return done(False, "no local model is available to read the results",
                    sources=sources, routing_rule=rule, queries=queries)

    model = None
    resolver = getattr(local_provider, "resolve_model", None)
    if resolver is not None:
        model = resolver(RESEARCH_TASK_TYPE, None)
        if model is None:
            return done(False, "no local model is installed",
                        sources=sources, routing_rule=rule, queries=queries)

    try:
        completion = local_provider.complete(
            CompletionRequest(
                messages=[
                    Message(
                        role="system",
                        content=build_system_prompt(RESEARCH_TASK_TYPE, "text", "strict"),
                    ),
                    Message(
                        role="user",
                        content=build_user_prompt(
                            question, items, max_chars=settings.LOCAL_CONTEXT_CHARS
                        ),
                    ),
                ],
                model=model,
                max_tokens=settings.LOCAL_MAX_TOKENS,
                temperature=0.2,
                timeout=settings.LOCAL_TIMEOUT_SECONDS,
            )
        )
    except Exception as exc:
        return done(False, f"the local model could not read the results: {type(exc).__name__}",
                    sources=sources, routing_rule=rule, queries=queries)

    answer = (completion.text or "").strip()
    if not answer:
        return done(False, "the local model produced nothing from the results",
                    sources=sources, routing_rule=rule, queries=queries)

    # --- level 3: validation --------------------------------------------------
    context_texts = [item.content for item in items]
    report = validate_answer(
        answer,
        question=question,
        task_type=RESEARCH_TASK_TYPE,
        context_texts=context_texts,
        finish_reason=getattr(completion, "finish_reason", None),
        retrieval_score=0.5,
    )
    if not report.passed or report.confidence < settings.SELF_LEARNING_MIN_CONFIDENCE:
        counters.rejected_by_validation += 1
        return done(
            False,
            f"the answer did not clear the bar (confidence {report.confidence:.2f})",
            answer=answer,
            confidence=report.confidence,
            sources=sources,
            routing_rule=rule,
            queries=queries,
        )

    # --- the trust floor ------------------------------------------------------
    # The answer stands; what it rests on decides whether it is learned from.
    # General-web evidence alone is read and reported and goes no further, so
    # a forum post cannot become something Brother knows. The bar lives in the
    # source file, so loosening it is a recorded decision rather than an edit
    # someone makes here in passing.
    if not trusted.may_learn_from(counters.best_source_tier):
        counters.rejected_untrusted_tier += 1
        return done(
            False,
            "read, not learned: the best source was "
            f"{trusted.tier_name(counters.best_source_tier)} (tier "
            f"{counters.best_source_tier}), below the tier "
            f"{trusted.min_tier_for_learning} bar for learning",
            answer=answer,
            confidence=report.confidence,
            sources=sources,
            routing_rule=rule,
            queries=queries,
        )

    # --- the learning gates ---------------------------------------------------
    known = check_against_known(retriever, question=question, answer=answer)
    if known.relation is KnowledgeRelation.DUPLICATE:
        counters.duplicates_skipped += 1
        return done(
            False, f"not kept: {known.summary()}",
            relation=known.relation.value, answer=answer,
            confidence=report.confidence, sources=sources,
            routing_rule=rule, queries=queries,
        )
    if known.relation is KnowledgeRelation.UPDATE:
        counters.updates_found += 1
    if known.relation is KnowledgeRelation.CONTRADICTION:
        counters.contradictions_found += 1

    decision = capture(
        session,
        client.client_id,
        question=question,
        answer=answer,
        task_type=RESEARCH_TASK_TYPE.value,
        provider=SELF_WEB_PROVIDER,
        model=completion.model or model or "local",
        failure_reason=None,
        local_attempt=None,
        validation=report.as_dict(),
        confidence=report.confidence,
        classification=classification,
        context={"texts": context_texts[:3], "sources": sources},
        request_id=request_id,
    )
    if not decision.captured or decision.solution is None:
        return done(
            False, f"not kept: {decision.reason}", relation=known.relation.value,
            answer=answer, confidence=report.confidence, sources=sources,
            routing_rule=rule, queries=queries,
        )

    counters.candidates_created += 1
    # CANDIDATE, always. Promotion is a person's decision, and this path does
    # not ask for an exception: `promoted` stays 0 here by construction.
    counters.awaiting_approval += 1
    best = evidence[0]
    # A market question gets a structured record, with the seam between what a
    # publisher said and what the local model made of it kept visible. The
    # split is made structurally — published text is the evidence, the model's
    # own words are the interpretation — because that line is knowable without
    # asking anyone to judge which half is which.
    trading = (
        from_research(
            question=question, answer=answer, sources=sources,
            confidence=report.confidence, origin=SELF_WEB_PROVIDER,
        )
        if is_market_question(question)
        else None
    )
    if trading is not None:
        # The stored answer is the rendered pair, not the bare paragraph. What
        # comes back out of memory months from now must still show which half
        # had a publisher — the citation must not be inherited by the reading.
        decision.solution.answer = trading.render()
    # Everything an audit needs to answer "where did Brother learn this?"
    # without re-running anything: the source, its tier and trust, the query
    # that found it, when it was read, what was extracted, how it validated,
    # and how it stands to what was already known.
    decision.solution.validation_result = {
        **(decision.solution.validation_result or {}),
        "knowledge_check": known.as_dict(),
        **({"trading": trading.as_dict()} if trading is not None else {}),
        "research": {
            "origin": SELF_WEB_PROVIDER,
            **best.rating.as_dict(),
            "source_tier_name": trusted.tier_name(best.rating.tier),
            "search_query": best.query,
            "retrieved_at": best.fetched_at,
            "routing_rule": rule,
            "queries": queries,
            "sources": sources,
            "source_list_version": trusted.as_dict(),
            "counters": counters.as_dict(),
        },
    }
    if known.requires_human:
        decision.solution.status_reason = f"{known.summary()} — needs a decision"[:300]

    log.info(
        "research_complete",
        client_id=client.client_id,
        relation=known.relation.value,
        solution_id=decision.solution.id,
        source_domain=best.rating.domain,
        source_tier=best.rating.tier,
        routing_rule=rule,
        **counters.as_dict(),
    )
    return done(
        True,
        f"kept for your approval, from {best.rating.domain} "
        f"(tier {best.rating.tier}, {best.rating.trust}): {known.summary()}",
        relation=known.relation.value,
        solution_id=decision.solution.id,
        answer=answer,
        confidence=report.confidence,
        sources=sources,
        routing_rule=rule,
        queries=queries,
    )
