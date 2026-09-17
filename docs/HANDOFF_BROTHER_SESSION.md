# Handoff — the Brother session (2026-09-16)

## THE BOX — VERIFIED 2026-09-17

```
/home/shyam/ai-helper            # the checkout AND the compose project
/home/shyam/ai-helper/docker-compose.yml
```

Confirmed by `docker compose ls` on the box: project `ai-helper`, running(6).
This is the one place the path is recorded; every other doc points here. It
was wrong in two docs before this line existed — a session invented
`/home/shyam/AIHELPER` from the repository name, `docs/deployment.md` says
`/opt/ai-helper` because that is where the *install guide* puts it, and only
the box knows which is true.

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

**Updated 2026-09-16 evening (§6b):** now 522 tests, version 1.2.1, and the
work continues on branch **`claude/epic-euler-4k1gl1`**, which was
fast-forwarded from `claude/exciting-hopper-uyy9gb` (no history rewritten, no
commits lost). The box is still checked out on the old branch name — §7 step 1
switches it.

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

## 6b. Session of 2026-09-16, evening — what AIH-2 actually showed

The plan question was asked on the box and the answer was **not** the refusal
we were braced for. It was nothing at all: an empty bubble, `route failed ·
UNVERIFIED`, with `tool:market_news:ELEVATED` and five document chunks in the
sources. Levels 0 and 1 did their jobs. Level 2 returned nothing.

The useful tell is what is *missing* from that line: there is no confidence.
Confidence is only set when the local call returns, so the call raised rather
than answering — a timeout or an unreachable Ollama, and the screen could not
tell you which, because the reason was being thrown away.

That last part was a defect in this repository and is fixed (1.2.1, 443e8a5):
`_degraded` recorded the cause only `if not base.notes`, and by the time it is
reached a note always exists on this box, because paid providers are off and
"escalation blocked: …" is appended on the way there. So the one fact worth
having was suppressed by the owner's own configuration. It is now recorded on
every failed request and put first.

Two things follow that the next window should hold on to:

- **A note guard that reads "only if we have nothing else to say" is a trap.**
  It made the system quietest exactly where it mattered most.
- **A test that asserts `response.notes` is not a test.** It checked that there
  were notes, not that any of them said why, and that is how this survived a
  release. It now asserts the content.

Also done this session: `load-knowledge --retry-rejected` for AIH-3
(supersedes, never deletes — Iron Rule 4), and the trading mirror's field
names verified against Sniper-System `3257184` for AIH-5, which turned up two
rendering defects (`win_rate` had lost its `%`; a null statistic vanished
instead of reading UNKNOWN). Version 1.2.1, 522 tests, ruff clean.

## 6c. The architecture audit, and Phases 1-3 (2026-09-16, later)

The owner read the failed plan answer and asked for an audit rather than a
patch. It found two failures stacked on one another: the local model raised
(proximate), and **even a perfect answer would probably have been discarded**
(structural). He then authorised Phases 1-3, which are built and pushed.

| | Shipped | What it fixes |
|---|---|---|
| Phase 1 | 1.3.0 `d6a91f5` | Four answer states. "The evidence is not available" stops rendering as a failure. "I don't have enough information" stops being scored as a refusal. The chat leads with the answer; route, sources and cost move behind *why*. |
| Phase 2 | 1.3.1 `ce1fa76` | BASE_SYSTEM stops ordering a refusal that BROTHER_LAWS forbids. The plan procedure moves into the prompts of the agents that answer plan questions. |
| Phase 3 | 1.4.0 `5acbdec` | A deterministic agent router — the gold question now reaches the *trading* agent. Per-message task classification works again in the chat. |

565 tests, ruff clean, no schema change, every phase reverts with one
`git revert`.

Traced end to end locally, with the owner's exact question:

```
QUESTION : Gold now 4265 what is trading plan. today fomc
AGENT    : trading | matched fomc, gold, plan, trading
POLICY   : partial          PLAN PROCEDURE IN PROMPT : yes
REFUSAL ORDER PRESENT : no  MARKER STILL A LAST RESORT: yes
```

**What is still owed, and it is the important half.** None of this has run on
the box, and Phases 1-3 do not fix the proximate failure: if the local call
raises, the request still ends. It now *says why* and says it in a sentence,
but a timeout is still a dead end. **Phase 5 — streaming, model routing by
turn shape, and one cheap local retry — is what actually resolves that**, and
it should not be designed before the tokens/sec measurement in §7 exists.

Read `docs/OPEN_ITEMS.md` AIH-13 for Phases 4-7. The audit report itself is
the artifact linked in that conversation; its findings are numbered F1-F12 and
the open items reference them.

## 6d. P0 settled by measurement (2026-09-16, later still)

The owner ran the read-only probes. **Nothing on the box was broken.** Ollama
up 7 days, qwen2.5:7b installed, database, Qdrant, embedder and n8n all OK,
paid providers DISABLED as intended. The 502 was the boot window and is gone
(`/admin/chat` returns 401, which is nginx working); `proxy_pass` is a fixed
loopback target, so there was never a stale-upstream problem.

The numbers:

```
qwen2.5:7b generation      5.35 tok/s
prompt evaluation (warm) 208.6 tok/s
cold model load             31.0 s
a real Brother request   ~2,320 input tokens -> 11.1 s before token one
```

`LOCAL_TIMEOUT_SECONDS=180` therefore allows ~900 output tokens warm, ~740
cold. `LOCAL_MAX_TOKENS` was **1024** — above both. The application was
permitting an answer length the hardware cannot produce in time, and the
blocking call threw the work away at the deadline. That is the whole failure.

Shipped as 1.5.0 (`e90082f`): stream and keep partial work, ceiling 600,
`KEEP_ALIVE` 24h. `LOCAL_TIMEOUT_SECONDS` deliberately unchanged — raising it
makes the assistant slower, not better, and collides with nginx's 180 s on the
synchronous routes.

**The trap for whoever deploys this:** the box's `.env` carries
`LOCAL_MAX_TOKENS=1024` explicitly, which overrides the new default. Edit that
line or the fix does nothing.

Lesson worth keeping: *a budget is three costs, not one* — model load, prompt
evaluation, generation — and only a measurement says which one is spending it.
"Raise the timeout" would have hidden all three.

## 7. Commands for Shyam, in order

Each block is one line at a time. Run them on the box, in
`/home/shyam/ai-helper`, and paste back what they print.

**Step 1 — take the fix, and see what the failure actually says.**

The box is checked out on `claude/exciting-hopper-uyy9gb`; the new commits are
on `claude/epic-euler-4k1gl1`, which starts from exactly that commit, so this
is a fast-forward and nothing local is lost.

```
cd /home/shyam/ai-helper
```

```
git fetch origin claude/epic-euler-4k1gl1
```

```
git checkout claude/epic-euler-4k1gl1
```

```
git log --oneline -1
```

(expect `Verify the trading mirror's field names…` or later)

```
docker compose up -d --build ai-helper
```

Then ask the same question again in `/admin/chat`:

```
Gold now 4265 what is trading plan. today fomc
```

The small grey line under the answer now begins with the reason. It will say
one of:

- `no answer: Ollama timed out after 180.0s` (or `60.0s`) → go to step 2.
- `no answer: ...connect...` / `...not running...` → go to step 3.
- an actual answer → AIH-2 is closed; record what it said.

**Step 2 — if it timed out: measure the model, do not guess at the threshold.**

```
grep LOCAL_TIMEOUT /home/shyam/ai-helper/.env
```

(empty output means the code default of 180 s is in force; a line reading 60
is the first thing to fix)

```
docker compose exec ollama ollama ps
```

(shows whether qwen2.5:7b is resident; if it is not listed, the first call
pays a cold load of several GB inside its timeout)

```
docker compose exec ollama curl -s http://localhost:11434/api/chat -d '{"model":"qwen2.5:7b","messages":[{"role":"user","content":"Write 200 words about risk management."}],"stream":false}' | python3 -c "import sys,json;d=json.load(sys.stdin);print(round(d['eval_count']/(d['eval_duration']/1e9),2),'tokens/sec')"
```

That number is the whole question. `LOCAL_MAX_TOKENS` is 1024, so a
full-length answer needs about **5.7 tokens/sec** to finish inside 180 s. Below
that, a long answer cannot complete and is discarded whole — the call is not
streamed, so 900 generated tokens are lost the same as zero. Paste the number
back before anything is changed; a threshold moved on a guess is how this
project loses a day.

**Step 3 — if Ollama was unreachable.**

```
docker compose ps
```

```
docker compose logs --tail=80 ai-helper
```

```
docker compose logs --tail=40 ollama
```

**Step 4 — AIH-3, after the local model is answering reliably.**

Not before: every retried seed costs one local model call, so a box that
cannot finish one answer cannot finish fifty. Do it in batches.

```
docker compose exec ai-helper python -m app.cli load-knowledge --retry-rejected --seed-limit 10
```

Read the `retried`, `promoted` and `rejected` counts it prints, then re-run the
same line to continue. The rejected rows are superseded, not deleted, so the
record of what the gate refused survives and an interrupted run is safe.

**Step 5 — AIH-1, whenever you want "bot status" to work.**

Make a USER key on the platform's `/api-access` page, then two lines in
`/home/shyam/ai-helper/.env`:

```
TRADING_PLATFORM_URL=https://<the platform host>
```

```
TRADING_PLATFORM_API_KEY=<the key from /api-access>
```

```
docker compose restart ai-helper
```

```
docker compose exec ai-helper python -m app.cli ask "bot status"
```

Paste the Stats line back. The field names were checked against the platform's
source this session and they match, but that is an audit, not a live read, and
AIH-5 stays open until a real payload has been through it.

## 8. Paste-ready opening prompt for the next window

```
Read /home/user/AIHELPER/CLAUDE.md, then docs/HANDOFF_BROTHER_SESSION.md,
then docs/OPEN_ITEMS.md. Branch claude/epic-euler-4k1gl1 (HEAD: git log --oneline -1),
565 tests green, version 1.4.0. The box ai.signalmesh.dev runs qwen2.5:7b with
the pack loaded; paid providers stay OFF by the owner's decision.
AIH-2 is IN PROGRESS and blocked on the box: the plan question returned no
answer at all, level 2 raised, and the architecture work (Phases 1-3, AIH-13)
is in but has NOT been run there. Phases 1-3 make the failure legible and get
the question to the trading agent; they do not stop a local timeout ending the
request -- that is Phase 5. Handoff §7 has the commands for Shyam; start by
asking him for their output, and do not move LOCAL_MAX_TOKENS or
LOCAL_TIMEOUT_SECONDS until the measured tokens/sec is in hand. Then AIH-3
(built, not yet run) and AIH-1. Findings first, small verified diffs, pytest
and ruff before every commit, commands for Shyam paste-ready one per line.
```
