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

## B. Production run — to be completed by the operator

Run `./scripts/deploy_v1.0.0.sh` from the AI Helper checkout on the server and
paste its output below. It stops rather than guesses at every check.

    Server           :
    Executed by      :
    Timestamp (UTC)  :
    Commit deployed  : 080bdf10cbec7eb961243e436bf184970caa3965
    Services changed : ai-helper, postgres, qdrant, ollama, n8n, open-webui
                       (compose project ai-helper; nothing else)
    Backup taken     : (path from scripts/backup.sh)
    Smoke tests      : (paste the script's output)
    Open WebUI       : reachable on 127.0.0.1:3000 — yes/no; first admin account created — yes/no
    Other projects   : observed only; all containers still "Up" — yes/no

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
