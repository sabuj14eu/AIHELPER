# Changelog

Every schema change gets an Alembic revision and an entry here, with its
migration note. Deploys follow: **backup → migrate → restart → verify logs.**

## 1.4.0 — 2026-09-16

Phase 3: something finally sends a message to a specialist.

**Migration:** none. The chat's agent selector now opens on `auto`.

### Added

- **A deterministic agent router** (`app/agents/router.py`). Four Brother
  agents existed, each with its own prompt and tool set, and nothing routed to
  any of them — the agent was whichever value the dropdown held. A trading
  question reached the trading expert only if the reader remembered to pick it,
  which is the same as saying the specialisation was decorative.

  It is regex over the message, not a model call. Iron Rule 2 stands, and a
  test asserts the module cannot reach a provider. Scoring counts *distinct*
  signals, so a message has to lean into a domain — one incidental "plan" does
  not move a question to trading. A tie goes to the generalist. Being wrong
  costs one local call against a slightly-wrong prompt, and that stays true
  only because the fallback is `brother`, which inherits the client's whole
  tool set — never "no agent", never a refusal.

  Every decision records the words that caused it and travels on the response
  as `agent_routing`, so accuracy is a measurement. The 24-message labelled set
  in `tests/unit/test_agent_router.py::LABELLED` is the thing to grow when it
  gets something wrong; it found six real misses on its first run.

- **`auto` in the chat selector**, and it is the default. Any named agent still
  overrides it and is never second-guessed: someone who picked the social agent
  for a question about gold meant it. `PERSONAL_AGENT` becomes the router's
  fallback rather than a fixed choice.

### Fixed

- **An agent's `default_task_type` disabled per-message classification.** It
  was passed to the classifier as `declared`, which short-circuits at
  confidence 1.0 — and all four Brother agents declare GENERAL, so every
  message in the chat classified as GENERAL and the 90 lines of patterns below
  never ran. The message speaks first now; the agent's default catches it only
  when nothing specific matched (`AGENT_DEFAULT_FLOOR`).

  The floor is deliberately at 0.8, which excludes the classifier's two guesses
  that are about the *client* rather than the question — "documents exist and
  this is open-ended" (0.5) and "nothing matched" (0.4). For a client holding a
  77-document knowledge pack the first fires on almost every sentence and would
  route ordinary conversation into strict document QA.

## 1.3.1 — 2026-09-16

Phase 2: the system prompt stops contradicting itself.

**Migration:** none.

### Fixed

- **One system message carried two incompatible orders.** `BASE_SYSTEM` told
  the model, unconditionally and first, to answer `INSUFFICIENT_CONTEXT`
  whenever the CONTEXT fell short. `BROTHER_LAWS`, appended several hundred
  words later, said a plan question is "a procedure, never a refusal". A small
  model follows the blunt rule that came first, which is the direct cause of
  the refusal observed under llama3.2:3b.

  The rule is now a choice an agent makes. `STRICT_CONTEXT_RULE` is unchanged
  and stays the default — a document-QA agent must not fill gaps from general
  knowledge. `PARTIAL_CONTEXT_RULE` says to name the missing input in one line
  and answer the rest, and keeps the marker as a last resort for when nothing
  useful can be said at all. The four Brother agents declare
  `context_policy="partial"`; everything else is untouched.
  Test: `TestBrotherAgents::test_the_brother_agents_do_not_carry_the_unconditional_refusal_order`.

### Changed

- **The plan procedure moved into the prompts of the agents that answer plan
  questions** (`brother`, `trading`). It lived only in a pack document, which
  made "does Brother know how to build a plan" a question about cosine
  similarity on the day. Iron Rule 5 draws its line at facts, not at method:
  the order Brother thinks in is the way of working. The procedure contains no
  level, threshold or sample size — every figure still comes from CONTEXT, and
  a test now enforces that across every Brother prompt, not just the shared
  laws.

## 1.3.0 — 2026-09-16

Phase 1 of the Brother architecture work (see the audit): a turn is now one of
four things, and only one of them is a fault.

**Migration:** none. `state` is response-only and is not persisted.

### Added

- **Four answer states** (`app/validation/states.py`): VERIFIED · USEFUL ·
  INSUFFICIENT · FAILED, on every `GatewayResponse` as `state`. Validation's
  boolean is unchanged and still decides escalation and promotion; `success`
  keeps its old meaning. What changes is that the three ways of *not* passing
  stop looking identical to the reader.
  - **INSUFFICIENT is a successful outcome.** "The evidence for this is not
    available" is what the constitution asks for on every question about the
    owner's systems. It reaches the reader as an answer, not as a failure.
  - **FAILED means no answer can be shown** — either nothing came back, or a
    veto says what came back must not be served.

### Fixed

- **"I don't have enough information" was scored as a refusal.** It is a report
  about the evidence, not a refusal to work — and the Brother laws *require* it
  ("say UNKNOWN and name what is missing"). The validator was punishing the
  assistant for following its own rules. `REFUSAL_PATTERNS` now covers only a
  model declining to work; `LACKS_EVIDENCE_PATTERNS` is its own finding and its
  own veto. Both still block a PASS — nothing here lowers a bar.
  Tests: `tests/unit/test_validation.py::TestOutputChecks::test_lacking_evidence_is_not_a_refusal`.
- **An empty bubble no longer stands in for a reason.** A FAILED turn renders a
  sentence built from its cause. The chat leads with the answer and a one-word
  state; route, model, confidence, sources and notes moved behind a "why"
  disclosure. Machinery is no longer the headline.

### Changed — this one tightens the bar

- **An answer vetoed for contradicting its sources, for a safety finding, for a
  degenerate loop, for an invalid format, or for disagreeing with a
  deterministic tool is now withheld**, with the reason named. It used to be
  handed over with an "unverified" label. There is no reading of those vetoes
  under which the text is worth showing.
  Test: `TestTheFourStates::test_a_withholding_veto_produces_failed_not_a_labelled_answer`.

## 1.2.1 — 2026-09-16

**Migration:** none.

### Added

- **`load-knowledge --retry-rejected`** (AIH-3) — offers pack seeds the local
  model previously rejected to the promotion gate once more. The reproduction
  gate is a judgement by a particular model, and 48 seeds were rejected by
  `llama3.2:3b` before `qwen2.5:7b` was installed; the model underneath them
  changed, the seeds did not.

  It does **not** delete the rejected rows, as the open item first proposed.
  Iron Rule 4 says a re-taught question supersedes, never edits, so the
  rejection is EXPIRED carrying its original reason
  (`retried after rejection: …`) and the retry faces the gate as a new
  candidate that earns its own status. The audit trail keeps what the gate
  refused and why.

  It refuses unless *every* row for a question is a REJECTED row that this
  pack seeded: a PROMOTED, VALIDATED or still-CANDIDATE row means a live
  answer is in play, and a rejected paid or taught answer belongs to those
  paths. It is never automatic — a plain reload still skips, so Iron Rule 4
  cannot be violated by a routine deploy. `seed_solutions` now also reports a
  `retried` count. Tests:
  `tests/unit/test_knowledge_pack.py::TestRetryingRejectedSeeds`.

### Fixed

- **The trading mirror's field names are verified, and two of its numbers now
  say what they mean** (AIH-5). Every key `trading_status` renders was checked
  against the platform's `app/routers/api_v1.py` and
  `app/services/analytics.py` at Sniper-System `3257184`: `portfolio` →
  `analytics.portfolio_totals`, `stats` → `analytics.full_report` (which
  spreads `core_stats`), and the `trades` and `signals` dictionaries are built
  literally in the router. All of them match; nothing was renamed. Two
  rendering defects turned up while checking:
  - `win_rate` arrives as a percentage and was printed bare, so "win rate 54.1"
    sat next to "profit factor 1.21" with nothing to say they are different
    kinds of number. It now carries its `%`.
  - A key the platform sent as `null` was dropped from the line entirely, which
    reads as "the platform did not report it". `profit_factor` is `null`
    precisely when there were no losing trades to divide by, and `max_drawdown`
    and `avg_rr` are `null` on an empty history. Absence is not zero and it is
    not silence: a present-but-null statistic now reads `UNKNOWN`, and Brother
    does not guess which of the two the platform meant.

  Note this is a rendering audit against the platform's source, not a live
  read: the connector is still unconfigured on the box (AIH-1), so no real
  payload has been through it.

- **A failed request now says why it failed.** When level 2 produced nothing
  at all, `GatewayRouter._degraded` recorded the reason only `if not
  base.notes` — and by the time it is reached a note almost always exists,
  because "escalation blocked: ..." is appended on the way there. With paid
  providers off, which is the owner's standing decision, that guard was always
  false, so the reason was *always* dropped. The chat showed an empty bubble,
  `route failed · UNVERIFIED`, and nothing distinguishing a local timeout from
  an Ollama that is down. The reason is now recorded on every failed request
  and inserted first, ahead of the notes that only say what did not rescue it.
  Regression tests:
  `tests/integration/test_failures.py::TestLocalModelDown::test_the_reason_there_is_no_answer_survives_the_escalation_blocked_note`,
  `::test_an_empty_local_answer_with_no_paid_provider_says_it_was_empty`, and a
  tightened `::test_with_the_local_model_down_and_no_paid_provider_the_request_fails_honestly`
  — the old assertion was `assert response.notes`, which is what let the cause
  go missing: it checked that there were notes, not that any of them said why.

## 1.2.0 — 2026-09-16

Brother can now talk about *now*: two read-only live connectors, a tool
intent mechanism that feeds live readings to the model as evidence, and a
stronger default model class for the Brother agents.

**Migration:** none. New settings only (all documented in `.env.example`);
the trading connector is inert until `TRADING_PLATFORM_URL` and
`TRADING_PLATFORM_API_KEY` are set.

### Added

- **`market_news` tool** (`app/tools/live.py`) — reads the ForexFactory weekly
  calendar, the one news source the v7 bot and the v18 brain already read, and
  renders the platform's three-state news risk (HIGH within 60 min of a
  high-impact event, ELEVATED within 240, LOW otherwise). UNKNOWN whenever the
  feed cannot be read, the week is empty, the feed is dead, or the last good
  reading is older than `MARKET_NEWS_MAX_AGE_HOURS`; UNKNOWN is never LOW.
  Every reading carries source, fetch time and age.
- **`trading_status` tool** — reads the Sniper-System platform's API v1
  (portfolio, stats, open trades, last signals) with a user API key. Read-only
  by the platform's Iron Rule 1; a failed section reads UNKNOWN rather than
  vanishing; the key never enters output or errors; DEMO is stated; a low
  sample is labelled as such.
- **Tool intents** — a `ToolSpec` may carry an `intent` matcher. A direct
  match answers at level 0 for free ("news today?", "bot status"); a context
  match runs the tool and hands its reading to the model as fenced, untrusted
  evidence ("should we be careful with gold this session given the news?").
  New permission `tool:live_data`, in the default set; an agent's narrowed
  tool list still applies.
- **Agent model role** — `AgentSpec.model_role`; the four Brother agents
  prefer the `STRONG_LOCAL_MODEL` and fall back to the task's class when it is
  not installed. Pull `qwen2.5:7b` to use it.
- **Dashboard chat** shows whether each connector is on.

### Fixed

- **Dashboard 401 shown as JSON.** A browser opening `/admin` or `/admin/chat`
  without a session received `{"error": "administrator sign-in required"}`
  instead of the sign-in form. A GET on an `/admin` page whose `Accept`
  names HTML now redirects to `/admin/login`; API calls and the chat's own
  `fetch()` keep their JSON 401. Reported on the first real deployment
  (ai.signalmesh.dev, 2026-09-16).
- **Constitution and handoff** — `CLAUDE.md` (iron rules, layout, the laws
  learned on the first real deployment), `docs/HANDOFF_BROTHER_SESSION.md`
  (state on the box, verified vs. not, backlog, opening prompt) and
  `docs/OPEN_ITEMS.md` (AIH-1 … AIH-11 with status).
- **Teaching** (`app/learning/teaching.py`, `/admin/chat/teach`,
  `python -m app.cli teach`, a form on every chat reply). The owner supplies
  question, answer and evidence; the pair goes through the same validation
  and reproduction gates as a paid answer and is PROMOTED only when the local
  model can use it. A re-taught question supersedes the earlier row. This is
  how a deployment with paid providers off learns from its owner.
- **Plan questions are a procedure.** A new pack document
  (`knowledge/brother/brother__trading_plan_recipe.md`) and a law line: news
  reading first, then the posted outlook (ABSENT if none), then the standing
  rules for the asset, then the plan, naming each input present or absent.
  Never a refusal, never an entry instruction.
- **Pack sources extended** with the documents Brother reported missing:
  v7 `INTENT_v5.md`, `ROADMAP.md`, the autonomy plan and adaptive gates spec;
  the platform's v7 integration contract and desk handover; the brain's
  Pine-versus-bot map. The sync now treats documented placeholders such as
  `<BB_BRAIN_WEBHOOK_SECRET>` as placeholders, not secrets.
- **The dashboard chat no longer depends on the proxy timeout.** A local
  model on CPU can take minutes on a reasoning question, and nginx's
  `proxy_read_timeout` (60 s by default) answered with its own 504 page.
  `/admin/chat/ask` now queues the question as the same background job
  `/api/v1/tasks` uses and returns at once; the page polls
  `/admin/chat/task/{id}` every two seconds and shows the elapsed time.
  `/admin/chat/ask-now` keeps the synchronous form for scripts behind no proxy.
- **Local prompt evidence budget** — `LOCAL_CONTEXT_CHARS` (default 4500,
  was the paid providers' 8000). Prompt evaluation dominates CPU latency, so
  this roughly halves the time to first token on a 3B model.
- **Ollama keep-alive 60 min** — the model no longer unloads after five idle
  minutes and pays a 10–20 s reload at the start of the next answer.
- `scripts/nginx_add_timeouts.sh` now tests and reloads nginx even when the
  directives are already present, so a hand edit that was never reloaded
  becomes live.
- **"hello" was answered with INSUFFICIENT CONTEXT.** Small talk was still
  retrieving pack chunks, and the base rule told the model to refuse when the
  context did not cover the question. Greetings and thanks now skip retrieval
  (`gateway.router.is_small_talk`), the Brother laws say the refusal is only
  for facts about the owner's systems, and the validator now catches the
  marker written as "INSUFFICIENT CONTEXT" (space, dash or lower case), which
  had slipped past as a passing answer at confidence 0.65.
- **`scripts/nginx_add_timeouts.sh`** — adds `proxy_read_timeout` and
  `proxy_send_timeout` to an existing nginx site file, anchor-safe: backup,
  exactly one `proxy_pass` or it refuses, `nginx -t`, reload, restore on failure.
- **`python -m app.cli ask "…"`** — talk to Brother from the terminal as the
  personal client, through the same ladder, bypassing any reverse proxy.
  Prints the answer, then route, confidence, latency, cost and sources.
- **Chat page showed "SyntaxError: Unexpected token '<'" on a proxy error.**
  When nginx answered with its own HTML (a 504 after its 60 s default
  `proxy_read_timeout`, or a 502 during a restart) the page tried to parse
  it as JSON. It now explains the HTTP status in plain words and shows an
  elapsed-time indicator while the model works. `LOCAL_TIMEOUT_SECONDS`
  default raised from 60 to 180 to match the proxy guidance in
  `docs/deployment.md`; a CPU model reading a full context needs it.
- **Bootstrap was one transaction and seeding was unbounded.** The pack
  documents and all 278 seeds committed together at the very end, so the
  chat page said "not loaded" for the whole run and an interrupt rolled
  everything back. On a CPU box the reproduction gate is tens of seconds per
  seed, about two hours in total. Now the documents commit first, seeding
  commits one solution at a time (resumable), prints progress with a time
  estimate, and `--seed-limit N` runs a batch.
- **Knowledge pack missing from the image.** `bootstrap-brother` inside the
  container refused with "knowledge pack directory not found" because the
  Dockerfile did not copy `knowledge/`. It is copied now, next to `app/` and
  `scripts/`. Found on the first real deployment.
- A "trading plan" question is treated as reasoning (live readings become
  context for the model) rather than a bare status request.

### Verification

New tests in `tests/unit/test_live_tools.py` cover the verdict windows, the
cache and max-age behaviour, partial failures, key non-disclosure, intents,
narrowing, and the router path with a mock transport. The conftest disables
both connectors so no test reaches the network.

## 1.1.0 — 2026-09-16

Brother: the personal assistant layer. AI Helper now knows who it works for.
Requested by the owner on 2026-09-16 ("develop this AI helper as my personal
AI"), which lifts the 1.0 feature freeze for this one addition; the gateway,
routing, cost, privacy and learning code paths are unchanged.

**Migration:** none. No table or column changes. The pack's provenance lives
in the existing `documents.meta` JSON column and seeded solutions are ordinary
`solution_candidates` rows (`provider = knowledge-pack`). Deploy is still
backup → migrate (no-op) → restart → verify logs, then once:

```bash
docker compose exec ai-helper python -m app.cli bootstrap-brother
```

### Added

- **Knowledge pack** (`knowledge/`) — hand-written digests of the owner's six
  repositories (laws, architecture, evidence, workflows and tools, validated
  solutions, open items, glossary) plus verbatim copies of their governing
  documents stamped with the commit they came from. Loaded through the
  ordinary ingestion pipeline as documents of the personal client, one
  namespace per domain. `app/knowledge/pack.py`.
- **Seeded solutions** — `*validated_solutions.md` blocks become CANDIDATE
  rows and go through the same promotion gate as a paid answer. PROMOTED
  with a local model running; held at VALIDATED without one.
- **Brother agents** — `brother`, `trading`, `architect`, `social`, sharing
  one set of working laws appended to the base rules. The four generic agents
  are unchanged. `app/agents/builtin.py`.
- **Dashboard chat** — `/admin/chat` runs as the personal client through the
  same `GatewayRouter`, with the client's rate limit, and shows route,
  confidence, cost, sources and validation notes for every reply.
- **CLI** — `bootstrap-brother`, `load-knowledge [--prune]`,
  `knowledge-status`; `scripts/sync_knowledge.py` refreshes `knowledge/sources/`
  from sibling checkouts and refuses any file the privacy detector marks
  RESTRICTED.
- **Settings** — `PERSONAL_CLIENT_ID`, `PERSONAL_AGENT`, `KNOWLEDGE_PACK_DIR`.
- **Audit action** — `knowledge.pack_loaded`.

### Fixed

- **Polarity check false positive** (`app/validation/factuality.py`). The
  contradiction detector flagged an answer whenever *any* context sentence
  sharing three content words differed in polarity, so a faithful quote of a
  source that says both "X is invalid" and "X is not neutral" was rejected as
  contradicting the source. Found when 278 seeded solutions and a pack
  answer were all rejected. A conflict is now a phrase the context asserts
  only with the opposite polarity. Regression test:
  `tests/unit/test_validation.py::TestFactuality::test_a_faithful_quote_of_a_mixed_polarity_source_is_not_a_contradiction`.

### Verification

469 tests pass (435 before, 34 added), ruff clean. Loading the shipped pack
against the fake local model produced 69 documents and 276 promoted seeds;
the numbers a real deployment produces depend on its embedder and model and
are printed by `bootstrap-brother`.

## 1.0.0 — 2026-09-07

First release. The standalone AI Helper: a local-first gateway with paid-API
fallback, cost protection, and learning from the cases it had to pay for.

**Migration:** `0001_baseline` — creates the whole schema. On an empty
database this is the only step:

```bash
alembic upgrade head
```

### Added

- **Gateway** — the level 0→4 ladder: deterministic tools, retrieval, the local
  model, validation, then a paid provider only if none of those sufficed and
  the budget, classification and client permission all allow it.
- **Local AI** — Ollama client with distinct handling for offline, timeout,
  missing model, server error, non-JSON body and malformed response; per-task
  model selection with graceful degradation.
- **Providers** — a registry behind one interface; OpenAI and Anthropic over
  plain HTTP, both disabled by default and requiring a key as well as a flag.
- **Cost protection** — per-request cap, daily and monthly budgets, per-client
  budgets, a pessimistic pre-flight check, and an unknown model priced at its
  provider's worst known rate rather than zero.
- **Learning** — capture every fallback; CANDIDATE → VALIDATED → PROMOTED with
  a validation gate and a local-reproduction gate; REJECTED and EXPIRED kept.
- **Memory** — conversation window, long-term items requiring provenance,
  semantic search over Qdrant with a durable database fallback, per-client
  namespaces.
- **Knowledge** — PDF, TXT, Markdown, DOCX, CSV, JSON, JSONL ingestion, with a
  scanned PDF refused rather than silently ingested empty.
- **Tools** — a closed registry with declared schemas, permissions and risk;
  an AST-based calculator with no `eval`; no general executor of any kind.
- **Privacy** — four classifications, a detector that can only raise,
  RESTRICTED blocked in two places, and redaction applied in addition to the
  gate rather than instead of it.
- **Security** — SHA-256 API keys, scrypt passwords (no bcrypt 72-byte
  ceiling), signed session cookies, per-client rate limiting, an append-only
  audit trail, and log redaction that removes content as well as secrets.
- **API** — chat, async tasks, documents, memory, solutions, models, tools,
  agents, usage, costs, health, and an admin surface.
- **Dashboard** — overview, solutions review, clients, audit search.
- **Agents** — four generic profiles that can only narrow what a client may do.
- **Deployment** — Docker Compose with ai-helper, postgres, qdrant, ollama,
  n8n and open-webui, named volumes for everything stateful, a non-root image,
  setup/health/backup scripts, and four n8n workflows.
- **Tests** — 435, including the ten critical regression tests and the
  cost-saving cycle, all runnable with no external service.

### Fixed during the pre-release audit

Six issues found by `audit/`, each with a regression test. Full detail in
`audit/AUDIT_REPORT.md`.

- **Production could start on the published placeholder `AUTH_SECRET`**, which
  signs the admin session cookie. Production now refuses to start unless it is
  at least 32 characters and not the default, and refuses `DEBUG=true`.
- **The privacy refusal that actually fires left no audit row.** The audit
  trail could answer "what did we send out?" but not "what did we refuse to
  send, and why?". Every refused escalation is now recorded.
- **Solution reuse could fail silently and expensively** when an embedding
  model's score scale did not match the configured threshold — every
  paraphrase would re-escalate and pay, invisibly. Added
  `ai-helper calibrate`, which measures the live embedder and exits non-zero
  when the thresholds do not fit it.
- **A near-miss was indistinguishable from an absence.** Retrieval now reports
  `near_miss_score` and `reuse_threshold`.
- **Refused escalations were not aggregated anywhere**, so a budget set too low
  to admit any request looked like a local model performing perfectly.
  `/api/v1/usage` and the dashboard now report them.
- **`/api/v1/documents/formats` was public by omission**, and
  **`ALLOW_ANONYMOUS` was dead configuration that read like a switch.** Both
  fixed; a test now enumerates the whole OpenAPI surface, and another keeps
  `.env.example` in sync with Settings in both directions.

### Container image (found during the Docker gate)

The image could not build on a host without access to Debian's package
repositories. The `apt-get` layers turned out to be unnecessary and were
removed:

- every runtime dependency installs as a pre-built wheel, so the builder needs
  no compiler (`--only-binary=:all:` now makes that a hard guarantee: a
  dependency that needed compiling would fail the build loudly instead of
  silently requiring a toolchain);
- `psycopg[binary]` bundles its own libpq, so `libpq5` was redundant;
- `useradd` is already in `python:3.11-slim`;
- the healthcheck now probes `/healthz` with the interpreter that is already
  in the image, so `curl` is no longer installed purely to check the container.

Net effect: a smaller image with fewer packages to patch, a faster build, and
no build-time dependency on `deb.debian.org`.

Added an **optional** `pip_ca` build secret for hosts behind a
TLS-intercepting proxy — a certificate belongs in a build secret, never in an
image layer:

```bash
docker build --secret id=pip_ca,src=/path/to/corporate-ca.crt .
```

`tests/unit/test_container_build.py` keeps all of this from regressing.

### Compose (found during the Docker gate)

- **n8n crash-looped on an IPv4-only host.** It defaults to binding `::`; with
  `restart: unless-stopped` that becomes an endless restart loop, and
  `docker compose ps` reports the container as Up throughout. Fixed with
  `N8N_LISTEN_ADDRESS: 0.0.0.0`. The gateway's `/health` was the only thing
  that reported it correctly.

### Decisions worth recording

- **No passlib/bcrypt.** `hashlib.scrypt` from the standard library instead:
  bcrypt truncates at 72 bytes and the passlib/bcrypt pairing breaks across
  versions.
- **Logs go to stderr.** So stdout stays clean for machine-readable command
  output.
- **The application is built lazily.** `app.main:app` constructs on first
  attribute access, so importing the module does not open connections.
- **Two similarity threshold pairs.** A semantic embedder and the lexical
  fallback score on different scales; the lexical pair is set from a measured
  distribution and a test fails if a change closes the gap.
- **`local_success_rate` counts successes, not non-escalations.** A request
  that failed outright is not a local success.
