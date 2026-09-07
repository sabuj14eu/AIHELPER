# AI Helper

A self-hosted, local-first AI gateway. One service that several applications
can share, that answers as much as it can locally, pays for an external model
only when it must, and gets cheaper over time by learning from the cases it had
to pay for.

It is a standalone system. It does not import from, call, or share state with
any other application, and integrating one is deliberately out of scope for
v1 — see [Future integration](#future-integration).

---

## The idea in one diagram

```
                        request
                           │
                    ┌──────▼──────┐
                    │   GATEWAY   │
                    └──────┬──────┘
                           │
  level 0   deterministic tools ─────────────► answer   (0 tokens, $0)
                           │ no match
  level 1   memory + documents + learned solutions
                           │
  level 2   local model (Ollama), given that context
                           │
  level 3   validation ────┬──────────────────► answer   (local, $0)
                           │ failed
  level 4   is it allowed? ── no ─────────────► best local attempt, flagged
                           │ yes            (budget · privacy · permission)
                    paid provider
                           │
                     validate again
                           │
                    capture the case
                           │
              CANDIDATE → VALIDATED → PROMOTED
                           │
                  next time: level 1 hits
```

The last two boxes are the point of the system. A question that cost money once
should not cost money again.

## What it does

- **Local first, as control flow, not preference.** There is no code path that
  reaches a paid provider without having tried and failed at levels 0–3.
- **Cost protection that cannot be talked out of.** Per-request cap, daily
  budget, monthly budget, per-client budget. When one is reached, paid
  providers stop and the system keeps answering locally.
- **Learning from fallback, with gates.** A paid answer is not trusted because
  it was expensive. It becomes reusable only after it passes validation *and*
  the local model demonstrates it can answer the question with that solution in
  front of it.
- **Privacy that is checked twice.** RESTRICTED data never leaves the system —
  refused in the policy layer and again in the last function before the wire.
- **Per-client isolation.** Memory, documents, conversations, solutions and
  logs are scoped to a client id, in the query, not by filtering afterwards.
- **Advisory only.** It analyses, explains, summarises, classifies and
  recommends. It has no tool that performs an outside action, and an answer
  claiming otherwise fails validation.

## Requirements

- Docker and Docker Compose v2
- ~8 GB RAM for a 3B local model, ~16 GB for a 7B one
- ~20 GB disk for models
- No API key from anyone. Paid providers are off by default and the system is
  fully functional without them.

## Install

```bash
git clone <this-repo> ai-helper && cd ai-helper
./scripts/setup.sh
```

`setup.sh` generates secrets into `.env`, starts the stack, waits for the
gateway, and pulls the default models. Then:

```bash
# a dashboard password
docker compose exec ai-helper python -m app.cli hash-password
#   → paste the ADMIN_PASSWORD_HASH= line into .env, then:
docker compose restart ai-helper

# an API key for your first client
docker compose exec ai-helper python -m app.cli create-client myapp
```

| Surface | URL |
|---|---|
| Gateway API | http://localhost:8000 |
| API docs (OpenAPI) | http://localhost:8000/docs |
| Admin dashboard | http://localhost:8000/admin |
| Open WebUI | http://localhost:3000 |
| n8n | http://localhost:5678 |

Ports bind to `127.0.0.1`. Put a TLS-terminating proxy in front before
exposing anything. See `docs/deployment.md`.

## Use it

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer ahk_..." \
  -H "Content-Type: application/json" \
  -d '{"message": "What is 1200 * 0.23?"}'
```

```json
{
  "answer": "276",
  "route": "tool",
  "provider": "tool",
  "cost_usd": 0.0,
  "confidence": 1.0,
  "notes": ["answered by a deterministic tool; no model was consulted"]
}
```

Every response says which level answered it, what it cost, how confident the
validation was, what it retrieved, and — when it escalated — exactly why.

## Configure

Everything is environment variables; `.env.example` documents each one with its
default and the reason for it. The four that matter most:

```bash
OPENAI_ENABLED=false          # paid providers are opt-in, and need a key too
ANTHROPIC_ENABLED=false
AI_DAILY_API_BUDGET=5.00      # hard stop, no override path
EXTERNAL_ALLOWED_CLASSIFICATIONS=PUBLIC,INTERNAL   # RESTRICTED is refused here
```

## Run the tests

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest            # the whole suite; no external services needed
.venv/bin/python -m pytest tests/test_acceptance.py -s   # the acceptance scenario
```

418 tests at the time of writing. They run against a real database, the real
gateway, the real validation pipeline and the real cost tracker; only the two
model providers are fakes.
`tests/gateway/test_critical_regressions.py` holds the ten guarantees from the
specification, and `tests/fallback/test_cost_saving_cycle.py` holds the one that
matters most: a question is paid for once and answered locally thereafter.

## Documentation

| Document | What is in it |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Every component, the routing ladder, why each boundary is where it is |
| [`docs/api.md`](docs/api.md) | Endpoints, authentication, response fields, integration |
| [`docs/security.md`](docs/security.md) | Authentication, permissions, privacy, external-call rules, threat notes |
| [`docs/deployment.md`](docs/deployment.md) | Production install, TLS, resources, upgrades |
| [`docs/operations.md`](docs/operations.md) | Backups, models, logs, troubleshooting, tuning |
| [`docs/CHANGELOG.md`](docs/CHANGELOG.md) | Releases and migration notes |
| [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) | What this does not do, and what it costs you |
| [`audit/AUDIT_REPORT.md`](audit/AUDIT_REPORT.md) | Independent verification, findings, and the production verdict |

Read `docs/LIMITATIONS.md` before you rely on any of this in production. It is
short, and it is the honest half of this README.

**Production status: NOT APPROVED.** No real language model has ever run
against this system, and the Docker image has never been built — both because
the build environment had neither. `audit/AUDIT_REPORT.md` lists exactly what
that leaves unproven and the seven steps to close it.

## Future integration

An application connects by holding an API key and calling `POST
/api/v1/chat`. Each gets its own credentials, permissions, budget, tool
allow-list, memory namespace and knowledge namespace, and cannot read another's.
None of that requires a change to the Gateway.

Doing that integration is out of scope for v1, by the specification, and should
not start until this standalone system passes its acceptance test in your own
deployment.

## License

MIT — see [LICENSE](LICENSE).
