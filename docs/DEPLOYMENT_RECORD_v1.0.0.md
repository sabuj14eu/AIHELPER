# Deployment record — AI Helper v1.0.0

    Approved commit : 080bdf10cbec7eb961243e436bf184970caa3965  (tag v1.0.0)
    Gate report     : audit/REAL_MODEL_GATE.md
    Scope           : compose project `ai-helper` only. No other project, database,
                      Docker stack, service, .env or credential is read or changed.

## A. Rehearsal on the exact commit (2026-09-09, isolated environment)

The full runbook was executed against a stack built from `080bdf1` on an
isolated Docker daemon (4 CPU, no GPU), with the production-default
configuration (paid providers disabled). Output:
`audit/results/real_model_gate_2026-09-09/deployment_rehearsal_080bdf1.txt`.

| Check | Result |
|---|---|
| HEAD is the approved commit, tree clean | yes |
| `calibrate` inside the container | exit 0 |
| PostgreSQL | accepting connections |
| Qdrant | 6 collections, reachable |
| Ollama / models | llama3.2:3b, nomic-embed-text listed; embedder OK |
| API health (`scripts/health_check.sh`) | overall ok, every component OK, paid DISABLED |
| Authentication | `/api/v1/usage` without a key → 401; non-admin key on an admin route → 403 |
| Local model inference | "What is the capital of Poland?" → route local, ollama, llama3.2:3b, "Warsaw", cost 0, 1.9 s |
| Memory / RAG | item written, semantic search hit 0.83 with nomic-embed-text; chat answered from it (memory hit, 0.925) |
| Privacy gate | RESTRICTED request → CLASSIFICATION_BLOCKED, no paid route, cost 0 |
| Cost tracking | `/api/v1/costs` reports budget 5.00, spend 0, not disabled by budget |
| Paid providers | openai DISABLED, anthropic DISABLED |
| Persistence | `restart ai-helper` only → request log and memory still present |
| Admin dashboard | `/admin/login` 200; `/admin/` without a session 401 |
| Open WebUI | **not verified**: its image is on ghcr.io, whose blob storage this environment refuses. Verify on the server (`docker compose -p ai-helper logs open-webui`, then http://127.0.0.1:3000 through an SSH tunnel). |

One observation worth carrying to the server: right after a host reboot the
first request timed out (route `failed`, LOCAL_TIMEOUT) because the model's
cold load took 36 s on this CPU against the default `LOCAL_TIMEOUT_SECONDS=60`.
With the documented CPU-host value of 180 the same request answered in 1.9 s.
Set 180 in the production `.env`, or expect the first request after a restart
to fail while the model loads.

## B. Production run — DONE (2026-09-09)

    Server           : vmi3221804 (shared host; AI Helper checkout ~/ai-helper)
    Executed by      : shyam, via scripts/deploy_v1.0.0.sh (run from a copy)
    Timestamp (UTC)  : 2026-09-09T15:15:46Z  (DEPLOYED line of the script)
    Commit deployed  : 080bdf10cbec7eb961243e436bf184970caa3965  (v1.0.0, first install)
    Services changed : ai-helper, postgres, qdrant, ollama, n8n, open-webui
                       (compose project ai-helper; nothing else)
    Backup taken     : none — first install, no data existed (SKIP_BACKUP=1)
    .env             : ENVIRONMENT=production, MEMORY_SIMILARITY_THRESHOLD=0.55,
                       SOLUTION_REUSE_THRESHOLD=0.80, ANTHROPIC/OPENAI disabled,
                       LOCAL_TIMEOUT_SECONDS=180, generated secrets, admin hash set

Smoke tests (script output, third run; the first two runs stopped on a
transient empty search right after the embedding model's cold load, and on
the script's own port check misreading a port held by AI Helper's container —
both fixed, nothing else changed):

    health_check.sh          overall ok (v1.0.0, production); gateway, database,
                             qdrant, ollama (nomic-embed-text, llama3.2:3b), n8n,
                             embedder all OK; openai/anthropic DISABLED
    PostgreSQL               accepting connections
    authentication           no key → 401
    local inference          route local, ollama, llama3.2:3b, "Warsaw.", cost 0,
                             25.1 s (cold load on CPU)
    memory / RAG             semantic, nomic-embed-text, top score 0.785
    privacy gate             RESTRICTED → CLASSIFICATION_BLOCKED, cost 0
    cost tracking            daily budget 5.00, no spend
    paid providers           DISABLED, DISABLED
    persistence              memory still found after restarting ai-helper only
    admin dashboard          /admin/login → 200
    Open WebUI               127.0.0.1:3000 → 200, container healthy (loopback only)
    containers               six ai-helper-* containers Up; app healthy
    other projects           brotherbot (app, db, redis), lokaldowoz (app, db,
                             redis), balispa — all still Up, observed only

Open items after deployment (still pending):
- Revoke the three test clients from /admin: smoke-1788963729,
  diag-1788964478, smoke-1788966843.
- Change the dashboard password (it was typed into a terminal once):
  hash-password again, escape `$` as `$$` in .env, recreate ai-helper.
- Push the tag: `git push origin v1.0.0` from the server checkout.
- Docker Compose interpolates `$` in .env values: any future value containing
  `$` (the scrypt hash does) must be written with `$$`.

## B2. Public routing — DONE (2026-09-09)

One hostname per application, one nginx server block per hostname, no path
sharing: Open WebUI serves its own backend under `/api/...`, so sharing a
hostname with AI Helper's `/api/v1` would have shadowed one of them.

    https://ai.signalmesh.dev/        → 127.0.0.1:8000  AI Helper: API /api/v1/*,
                                        /docs, /health, dashboard /admin
    https://chat.signalmesh.dev/      → 127.0.0.1:3000  Open WebUI (own login,
                                        signup disabled; talks to Ollama directly —
                                        v1.1 will route it through the gateway)
    not proxied, loopback only        Ollama 11434, PostgreSQL, Qdrant 6333, n8n 5678

    DNS               A records ai/chat.signalmesh.dev → 62.171.164.19 (DNS only)
    nginx (shared)    inspected first: no conflicting server_name; two NEW files
                      sites-available/{ai,chat}.signalmesh.dev, symlinked, nginx -t,
                      reload (never restart). app.signalmesh.dev untouched.
    TLS               certbot --nginx, one certificate covering both names
                      (/etc/letsencrypt/live/ai.signalmesh.dev, expires 2026-12-08,
                      auto-renew scheduled), HTTP → HTTPS redirect.
    incident          certbot ran before the chat vhost existed and cloned the
                      shared `default` static server for chat.signalmesh.dev; the
                      two added blocks were removed (file backed up first as
                      ~/nginx-default.bak-*), the pre-existing lokalnydowoz.pl
                      entries in that file were not touched, and the chat vhost was
                      written with the issued certificate directly.
    verification      GET https://ai.signalmesh.dev/health → "status":"ok"
                      /admin/login reachable · /api/v1/usage without key → 401
                      https://chat.signalmesh.dev/ → 200 · http → 301
                      ports 8000, 3000, 11434, 5432, 6333, 5678 closed on 62.171.164.19

## C. Rollback

1. `git checkout <previous commit or tag>` in the AI Helper checkout.
2. `docker compose -p ai-helper up -d --build` (AI Helper services only).
3. Restore the backup taken in step 6 with the restore procedure in
   `scripts/backup.sh`. v1.0.0 ships **no schema migration**, so the database
   from v1.0.0 also works unchanged with the previous commit; restoring is only
   needed if data must be rolled back too.
4. `./scripts/health_check.sh`.

## D. Frozen after deployment

v1.0.0 is frozen once §B is complete. Not in this release, by explicit
decision: routing Open WebUI through the Gateway (Open WebUI talks to Ollama
directly and bypasses privacy, budget, validation, learning and audit — a v1.1
design), enabling any paid provider (findings A and B in the gate report
first), threshold changes, redesigns.
