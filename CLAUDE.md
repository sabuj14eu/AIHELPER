# CLAUDE.md — AI Helper / Brother constitution

Read this before touching anything. This repository is **AI Helper**, the
self-hosted local-first AI gateway, and **Brother**, the personal assistant
layer on top of it that knows Shyam's other projects (Sniper-System,
brother-brain-v2, brother_sniper_v7, brother-developer, Accounting-) from a
knowledge pack. It runs at ai.signalmesh.dev on the Contabo box next to the
v18 brain. It observes and advises; it never trades, deploys, posts or acts.

## IRON RULES — NEVER VIOLATE
1. **Local first is control flow, not preference.** Every request walks the
   ladder in `app/gateway/router.py`: tools, retrieval, local model,
   validation, and only then a paid provider, and only if the client, the
   classification and the budget allow it. No new path may reach a paid
   provider around that ladder. The owner's standing decision (2026-09-16):
   **paid providers stay OFF for the personal client; make the local learner
   better instead.**
2. **No LLM in a control decision.** Task classification, tool dispatch and
   intents, escalation, budgets, privacy and the promotion gates are
   deterministic code. A model call in any of them is a defect.
3. **Advisory only.** No tool acts: no shell, no filesystem write, no
   arbitrary HTTP, nothing that places, modifies, dispatches, posts or
   switches anything. The live connectors (`app/tools/live.py`) read fixed,
   operator-configured URLs. An answer that claims to have acted fails
   validation.
4. **Learning goes through the gate, never around it.** A paid answer, a
   seeded pack solution and an owner-taught answer all become CANDIDATE and
   must pass validation and the local model's reproduction before PROMOTED.
   A rejection is never resurrected by a reload; a re-taught question
   supersedes (EXPIRED with reason), never edits.
5. **The pack is data; the prompts hold only the way of working.** Facts
   about the owner's systems live in `knowledge/` and are reloaded. The
   Brother laws in `app/agents/builtin.py` may not carry a number the pack
   should own (a test enforces it). AI Helper imports nothing from any other
   repository; `scripts/sync_knowledge.py` copies markdown, on purpose, and
   refuses anything the privacy detector reads as a secret.
6. **Per-client isolation in the query**, never by filtering afterwards.
   Memory, documents, solutions, jobs and logs carry `client_id`.
7. **Secrets** (.env, API keys, the platform key, MT5 credentials) are never
   committed, never logged, never printed in chat, never in the pack. The
   platform key is read from settings and never enters a tool's output or
   error.
8. **Every schema change ships with a migration note in docs/CHANGELOG.md.**
   Deploy on the box: `git pull` → `docker compose up -d --build ai-helper`
   → verify with `python -m app.cli ask "news today?"` and the logs.

## LAYOUT
- `app/gateway/` router (the ladder), escalation, provider manager.
- `app/tools/` closed tool set; `live.py` = market news + trading mirror;
  `registry.py` carries `IntentMatch`; `dispatcher.py` = level 0.
- `app/agents/builtin.py` generic agents + the four Brother agents and
  `BROTHER_LAWS`.
- `app/knowledge/pack.py` pack loader, seeding, `secret_probe`.
- `app/learning/` capture, promotion (the gate), `teaching.py`.
- `app/api/routes/admin.py` dashboard incl. `/admin/chat` (queued job +
  poll), `/admin/chat/teach`, `/admin/chat/ask-now`.
- `app/cli.py` bootstrap-brother, load-knowledge, knowledge-status, ask,
  teach, calibrate, expire.
- `knowledge/` the pack (see its README); `knowledge/sources/` verbatim
  copies stamped with commit and date.
- `scripts/` setup, sync_knowledge, nginx_add_timeouts, backup, health.
- `tests/` 514 tests; conftest disables the live connectors so no test
  reaches the network.

## WORKING LAWS LEARNED ON THE FIRST REAL DEPLOYMENT (2026-09-16)
- **A local model on CPU takes minutes; nothing may wait on it.** The chat
  queues a job and polls. Never reintroduce a synchronous path in the UI.
- **A greeting needs no evidence.** Retrieving for small talk produced a
  refusal. `is_small_talk` skips retrieval.
- **A plan question is a procedure, never a refusal.** News reading, posted
  outlook (ABSENT if none), the asset's standing rules, then the plan naming
  each input present or absent. `knowledge/brother/brother__trading_plan_recipe.md`.
- **The marker has variants.** "INSUFFICIENT CONTEXT" with a space passed as
  an answer at 0.65. The validator now catches space, dash and lower case.
- **A documented placeholder is not a secret** (`<BB_BRAIN_WEBHOOK_SECRET>`),
  but the probe is shared code (`secret_probe`), not a per-caller exception.
- **A long bootstrap commits as it goes.** Documents first, then one
  solution per commit; `--seed-limit` batches; interrupts are safe.
- **What ships in the image is what runs.** `knowledge/` was missing from
  the Dockerfile once; a test now checks every copied path exists and is
  not docker-ignored.

## SESSION HANDOFF AND OPEN ITEMS
**docs/HANDOFF_BROTHER_SESSION.md** is the living handoff: the state on the
box, what was verified live and what was not, the backlog in order, and the
paste-ready opening prompt for the next window. **docs/OPEN_ITEMS.md**
carries deferred work; an item deferred in conversation is an item
forgotten. Delete an entry only when it is done and verified, and say where
the proof is.

## HOW TO WORK HERE
Findings first, then code. Small verified diffs over rewrites. Run
`.venv/bin/python -m pytest -p no:cacheprovider` (without `-q`: the project
already sets it, and a second one hides the summary line) and
`.venv/bin/ruff check app tests scripts` before every commit. Never mark a
gate PASS from static inspection; if it did not run, it is NOT RUN. The
owner is Shyam; commands for him are written paste-ready, one per line, with
the directory, and say what output to expect.
