# AI HELPER — FINAL AUDIT

    Version          : 1.0.0
    Git commit       : 4f0a69d (base) + this audit's fixes
    Branch           : claude/self-hosted-ai-helper-ew0x2m
    Audited          : 2026-09-07
    Environment      : Python 3.11.15, SQLite, no GPU, no model weights,
                       Docker registry unreachable (see Docker, below)

    PRODUCTION STATUS: NOT APPROVED
    Reason: two acceptance criteria could not be executed in this environment
    (a real Ollama model and a Docker clean install). Everything that could be
    executed here passed. See "What is blocking approval".

---

## Tests

    Total    : 418
    Passed   : 418
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

## Docker

    Clean install                                              NOT RUN
    Restart persistence                                        NOT RUN (containers)

**This environment cannot reach a container registry.** Docker Hub's blob CDN
(`production.cloudfront.docker.com`) is refused by the network policy with 403,
and manifest requests return 429. `docker pull alpine:latest` fails, so no
image can be built or run here. This is an environment limitation, not a
finding about the Dockerfile — and it is also not a pass.

What was verified instead, statically and locally:

    docker-compose.yml validates (docker compose config)       PASS
    docker-compose.dev.yml overlay validates                   PASS
    Missing-secret guards fire (POSTGRES_PASSWORD etc.)        PASS
    Every COPY source in the Dockerfile exists                 PASS
    .dockerignore excludes nothing the image needs             PASS
    The container's start command works locally
      (alembic upgrade head && uvicorn --factory)              PASS
    The healthcheck path (/healthz) exists and answers         PASS
    Clean install from requirements.txt into an empty venv     PASS
    418/418 tests pass on that clean install                   PASS
    Named volumes cover every stateful service                 PASS

Restart persistence was proved at the process and database level (35/35 above),
which is the same property the volumes exist to provide. It has not been
proved through `docker compose down && up`.

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

Six issues were found during this audit. All six are fixed, each with a
regression test.

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

Two acceptance criteria could not be executed here. Neither is a defect; both
are things nobody has yet seen work.

**1. No real language model has ever run against this system.** There are no
model weights in this environment. Every "local model" and "paid provider" in
this audit is a protocol-faithful HTTP stand-in: the real `OllamaClient`,
`ModelManager`, `AnthropicProvider` and the whole gateway execute exactly as
they would in production, but the thing at the other end is a rule, not a
network. Specifically unproven:

- that a real 3B model's output passes the validation pipeline at a useful
  rate — the confidence weights and `CONFIDENCE_THRESHOLD` have never been
  calibrated against real model output, and if they are wrong the system either
  escalates constantly (expensive) or accepts poor answers (worse);
- that `nomic-embed-text` scores paraphrases above `SOLUTION_REUSE_THRESHOLD`
  (0.80). This is F1's unproven assumption and it is the assumption the entire
  cost-saving claim rests on. `ai-helper calibrate` now answers it in one
  command — run it first;
- that the reproduction gate behaves sensibly with a real model rather than
  approving nearly everything or rejecting nearly everything.

**2. The Docker image has never been built.** Registry access is blocked here.
The compose files validate and the start command works locally, but the build
itself is unverified.

### Before approving production, in order

1. On a machine with a registry: `./scripts/setup.sh`, then
   `./scripts/health_check.sh`. Confirm the image builds and every component
   reports OK.
2. `docker compose exec ai-helper python -m app.cli calibrate`. If it exits
   non-zero, fix the thresholds before anything else — until it passes, the
   system will pay for every reworded question.
3. `docker compose down && docker compose up -d`, then confirm a previously
   learned answer is still reused for free. That closes the Docker restart gap.
4. Run 50–100 real questions with paid providers **disabled**. Watch
   `local_success_rate` and `escalations_blocked`. Tune
   `CONFIDENCE_THRESHOLD` against real output before any money is at risk.
5. Only then enable one paid provider, with `AI_DAILY_API_BUDGET` set to a
   number you would be relaxed about losing. Watch
   `/api/v1/costs → by_escalation_reason` for a week.
6. Keep `AUTO_PROMOTE=false` until you have reviewed a few dozen promotion
   decisions and agree with them.
7. Restore a backup into a scratch environment. A backup that has never been
   restored is a hypothesis.

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

Each exits non-zero on any failure, so they work in CI.
