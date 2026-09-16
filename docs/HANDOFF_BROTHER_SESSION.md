# Handoff — the Brother session (2026-09-16)

For the next window. Read `CLAUDE.md` first, then this, then
`docs/OPEN_ITEMS.md`. The previous window was Fable; the owner's weekly
limit was reached mid-deployment, so this file carries the state exactly.

## 1. What this repository became today

AI Helper 1.0 was a generic local-first gateway with no owner. In one day it
became **Brother**, Shyam's personal assistant, in twelve commits on branch
`claude/exciting-hopper-uyy9gb` (b36ac85 → 808b5f2):

| Piece | Where | Status |
|---|---|---|
| Knowledge pack: 45 hand-written digests over 6 repos + 31 verbatim governing documents | `knowledge/` | loaded on the box: 77 documents, 1760 chunks |
| Four Brother agents sharing `BROTHER_LAWS` | `app/agents/builtin.py` | live; prefer `qwen2.5:7b` |
| Seeded solutions through the promotion gate | `app/knowledge/pack.py` | 229 PROMOTED, 1 VALIDATED, 48 REJECTED (by llama3.2:3b) |
| Live connectors: market news (ForexFactory), trading mirror (platform API v1) | `app/tools/live.py` | news live and verified; trading not configured (AIH-1) |
| Tool intents: direct level-0 answers and context readings | `app/tools/registry.py`, `dispatcher.py` | verified live ("news today?" answered in 0.1 s) |
| Dashboard chat as a queued job with polling, teach form | `app/api/routes/admin.py`, `templates/admin/chat.html` | verified live after the change |
| Teaching: owner corrections through the gate | `app/learning/teaching.py`, CLI `teach` | tested; not yet used by the owner |
| CLI: bootstrap-brother, load-knowledge, knowledge-status, ask, teach | `app/cli.py` | all used on the box |
| nginx helper, sync script, Dockerfile ships the pack | `scripts/` | used on the box |

Tests: 514 pass, ruff clean. Version 1.2.0. CHANGELOG has every change with
its reason.

## 2. The box (ai.signalmesh.dev, Contabo, hostname vmi3221804)

- Checkout: `/home/shyam/ai-helper`, branch `claude/exciting-hopper-uyy9gb`
  at the handoff commit or later (verify with `git log --oneline -1`; this file was written at 808b5f2).
- Stack: Docker Compose; ai-helper 1.2.0, PostgreSQL, Qdrant (connected),
  Ollama with `llama3.2:3b`, `nomic-embed-text` (semantic embedder is live)
  and `qwen2.5:7b` (pulled 19:35 UTC; used automatically by the Brother
  agents via `model_role="strong"`).
- nginx: `/etc/nginx/sites-available/ai.signalmesh.dev` carries
  `proxy_read_timeout 180s` and was reloaded by the helper script. The
  chat no longer depends on it.
- Admin password set; personal client `brother` exists; pack loaded
  (last `load-knowledge`: 8 ingested, 69 unchanged, 278 seeds skipped).
- `.env`: `LOCAL_TIMEOUT_SECONDS` may still read 60 from the first setup;
  the code default is 180. Check with `grep LOCAL_TIMEOUT .env`.
- No paid provider is enabled and the owner has said none will be.
- Open WebUI (port 3000, chat.signalmesh.dev) is running but bypasses
  Brother (AIH-8).

## 3. What was verified live and what was not

Verified by the owner's pasted output:
- `ask "news today?"` → LOW, next high-impact NZD GDP, fetched age 0 s,
  route tool, 0.1 s.
- The chat page answered "hello" (badly, before the small-talk fix) and
  later a plan question (a refusal, before the recipe and qwen).
- Bootstrap, seeding counts, pack reload counts as above.

Not yet observed:
- Any answer from `qwen2.5:7b`.
- The plan recipe in action.
- The teach form end to end on the box (tests only).
- `calibrate` on the box with the real embedder.

## 4. Laws learned today (all in CLAUDE.md, repeated because they cost time)

Nothing may wait on the local model (queue and poll). A greeting needs no
evidence. A plan question is a procedure. The refusal marker has variants.
A placeholder is not a secret, but the rule lives in one function. A long
bootstrap commits as it goes. What ships in the image is what runs. Check
the file, not the claim: the nginx directives were "added" twice before
they were found to be present but not reloaded.

## 5. The backlog, in the order to do it

1. **Observe the plan answer under qwen** (AIH-2). Ask
   "Gold at 4346, FOMC in a few minutes, what is the plan?" in `/admin/chat`.
   Read the route, confidence and sources line. If it still refuses, teach
   the correct plan through the form (the recipe document is the template)
   and re-ask; the second ask should be a memory hit.
2. **Configure the trading connector** (AIH-1). Owner makes a key at the
   platform's `/api-access`, two lines in `.env`, restart. Then verify the
   `stats` field names (AIH-5).
3. **Retry the 48 rejected seeds under qwen** (AIH-3): add
   `load-knowledge --retry-rejected`, small change in `seed_solutions`.
4. **Run `calibrate` and build the evals question set** (AIH-4/AIH-11).
   This is the gap the 1.0 handover named first, and the box can now run it.
5. **Decide Open WebUI** (AIH-8) with the owner.
6. **Outlook read endpoint** on the platform side (AIH-6), if the owner
   wants the recipe's "posted outlook" step to ever be present.

Do not: enable a paid provider; add an LLM to any control decision; make
the chat synchronous again; put facts into the prompts; widen the tool set
toward anything that acts.

## 6. Paste-ready opening prompt for the next window

```
Read /home/user/AIHELPER/CLAUDE.md, then docs/HANDOFF_BROTHER_SESSION.md,
then docs/OPEN_ITEMS.md. Branch claude/exciting-hopper-uyy9gb (HEAD: git log --oneline -1),
514 tests green. The box ai.signalmesh.dev runs 1.2.0 with qwen2.5:7b
pulled and the pack loaded; paid providers stay OFF by the owner's decision.
Start with OPEN_ITEMS AIH-2 (observe the plan answer under qwen, teach if it
refuses), then AIH-1 and AIH-3. Findings first, small verified diffs, pytest
and ruff before every commit, commands for Shyam paste-ready one per line.
```
