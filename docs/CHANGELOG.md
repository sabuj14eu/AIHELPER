# Changelog

Every schema change gets an Alembic revision and an entry here, with its
migration note. Deploys follow: **backup → migrate → restart → verify logs.**

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
