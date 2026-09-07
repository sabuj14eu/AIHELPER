# AI HELPER — FINAL AUDIT

    Version          : 1.0.0
    Git commit       : 4f0a69d (base) + this audit's fixes
    Branch           : claude/self-hosted-ai-helper-ew0x2m
    Audited          : 2026-09-07
    Environment      : Python 3.11.15, SQLite, no GPU, no model weights,
                       Docker registry unreachable (see Docker, below)

    PRODUCTION STATUS: NOT APPROVED
    Reason: ONE blocker remains — no real model weights are obtainable in this
    environment, which leaves the Real Ollama gate and the calibration gate
    unproven. The Docker and persistence gates, previously NOT RUN, now PASS
    for real. See "What is blocking approval".

    Second pass (2026-09-07, later): Docker Hub proved reachable through
    mirror.gcr.io, so the image was built for real and the full stack was run
    with real PostgreSQL and real Qdrant. Container restart persistence was
    proved with a real `docker compose down` / `up`.

---

## Tests

    Total    : 435
    Passed   : 435
    Failed   : 0
    Skipped  : 0
    Coverage : 89% of app/
    Stability: 5 consecutive full runs, 418/418 each time
    Lint     : ruff clean across app/, tests/, audit/

    tests/unit         202      tests/memory        30
    tests/gateway       69      tests/security      32
    tests/integration   37      tests/test_acceptance 2
    tests/fallback      34

The suite runs against a real database, the real gateway, the real validation
pipeline and the real cost tracker. Only the two model providers are doubles.
It also passes on a clean virtualenv built from `requirements.txt` alone,
which is the check that catches undeclared dependencies.

## Critical regression (the ten from the specification)

     1. A normal request does not call a paid API              PASS
     2. A successful local answer costs nothing                PASS
     3. A failed local answer escalates                        PASS
     4. The fallback is saved                                  PASS
     5. A validated fallback becomes candidate knowledge       PASS
        5b. A paid answer that fails validation is not stored  PASS
     6. Promoted knowledge lets the local model answer         PASS
     7. Budget prevents further paid calls                     PASS
        7b. Monthly budget also stops spending                 PASS
        7c. Per-request cap stops an oversized call            PASS
     8. Restricted information cannot be sent externally       PASS
        8b. A declared class above the ceiling is blocked      PASS
        8c. A client denied escalation never escalates         PASS
     9. One client cannot read another's private memory        PASS
        9b. Solutions are not shared between clients           PASS
        9c. Documents are not shared between clients           PASS
        9d. A tool cannot be pointed at another client         PASS
    10. The AI cannot execute arbitrary commands               PASS
        10b. Every tool declares permissions and risk          PASS
        10c. A client tool allow-list is enforced              PASS

## Live demonstration — 27/27

Run against a real uvicorn process talking HTTP to an Ollama endpoint and an
Anthropic endpoint. Nothing inside the application is stubbed.

    1st ask   route=paid   provider=anthropic  cost=$0.000858
              escalation=VALIDATION_FAILURE
              local model called over HTTP, answered INSUFFICIENT_CONTEXT
    saved     status=PROMOTED  gate 1 (validation) passed
                               gate 2 (local reproduction) passed
    2nd ask   route=local  memory_hit=True  exact_match=True  cost=$0.0000
              PAID API NOT CALLED
    dashboard requests, local, fallbacks, memory hits, promoted, cost all agree

    Local AI (real OllamaClient over HTTP)                     PASS
    Fallback to a paid provider                                PASS
    Candidate creation                                         PASS
    Validation gate                                            PASS
    Promotion gate                                             PASS
    Memory reuse, no paid call                                 PASS

## Cost protection — 25/25

Proved against a paid endpoint that counts every request it receives. A budget
enforced only in a mock is not enforced; here the proof is that the counter
does not move.

    Per-request cost cap                                       PASS
    Per-request size cap                                       PASS
    Daily budget                                               PASS
    Monthly budget (independent of the daily one)              PASS
    Exhaustion mid-run, without a restart                      PASS
      8 hard questions → 4 paid, then 4 local; $0.0035 of $0.034
    Spend never exceeds the budget                             PASS
    System keeps answering locally when the budget is gone     PASS
    Repeating a blocked request never resumes spending         PASS
    One request never calls a provider twice                   PASS
    A provider returning 500 is not retried in a loop          PASS
    A failed call's input tokens are still costed              PASS

## Privacy — 54/54 (with permissions)

    RESTRICTED data never reaches an external API              PASS
      API key, AWS key, private key block, DB URL with password
      — each classified RESTRICTED, blocked, counter unmoved
    A caller declaring PUBLIC cannot lower a RESTRICTED request PASS
    Secrets are not in the logs                                PASS
      provider key, prompt-supplied key, client API keys
    Prompt text is not in the logs                             PASS
    Document contents are not in the logs                      PASS
    The logs are still useful (request_id, route, outcome)     PASS
    The audit trail carries metadata, never content            PASS
    Every refusal to send is audited, not only every send      PASS  (fixed — see F3)
    API keys are not in Git                                    PASS
      .env is ignored; no env/key/pem file in any commit;
      no credential-shaped string in history outside tests

## Security — 51/51

    Authentication                                             PASS
      7 malformed-credential forms rejected; a real key id and
      a made-up one are indistinguishable; errors never echo
      the credential
    Authorization                                              PASS
      admin API, dashboard, forged cookie, revoked key
    Every non-public endpoint requires a key                   PASS  (fixed — see F4)
      29 endpoints enumerated from the schema with the right verb
    Rate limits                                                PASS
      burst throttled, retry_after returned, clients isolated
    Input validation                                           PASS
      12 malformed bodies, all 422
    File upload limits                                         PASS
      oversize, empty, 5 unsupported types, traversal filename
    SSRF protection                                            PASS
      no tool accepts a URL; metadata service, loopback, file://
      and the internal Ollama port all unreachable
    Prompt-injection defences                                  PASS
      a poisoned document was retrieved and did not take over;
      fenced, labelled untrusted, attributed as a source
    External API data controls                                 PASS

## Tool and agent restrictions

    Execute arbitrary shell commands              CANNOT — no such tool exists
    Modify its own code                           CANNOT — no write tool exists
    Modify Docker                                 CANNOT — no such tool exists
    Access arbitrary files                        CANNOT — 5 probes returned nothing
    Access another client's private memory        CANNOT — 11 isolation checks
    Make uncontrolled external requests           CANNOT — no tool takes a URL

The exposed tool surface is: calculator, date_calculator, document_list,
document_search, json_parser, memory_search, system_info. All read-only. The
one network-capable tool (web_search) is disabled by default and therefore not
exposed at all.

## Learning system — 29/29

    API result → Candidate → Validation → Promotion → Reusable knowledge

    An API answer enters as CANDIDATE, never as knowledge      PASS
    A CANDIDATE is not offered back to the model               PASS
      so the same question escalates again until promoted
    Gate 1 — a refusal is never stored                         PASS
    Gate 1 — an answer claiming an action is never stored      PASS
    Gate 2 — an answer the local model cannot use is REJECTED  PASS
    A REJECTED solution is never retrieved                     PASS
    A human rejection removes it from circulation immediately  PASS
      and the question escalates again rather than serving it
    The whole lifecycle is audited                             PASS
      captured / validated / promoted / rejected

`AUTO_PROMOTE` is false by default: with it off, nothing becomes reusable
knowledge without a person.

## Migrations and persistence — 35/35

    Fresh install (alembic upgrade head, empty database)       PASS
    Idempotent re-run                                          PASS
    Restart — memory, documents, solutions, request log,
      spend and the semantic index all survive                 PASS
    A learned answer is still reused after a restart, free     PASS
    Downgrade to base, then re-upgrade                         PASS
    Backup produced and verified to contain every table        PASS
    Database destroyed, restored from the dump                 PASS
    After restore: memory, solutions and the audit trail
      are intact, and the learned answer is reused free        PASS
    No lost memory                                             PASS

## Docker — second pass, now PASS

    Clean image build (no cache)                               PASS
    Full stack up                                              PASS
    Container restart persistence                              PASS
    PostgreSQL persistence                                     PASS
    Qdrant persistence                                         PASS

`mirror.gcr.io` reaches Docker Hub from this host, so the build and the stack
were exercised for real.

    docker compose build ai-helper      36s from a cold cache, 522 MB image
    docker compose up -d                postgres, qdrant, ollama, n8n, ai-helper
    alembic upgrade head                ran inside the container against real
                                        PostgreSQL: "Running upgrade -> 0001_baseline"
    startup log                         "vector_backend": "qdrant"  (not the fallback)
    HEALTHCHECK                         container reports healthy

One service could not start: **Open WebUI**. Its image is published only on
ghcr.io, whose blob storage this network refuses. It is an optional
human-facing chat surface that talks to Ollama directly and deliberately does
not go through the Gateway, so nothing else in this audit depends on it. It
remains NOT RUN.

### A build failure was found and fixed

The first real build failed: `apt-get install libpq5 curl` could not reach
`deb.debian.org`. Rather than work around it, the apt layers were removed,
because they turned out to be unnecessary — see F7 below.

### Container restart persistence — 30/30, twice

Real containers, real named volumes, a real `docker compose down` followed by
`up`. Row counts read straight from PostgreSQL with `psql`, and vector counts
straight from Qdrant's own API — not through the application, which could have
reported whatever it had cached.

    created         a memory item, a document, a learned+promoted solution
    before          postgres {clients 1, memory_items 1, documents 1,
                              document_chunks 1, solution_candidates 1,
                              cost_records 1, audit_events 19}
                    qdrant   {knowledge 1, memory 1, solutions 1}
    docker compose down                 containers removed, volumes retained
    docker compose up
    after           identical on every count
    then            the learned answer was still reused, locally, with NO paid
                    call, and semantic search still worked against Qdrant

    PostgreSQL restarted alone: data intact, app recovered   PASS
    Qdrant restarted alone: vectors intact                   PASS

No silent loss of learned experience.

## Documentation

    README commands run as written                             PASS
    Test count in the README corrected 388 → 418               FIXED
    .env.example documents every setting                       PASS  (fixed — see F5)
    No setting documented that the application does not read   PASS
    Deployment instructions match the compose files            PASS
    API docs list every implemented endpoint                   PASS  (one added)
    Architecture doc names only modules that exist             PASS
    Every enum value appears in the docs                       PASS
    No undocumented dependencies                               PASS
    Scripts are executable and syntactically valid             PASS

---

## Findings, and what was done about them

Eight issues were found across the two audit passes. All eight are fixed,
each with a regression test.

**F1 — Solution reuse can fail silently and expensively.** The similarity
threshold is chosen from *which class* of embedder is running (semantic or
lexical), never from a measurement of the model actually installed. If a
deployment's embedding model scores on a different scale than the defaults
assume, every paraphrase re-escalates and pays — forever, invisibly.

*Fixed:* `ai-helper calibrate` measures the live embedder against known
paraphrase and unrelated pairs, reports the distribution as JSON with a
verdict, and exits non-zero when the thresholds do not fit. It distinguishes
"the threshold is misplaced" (adjustable) from "this embedder cannot separate
related from unrelated text at all" (not a tuning problem), because telling
someone to adjust a threshold that cannot exist is worse than saying nothing.

**F2 — A near-miss was indistinguishable from an absence.** When a learned
solution was found but scored below the reuse threshold, nothing was recorded.
"Nothing similar exists" and "we scored 0.59 against a threshold of 0.80" need
completely different fixes and looked identical.

*Fixed:* retrieval now reports `near_miss_score` and `reuse_threshold` on every
response and logs the near miss. Three tests.

**F3 — The privacy refusal that actually fires left no audit row.** The
policy-layer block (the one that runs in production) recorded nothing; only the
last-ditch guard inside the provider manager audited, and that is only reached
if the policy layer is bypassed. The audit trail could answer "what did we send
out?" but not "what did we refuse to send, and why?".

*Fixed:* every refused escalation is now audited, privacy separately from
configuration, carrying the classification and the reason and no content. Four
tests.

**F4 — One endpoint was public by omission.** `/api/v1/documents/formats`
answered without a key. It discloses only a static list of file extensions, so
the impact is negligible — but it sat under an otherwise authenticated prefix
and was an oversight rather than a decision.

*Fixed:* it requires a key. More usefully, a test now enumerates the entire
OpenAPI surface with the correct verb for each route and fails on anything
reachable that is not in an explicit, justified public set.

**F5 — Dead security-relevant configuration.** `ALLOW_ANONYMOUS` was declared
in Settings, wired to nothing, and read exactly like a switch. An operator
could set it and reasonably believe they had changed something.

*Fixed:* removed, with a comment explaining why no such switch exists, and a
test that fails if a setting matching `ANONYMOUS|NO_AUTH|DISABLE_AUTH|SKIP_AUTH`
is ever added. Three live settings that were missing from `.env.example`
(`APP_NAME`, `OPENAI_BASE_URL`, `ANTHROPIC_BASE_URL`) are now documented, and a
test keeps `.env.example` and Settings in sync in both directions.

**F6 — Production could start on the published placeholder secret.**
`AUTH_SECRET` defaults to `change-me-in-production`, which is printed in this
repository and in `.env.example`. It signs the admin session cookie. A
production instance still carrying it could have an admin session forged by
anyone who has read the repo, and nothing warned or stopped it.

*Fixed:* with `ENVIRONMENT=production` the application **refuses to start**
unless `AUTH_SECRET` is at least 32 characters and is not the default, and
refuses to start with `DEBUG=true`. The error says how to generate one. Six
tests.

## What is blocking approval

One thing, and it is the same one thing in two places.

**No real language model has ever run against this system, and none can be
obtained here.** Every model-weight source is refused by this network's policy:

    registry.ollama.ai   403 denied      huggingface.co       403 denied
    ollama.com           403 denied      cdn-lfs.huggingface  403 denied

Only pypi is reachable. The Ollama *container* runs, and the real
`OllamaClient` talks to it over real HTTP, but with no model it cannot answer,
so the audit continues to drive a protocol-faithful stand-in. That leaves two
gates unproven:

**Real Ollama (§2) — NOT RUN.** The path
`request → gateway → model router → Ollama → response → validation → memory`
is exercised end to end over HTTP, but the responder is a rule, not a network.
Specifically still unknown: whether a real 3B model's output passes the
validation pipeline at a useful rate. `CONFIDENCE_THRESHOLD` and the confidence
weights have never been calibrated against real model output. If they are
wrong the system either escalates constantly (expensive) or accepts poor
answers (worse).

**Calibration (§6) — FAIL, correctly.** Run inside the container:

    $ docker compose exec ai-helper python -m app.cli calibrate
    THIS EMBEDDER CANNOT SEPARATE RELATED FROM UNRELATED TEXT.
      Paraphrases of the same question score as low as 0.000.
      Unrelated text scores as high as 0.105.
      Those ranges overlap, so no threshold exists that admits the
      first and rejects the second. This is not a tuning problem.
    exit 1

This is the gate working, not failing. Without `nomic-embed-text` the system
falls back to a lexical vectoriser that genuinely cannot match a reworded
question, and `calibrate` says so and refuses. Per §6, production status
therefore remains NOT APPROVED.

Both close with one command on a host that can reach `registry.ollama.ai`.

### To reach APPROVED

1. `docker compose exec ollama ollama pull nomic-embed-text`
   `docker compose exec ollama ollama pull llama3.2:3b`
2. `docker compose exec ai-helper python -m app.cli calibrate` — must exit 0.
   Until it does, learned solutions will not be reused for a reworded question
   and the system will pay for the same problem repeatedly.
3. `./scripts/health_check.sh` — the embedder must read OK, not DEGRADED.
4. Re-run `audit/demo_e2e.py` against the real model: confirm a hard question
   fails locally, escalates, is learned, and is then answered locally.
5. Run 50–100 real questions with paid providers **disabled**, and tune
   `CONFIDENCE_THRESHOLD` against what a real model actually produces.
6. Only then enable one paid provider, with a daily budget you would be
   relaxed about losing.
7. Keep `AUTO_PROMOTE=false` until you have reviewed a few dozen promotion
   decisions and agree with them.

Steps 1–4 are mechanical and should take under an hour. Step 5 is the one that
takes real time, and it is the one that decides whether the economics work.

**F7 — The image could not be built on a host without Debian's repositories.**
`apt-get install build-essential libpq-dev` (builder) and `libpq5 curl`
(runtime) failed against a network that refuses `deb.debian.org`. On inspection
none of them was needed: every dependency installs as a pre-built wheel,
`psycopg[binary]` bundles its own libpq, `useradd` is in the base image, and
`curl` existed only for the healthcheck.

*Fixed:* the apt layers are gone. `--only-binary=:all:` now makes the
wheel-only assumption a hard guarantee rather than a coincidence, the
healthcheck uses the interpreter already present, and an optional `pip_ca`
build **secret** (never a COPYed layer) lets the image build behind a
TLS-intercepting proxy. Smaller image, fewer packages to patch, faster build,
no build-time dependency on a Debian mirror. Eleven regression tests in
`tests/unit/test_container_build.py` keep it that way.

**F8 — n8n crash-looped forever while reporting itself as running.** On this
IPv4-only host n8n tried to bind `::`, failed, and — with
`restart: unless-stopped` — restarted endlessly. `docker compose ps` showed
"Up 12 seconds" the whole time. The gateway's own `/health` was the only thing
telling the truth, reporting n8n DOWN, which is precisely the failure mode
`docs/architecture.md` warns about: a container being "up" is not evidence
that a service works.

*Fixed:* `N8N_LISTEN_ADDRESS: 0.0.0.0` in `docker-compose.yml`; n8n now starts
and answers on `/healthz`. Five compose regression tests added covering the
listen address, named volumes on every stateful service, no port published
beyond loopback, no database port at all, and no silent default for any
secret.

## Standing limitations

Unchanged by this audit, documented in `docs/LIMITATIONS.md`, and worth
re-reading before deployment: validation detects mechanical failure modes and
cannot verify truth; the rate limiter and job queue are per-process; promotion
checks usability rather than correctness, so a confident wrong answer can reach
PROMOTED and be served for its TTL; learning is per client, so ten clients
asking the same hard question pay ten times.

## How to re-run this audit

    .venv/bin/python -m pytest                                   # 418 tests
    .venv/bin/python audit/demo_e2e.py                           # 27 checks
    .venv/bin/python audit/prove_cost.py                         # 25 checks
    .venv/bin/python audit/prove_privacy_and_permissions.py      # 54 checks
    .venv/bin/python audit/prove_security.py                     # 51 checks
    .venv/bin/python audit/prove_learning.py                     # 29 checks
    .venv/bin/python audit/prove_persistence.py                  # 35 checks
    .venv/bin/python audit/prove_container_persistence.py        # 30 checks
                                                    (needs the Docker stack up)

Each exits non-zero on any failure, so they work in CI.
