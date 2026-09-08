# AI HELPER — FINAL AUDIT

    Version          : 1.0.0
    Base commit      : b36ac85  (+ this audit's fixes)
    Branch           : claude/ai-helper-final-audit-uv46bj
    Audited          : 2026-09-08
    Scope            : the AI Helper repository ONLY. No other project — accounting,
                       shop, the trading bot, SignalMesh, LokalnyDowoz — was read,
                       written, restarted or touched. No shared or production
                       database, container, service or credential was used.
    Environment      : Python 3.11.15; an isolated, throwaway Docker daemon on a
                       private socket and data-root, project name "ai-helper";
                       fresh audit-only Postgres/Qdrant/Ollama containers and named
                       volumes; SQLite for the test suite. No model weights are
                       obtainable here (see BLOCKED).

    PRODUCTION STATUS: NOT APPROVED
    Reason: exactly one gate cannot be satisfied in this environment — no real
    language model or embedding model has ever run against the system, because
    every model-weight source is refused by the network policy. Everything that
    CAN be tested here was, and five real defects were found and fixed, each
    with a regression test. The verdict is NOT APPROVED on the real-model gate
    alone, not on any unfixed defect.

---

## The audit boundary record

    Project              : AI Helper / Local AI
    Repository           : /home/user/AIHELPER  (github sabuj14eu/AIHELPER)
    Git commit at start  : b36ac85
    Working directory    : /home/user/AIHELPER
    Docker project name  : ai-helper  (isolated daemon at unix:///tmp/aihelper-dockerd.sock,
                           data-root /tmp/aihelper-docker-root — not the host daemon)
    Test database        : audit-only Postgres container + volume ai-helper_postgres_data;
                           SQLite in-memory / tmp files for the unit suite
    Qdrant instance      : audit-only Qdrant container + volume ai-helper_qdrant_data
    Ollama instance      : audit-only Ollama container + volume ai-helper_ollama_models
                           (no model pulled — the registry is unreachable)

Every resource above was created for this audit. Nothing shared with, or
belonging to, another application was read or modified.

---

## VERIFIED — things actually executed and passed

### Tests

    Total    : 445  (435 pre-existing + 10 new regression tests)
    Passed   : 445
    Failed   : 0
    Skipped  : 0
    Coverage : 89% of app/
    Stability: 3 consecutive full runs, 445/445 each
    Lint     : ruff check clean across app/, tests/, audit/

The suite runs against a real database, the real gateway, the real validation
pipeline and the real cost tracker. Only the two model providers are doubles.

### Live audit suites (network-free, real uvicorn over HTTP)

    demo_e2e                        DEMONSTRATION PASSED             27/27
    prove_cost                      COST PROTECTION PROVEN           25/25
    prove_privacy_and_permissions   PRIVACY AND PERMISSIONS PROVEN   54/54
    prove_security                  SECURITY SURFACE PROVEN          51/51
    prove_learning                  LEARNING SYSTEM PROVEN           29/29
    prove_persistence               PERSISTENCE PROVEN               35/35

### Docker and container persistence (isolated daemon)

    Clean image build (--no-cache)                    PASS   522 MB, ~59 s
      via the documented pip_ca build secret; see the Docker note below.
    Full stack up (postgres, qdrant, ollama, app)     PASS
    alembic upgrade head inside the container         PASS
    HEALTHCHECK reports healthy                        PASS
    prove_container_persistence                        PASS   30/30
      create data → docker compose down → up → row and vector counts identical;
      learned answer still reused locally and free; individual service restarts
      survive. Row counts read straight from PostgreSQL with psql and vector
      counts from Qdrant's own API, not through the application.

### Local-first routing, fallback, learning, cost, privacy, security

All exercised by the suites above against the real gateway with protocol
stand-in providers:

    Local-first (no paid call on a solvable request)   PASS
    Controlled fallback with a recorded reason         PASS
    CANDIDATE → VALIDATED → PROMOTED, gated             PASS
    Memory reuse (exact fingerprint), free             PASS
    Per-request / daily / monthly / per-client budget  PASS
    RESTRICTED never leaves; refusal audited           PASS
    Authentication, authorization, client isolation    PASS
    Tool permissions, no arbitrary executor, SSRF      PASS

---

## Findings, and what was done about them

Five defects were found by line-by-line review and proved with a failing test
before the fix. All five are fixed; each has a regression test in
`tests/security/test_audit_findings.py`, and the whole suite is green after.

**F1 — Retrieved context bypassed the classification gate (HIGH, privacy).**
A request's classification was computed from the user's *message* only. But the
prompt that actually reaches a paid provider also carries everything retrieval
put in front of the model — document chunks, long-term memory items, learned
solutions — each with its own stored classification that nothing read. So a
memory item written as RESTRICTED, or a document ingested as CONFIDENTIAL,
retrieved for an ordinary INTERNAL question, was sent verbatim to the external
provider. This is exactly the disclosure the privacy layer exists to prevent,
and it was reproducible: a RESTRICTED note ("the secret margin is forty-two
percent") left the system inside an INTERNAL question.

*Fix:* `RetrievalResult.effective_classification()` returns the highest
classification across the message and every retrieved item (an unknown or
missing label is treated as RESTRICTED, never as safe), and the gateway raises
the request to it before the escalation decision. A CONFIDENTIAL chunk or a
RESTRICTED memory item now lifts the whole request out of what may leave, and
the refusal names which sources raised it — as counts, never content. Verified:
`TestContextClassificationGate` (3 tests, including one that confirms ordinary
INTERNAL context still escalates, so the gate did not become a blanket block).
*Files:* `app/memory/retrieval.py`, `app/gateway/router.py`,
`app/local_ai/prompts.py`.

**F2 — Refusals raised out of the auth layer left no audit row (MEDIUM,
audit integrity).** An authentication failure and a rate-limit block are raised
from the request dependency, before the route runs. The request session is then
rolled back on the way out — taking the audit row for that refusal with it. The
audit trail could therefore not answer "who was turned away, and why", which is
the first question an audit trail exists to answer. (Privacy-block refusals,
written from inside the route, did persist — only the dependency-layer refusals
were lost.)

*Fix:* `audit.record_durable()` writes those refusals in their own committed
transaction, independent of the rejected request. It never re-raises — losing
the request to a logging failure would be worse than losing the log. Verified:
`TestRefusalsAreDurablyAudited`. *Files:* `app/core/audit.py`, `app/api/deps.py`.

**F3 — A recorded charge was discarded if later bookkeeping raised (MEDIUM,
cost integrity).** After a paid call was made and its CostRecord written, the
gateway still ran solution capture and conversation storage on the same
session, and `handle()` then wrote the request log. An exception in any of
those rolled the whole session back — including the CostRecord for a call that
really happened and was billed. Money spent with no record of the spend is the
one thing the cost layer must never allow.

*Fix:* the post-payment steps (`_learn`, `_remember_answer`, `_log_request`) are
guarded so a failure in bookkeeping cannot roll back a billed charge; the charge
and the answer stand, and the failure is logged. Verified:
`test_a_recorded_charge_survives_a_failure_in_post_call_bookkeeping`.
*File:* `app/gateway/router.py`.

**F4 — Bad input returned 500 instead of a clean 4xx (LOW/MEDIUM,
robustness).** Three paths raised an uncaught `ValueError`/`PermissionError`
and surfaced as a 500: an invalid `classification` on document upload, an
invalid classification on admin client creation, and re-using another client's
`conversation_id` on `/chat`. The last also contradicted the code's own stated
intent (a cross-client id should be not-found, not a server error).

*Fix:* the two classification paths validate at the boundary and raise a 422;
the cross-client conversation raises a clean 404, revealing nothing about
whether the id exists. Verified: `TestBadInputIsAFourHundred` (3 tests).
*Files:* `app/api/routes/documents.py`, `app/api/routes/admin.py`,
`app/gateway/router.py`.

**F5 — /costs disclosed every client's provider/model breakdown (MEDIUM,
isolation).** `GET /api/v1/costs` returned `by_provider` and
`by_escalation_reason` computed across all clients, to any authenticated
client. A non-admin could see which models other clients used and what they
cost — a per-client-isolation violation, unlike the sibling `/usage` endpoint
which already scoped by client.

*Fix:* both breakdowns are scoped to the calling client for non-admins (admins
still see the deployment). The top-line spend-against-budget figures remain
global by design and are documented as such: the daily and monthly budgets are
a single shared limit every client is subject to, so a client must be able to
see when paid calls are globally disabled by budget. Verified:
`test_costs_breakdown_is_scoped_to_the_client_for_a_non_admin`.
*Files:* `app/cost/tracker.py`, `app/api/routes/usage.py`.

No schema change was made, so there is no migration.

---

## BLOCKED — prevented by the environment, not by the product

**Real Ollama (a real local model) — BLOCKED.** No model weights can be
obtained here. Every source is refused by the network policy:

    registry.ollama.ai   403        huggingface.co        403
    ollama.com           403        cdn-lfs.huggingface   (no route)
    github release asset 403        modelscope / mirrors  (no route)

Only PyPI is reachable. The Ollama *container* runs and the real `OllamaClient`
talks to it over real HTTP, but with no model installed it cannot answer, so
every "local model" and "paid provider" in this audit is a protocol-faithful
HTTP stand-in. The real gateway, validation, cost tracker, database, Qdrant and
persistence all execute exactly as in production — but the thing answering is a
rule, not a network. The Qdrant collections named `…ollama-nomic-embed-text`
during the persistence gate are the stand-in reporting that model name, not real
weights.

**Docker clean build — PASS, with a note.** This environment's egress is a
TLS-intercepting proxy, so `pip` inside a plain `docker build` cannot verify the
certificate chain and the build fails loudly (which is the Dockerfile's
intended behaviour). Supplying the proxy CA through the documented `pip_ca`
build **secret** builds the image cleanly:

    docker build --secret id=pip_ca,src=<proxy-ca.crt> -t ai-helper .

The plain-build failure is an artefact of the intercepting proxy, not a defect;
the product ships exactly the mechanism needed for it.

**Open WebUI — NOT RUN.** Its image is published only on ghcr.io, whose blob
storage this network refuses. It is an optional human chat surface that talks to
Ollama directly and does not go through the Gateway, so nothing else depends on
it.

---

## NOT PROVEN — true, but not empirically established here

- **The confidence weights and `CONFIDENCE_THRESHOLD` (0.62).** Five weighted
  signals summing to 1.0, all calibrated against a rule-based stand-in. They
  directly control spend and have never been measured against real 3B-model
  output. This is the least evidence-backed thing in the repository.
- **Memory reuse for a paraphrase.** Exact-match reuse is proven. Paraphrase
  reuse depends on a real semantic embedder, which cannot run here; `calibrate`
  correctly refuses on the lexical fallback (see below).
- **The two semantic threshold pairs (0.72 / 0.80).** Inherited convention,
  never measured against a real embedding model.

---

## CALIBRATION — the freshness gate, working correctly

`python -m app.cli calibrate` against the lexical fallback embedder:

    verdict: no_separation   (exit 1)
    Paraphrases score as low as 0.000; unrelated text as high as 0.105 — the
    ranges overlap, so no threshold can admit the first and reject the second.

This is the gate doing its job, not a failure: without a real embedding model
the system says so and refuses, rather than silently re-escalating (and paying
for) every reworded question. It will exit 0 only once `nomic-embed-text` is
installed and measured.

---

## Gate summary

    Real Ollama (real weights) ........ BLOCKED   (no weights obtainable)
    Local-first routing ............... PASS
    Fallback .......................... PASS
    Learning / validation ............. PASS
    Promotion ......................... PASS
    Memory reuse (exact) .............. PASS
    Memory reuse (paraphrase) ......... NOT PROVEN (needs a real embedder)
    Calibration ....................... FAIL, correctly (gate refuses the fallback)
    Cost controls ..................... PASS
    Privacy (incl. F1 fix) ............ PASS
    Security / auth / authz ........... PASS
    Client isolation (incl. F5 fix) ... PASS
    Docker clean build ................ PASS (with the pip_ca CA secret)
    Container restart persistence ..... PASS   30/30
    PostgreSQL persistence ............ PASS
    Qdrant persistence ................ PASS
    Full regression suite ............. PASS   445/445, thrice

---

## OPEN QUESTIONS / future evaluation roadmap

1. Run 50–100 real questions with paid providers disabled and tune
   `CONFIDENCE_THRESHOLD` against what a real 3B model actually produces. This
   decides whether the economics work and is pure guesswork until done.
2. Build an evals harness (a fixed question set with expected outcomes) so a
   change to the confidence weights can be measured rather than assumed.
3. Promotion validates *usability*, not *truth*: a confident, well-formed,
   wrong paid answer can still reach PROMOTED. Keep `AUTO_PROMOTE=false` and
   review promotion decisions until the pattern is trusted.
4. Per-process rate limiter and job queue cap the deployment at one worker;
   move to Redis / a real queue before scaling out.

---

## To reach APPROVED (unchanged, on a host that can reach the model registry)

    docker compose exec ollama ollama pull nomic-embed-text
    docker compose exec ollama ollama pull llama3.2:3b
    docker compose exec ai-helper python -m app.cli calibrate     # must exit 0
    ./scripts/health_check.sh                                     # embedder OK, not DEGRADED
    python audit/demo_e2e.py                                      # against the real model
    # then the 50–100 real-question tuning pass, then enable one paid provider.

## How to re-run this audit

    python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
    .venv/bin/python -m pytest                                    # 445 tests
    .venv/bin/python audit/demo_e2e.py                            # 27
    .venv/bin/python audit/prove_cost.py                          # 25
    .venv/bin/python audit/prove_privacy_and_permissions.py       # 54
    .venv/bin/python audit/prove_security.py                      # 51
    .venv/bin/python audit/prove_learning.py                      # 29
    .venv/bin/python audit/prove_persistence.py                   # 35
    .venv/bin/python audit/prove_container_persistence.py         # 30 (stack up)
