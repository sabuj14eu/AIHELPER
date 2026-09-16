# Changelog

Every schema change gets an Alembic revision and an entry here, with its
migration note. Deploys follow: **backup → migrate → restart → verify logs.**

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
