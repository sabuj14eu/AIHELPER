# Brother — the personal assistant layer

AI Helper 1.0 was a generic gateway that knew nothing about anyone. Brother
is what makes it the owner's own assistant: it knows the trading system, the
platform, the brain, the v7 bot, the developer agent and the accounting
application, and it works by their laws. This document says how that is
built, how to load it, how to talk to it, and how to keep it current.

Nothing about the gateway changed to make room for it. Brother is a knowledge
pack (data), four agents (routing profiles), a bootstrap command and a chat
page. Every answer still walks the same ladder, is validated the same way, is
budget- and privacy-gated the same way, and is audited under the same actor.

## The three parts

```
knowledge/                the pack: what Brother KNOWS       (data, reloadable)
app/agents/builtin.py     the Brother agents: how Brother WORKS   (stable prompts)
/admin/chat               where you TALK to it                (dashboard, admin session)
```

**What Brother knows lives in the pack, never in a prompt.** Facts change:
a law gets locked, an open item closes, a version ships. The pack is
re-loaded; the prompts are not edited. A test guards this: the shared law
text in the prompt may not carry a number the pack should own.

**How Brother works lives in the prompts.** Findings first; the evidence law;
never infer from silence; stale is invalid, not neutral; the refusals; the
deploy ceremony; advisory only. These are the owner's working laws, which
have not changed across the repositories, and the small local model needs
them in front of it on every request.

## The knowledge pack

`knowledge/README.md` describes the format. In short: one folder per domain
(`brother`, `platform`, `brain`, `v7`, `developer`, `accounting`), eight
digests per repository (overview, laws, architecture, evidence, workflows and
tools, validated solutions, open items, glossary), plus `sources/` with
verbatim copies of each repository's governing documents stamped with the
commit they came from.

Loading goes through `DocumentIngestor`, exactly as an upload does: the file
becomes a document of the personal client in the namespace named by its
domain, chunked and indexed by the running embedder. `Document.meta` keeps
the pack path and the file digest, which is what makes a reload idempotent:
unchanged files are skipped, changed files replace their document, and
`--prune` removes documents whose file is gone. Every load writes one audit
row (`knowledge.pack_loaded`) with the counts.

### Validated solutions

Each `*validated_solutions.md` file holds blocks of the form

```
### <title>
question: <one line>
answer: <a few sentences>
evidence: <where the proof is>
```

The loader turns each block into a CANDIDATE solution with
`provider=knowledge-pack`, the repository as `model`, and the evidence
pointer on the row, then hands it to the same `PromotionPipeline` a paid
answer goes through. With a local model running they end PROMOTED, and the
exact question is then answered from memory at no cost. Without a local model
they are held at VALIDATED, which is the gate working, not a bug: nothing is
offered back as knowledge that the local model has not shown it can use. The
document text is still retrievable either way. A question already in the
store, in any status, is skipped on reload, so a rejection is never
resurrected by a reload.

## The agents

| Agent | Default task | What it adds |
|---|---|---|
| `brother` | general | The personal assistant. Knows the six projects from the pack; the shared laws. |
| `trading` | general | Reads every result through the evidence law (n, period, segment, source); Pine stays frozen; nothing dispatches. Tools narrowed to calculator, dates, documents, memory. |
| `architect` | general | Diagnoses in the developer agent's order (SYMPTOM → ROOT CAUSE → AFFECTED → WHY TESTS MISSED IT → FIX → RISKS → TEST PLAN); smallest diff, named test. |
| `social` | general | Drafts posts and threads under the publishing rules: DEMO stated, no claim without n and date, no probabilities, a changed view is a new post. Drafts only. |

All four share `BROTHER_LAWS`, appended after the base system rules (an agent
adds, never replaces). An agent can only narrow the client's tool set. The
four generic agents (`general`, `research`, `document`, `developer`) are
unchanged.

## Live connectors

Two tools let Brother talk about now instead of only about the pack. Both are
read-only, both carry `tool:live_data`, and both report source, fetch time
and age on every reading so the model quotes freshness rather than asserting
it (`app/tools/live.py`).

| Tool | Reads | Says |
|---|---|---|
| `market_news` | the ForexFactory weekly calendar, the one news source the v7 bot and the v18 brain read | the platform's three-state news risk (HIGH within 60 min of a high-impact event, ELEVATED within 240, LOW otherwise), the next events with forecast and previous, and UNKNOWN whenever the feed cannot be read, is empty, is dead, or the last good reading is older than `MARKET_NEWS_MAX_AGE_HOURS`. UNKNOWN is never LOW. |
| `trading_status` | the platform's API v1 with a user key: portfolio, stats, open trades, last signals | accounts online (heartbeat-driven), balance and equity, open trades, last signals, closed-trade stats with n and a LOW SAMPLE label. A failed section reads UNKNOWN. The key never appears in output. |

A tool may carry an **intent** matcher. A short, plain question ("news
today?", "USD news this week", "bot status", "show open trades") is answered
at level 0 by the tool itself, for free, exactly like arithmetic. A question
that reasons ("should we be careful with gold this session given the news?")
runs the tool and hands its reading to the model as fenced, untrusted evidence
alongside the pack, and the answer cites `tool:market_news` in its sources.
An agent's narrowed tool list still applies: `social` sees news but never the
trading mirror.

Configure in `.env`:

```bash
MARKET_NEWS_ENABLED=true                     # public feed; on by default
TRADING_PLATFORM_URL=https://<your platform host>
TRADING_PLATFORM_API_KEY=bb_...              # a USER key from the platform dashboard; read-only
```

What the connectors cannot do, on purpose: place, modify, cancel or dispatch
anything; switch the bot on or off; change a risk setting. The platform's API
v1 has no such endpoint (its Iron Rule 1), and AI Helper has no tool that
acts. Brother reports; you decide.

## Setting it up

```bash
# once: create the personal client, load the pack, seed the solutions
docker compose exec ai-helper python -m app.cli bootstrap-brother

# then sign in at /admin and open  /admin/chat
```

Timing matters on a CPU box. The documents load in a few minutes and are
committed first, so the chat works from that moment. Seeding the validated
solutions is slower: every solution is one local model call through the
reproduction gate, tens of seconds each, so all of them take an hour or two
on a 3B model without a GPU. Seeding commits one solution at a time and is
resumable, so you can run it in batches whenever the box is idle:

```bash
python -m app.cli bootstrap-brother --no-seed        # documents only, fast
python -m app.cli load-knowledge --seed-limit 40     # a batch; re-run to continue
nohup python -m app.cli load-knowledge > seed.log 2>&1 &   # or all of it, in the background
```

Progress is printed to stderr as `seed 12/278: promoted 11 … about 95 min left`.
A seed that is not yet promoted costs nothing: the same facts are already in
the pack documents; promotion only adds the free exact-question memory hit.

`bootstrap-brother` creates the client named by `PERSONAL_CLIENT_ID`
(default `brother`) with escalation OFF and an external ceiling of INTERNAL:
the pack describes the owner's own systems, and sending them to a paid
provider is a decision to take on purpose (`--may-escalate`, a budget, and
the deployment's own provider flags). The API key is printed once for
programmatic use; the dashboard chat does not need it.

The chat page shows, before you type, whether the pack is loaded, whether a
local model is running and whether the embedder is semantic. Without
`nomic-embed-text` the embedder is the lexical fallback: it matches wording,
not meaning, and a reworded question may miss. The page says so; install the
model and run `python -m app.cli calibrate`.

Every reply shows its route (tool, memory, local, paid), its confidence, its
cost, the sources it used and the validation notes. A reply marked UNVERIFIED
did not pass validation and is a draft, not a fact.

## Keeping it current

Two kinds of change, two procedures.

**A repository's governing documents changed** (a CLAUDE.md law, OPEN_ITEMS,
a handoff): run the sync from a checkout that has the sibling repositories
next to this one, then reload.

```bash
python scripts/sync_knowledge.py            # refreshes knowledge/sources/, stamps commit + date
python -m app.cli load-knowledge --prune    # re-ingests only what changed
python -m app.cli knowledge-status          # documents held vs. files on disk, stale and missing
```

The sync refuses any file the privacy detector classifies as RESTRICTED. It
never copies `.env`, registries or anything under `tests/audit` fixtures.

**A digest is wrong or out of date:** edit the markdown under
`knowledge/<domain>/`, keep the header, bump `verified_on`, reload. When a
digest and a source disagree the source wins; fix the digest. Digests were
written from the repositories as of 2026-09-16 and every non-obvious claim in
them names its source file; where a repository is silent they say UNKNOWN.

## What Brother cannot do, on purpose

- It has no tool that acts. It cannot run a command, read a live repository,
  deploy, post, place or modify a trade. An answer that claims to have done
  so fails validation.
- It does not know anything that is not in the pack or the conversation.
  Ask it about a value the pack does not carry and the right answer is
  UNKNOWN. If it produced a number instead, that is a defect: report it with
  the request id.
- It is not a fourth decision-maker in the trading system. The council
  decides, v7 executes within its rules, the developer agent diagnoses, the
  human releases. Brother explains and proposes.
- The generic validation limits in `docs/LIMITATIONS.md` all still apply:
  confidence is a routing signal, grounding is lexical overlap, promotion
  checks usability not truth.

## Verification

- `tests/unit/test_knowledge_pack.py` — parsing, idempotent load, per-client
  isolation, retrieval from a loaded pack, seeding through the gate (with and
  without a local model), the CLI, the agents, and the shipped pack itself
  (every file parses, no file carries a secret shape, every solutions file
  yields parseable blocks with evidence).
- `tests/integration/test_api.py::TestBrotherChat` — the chat page needs a
  session, explains a missing client, runs as the personal client with the
  default agent, keeps the conversation, refuses an unknown agent, and leaves
  a tool answer free.
- `tests/unit/test_validation.py` — the polarity check no longer rejects a
  faithful quote of a source that states one fact both positively and
  negatively (a defect found by seeding the pack; see CHANGELOG 1.1.0).
