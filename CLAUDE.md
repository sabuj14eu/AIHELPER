# CLAUDE.md — AI Helper / Brother constitution

Read this before touching anything. This repository is **AI Helper**, the
self-hosted local-first AI gateway, and **Brother**, the personal assistant
layer on top of it that knows Shyam's other projects (Sniper-System,
brother-brain-v2, brother_sniper_v7, brother-developer, Accounting-) from a
knowledge pack. It runs at ai.signalmesh.dev on the Contabo box next to the
v18 brain. It observes and advises; it never trades, deploys, posts or acts.

## WHAT AI HELPER IS (owner's position, 2026-09-17)
**AI Helper is not a second trading bot.** It is a read-only market-data
consumer and a reasoning and explanation layer. **SignalMesh remains the
trading authority and the executor.** Brother reads what SignalMesh already
decided and already measured, reasons about it, explains it and learns from
it. It never places, modifies, routes, cancels or dispatches anything, and it
never becomes a competing second opinion beside the desk.
Where a concept exists in SignalMesh, Brother mirrors it rather than
inventing its own — `docs/METHODOLOGY_MAPPING.md` is the contract, and every
row that reads DIFFERENT is declared there and labelled wherever it shows.

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
- `app/agents/builtin.py` generic agents + the four Brother agents,
  `BROTHER_LAWS`, `TRADING_PLAN_PROCEDURE` and `TRADING_RESEARCH_PROCEDURE`
  (rendered from `app.trading.plan.REASONING_STEPS`); `router.py` picks the
  specialist from the message.
- `app/validation/states.py` the four answer states.
- `app/knowledge/pack.py` pack loader, seeding, `secret_probe`.
- `app/learning/` capture, promotion (the gate), `teaching.py`,
  `origin.py` (seeded / taught / self / self_web / paid), `conflicts.py`
  (NEW / DUPLICATE / UPDATE / CONTRADICTION before a candidate is written),
  `research.py` (the web-research job), `sources.py` (the trusted-source
  list loader), `report.py` (the loop in numbers).
- `app/trading/` `plan.py` (the twelve-step order, the four statuses,
  `unsourced_prices`) and `knowledge.py` (source fact vs interpretation,
  and the n=1 rule). It reasons; it never trades. Any market concept it
  computes must appear in `docs/METHODOLOGY_MAPPING.md` first.
- `docs/MARKET_DATA_INSPECTION.md` where the market data is, what is
  VERIFIED / NOT VERIFIED / MISSING, and what AIH-1 must expose.
- `docs/METHODOLOGY_MAPPING.md` SignalMesh → AI Helper, concept by concept,
  SAME or DIFFERENT with the reason. The contract for `app/trading/`.
- `app/market/mirror.py` the read-only market mirror: four GETs on the
  platform, named failure states, and `usable` only at LIVE. It imports
  nothing from the research side — a test reads the import graph, because
  a web snippet must have no path to a price field.
- `app/api/routes/market.py` those four as AI Helper's own read-only GETs.
  `docs/MARKET_MIRROR_API.md` is the contract for both halves.
- `app/tools/egress.py` the one gate that lets a request reach the internet.
- `config/trusted_sources.yaml` domains, tiers, routing and the learning
  floor. DATA: adding a source never touches `app/`.
- `app/api/routes/admin.py` dashboard incl. `/admin/chat` (queued job +
  poll), `/admin/chat/teach`, `/admin/chat/ask-now`,
  `/admin/chat/research` (queued; never awaited).
- `app/cli.py` bootstrap-brother, load-knowledge, knowledge-status, ask,
  teach, research, learning-report, calibrate, expire.
- `knowledge/` the pack (see its README); `knowledge/sources/` verbatim
  copies stamped with commit and date.
- `scripts/` setup, sync_knowledge, nginx_add_timeouts, backup, health.
- `tests/` 798 tests; conftest disables the live connectors so no test
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
- **A diagnostic guarded by "only if we have nothing else to say" says
  nothing, in the case that matters.** `_degraded` recorded why level 2
  produced no answer only `if not base.notes` -- and with paid providers
  off, a note is always already there ("escalation blocked: ..."), so the
  cause was suppressed by the owner's own configuration. A failed request
  states its cause unconditionally, first.
- **`assert response.notes` is not a test.** It asserts that something was
  said, not that anything said why, and that is how the defect above shipped.
  Assert the content of the message a human will read.
- **Absence is not silence.** A statistic the platform sends as null means
  something specific (`profit_factor` is null when there were no losing
  trades); dropping the key turns a fact into "not reported". Render it
  UNKNOWN rather than guessing which it was -- the Freshness Law's
  MISSING NEWS rule, applied to a mirror.

## WHAT THE ARCHITECTURE AUDIT CHANGED (2026-09-16, Phases 1-3)
The owner asked why a plan question returned nothing. The answer was two
failures, and the second outlived the first. These are now laws.
- **A turn is one of four things, and only one is a fault.** VERIFIED ·
  USEFUL · INSUFFICIENT · FAILED (`app/validation/states.py`). "The
  evidence is not available" is a successful outcome and must never render
  as a failure. Validation's boolean is unchanged and still gates
  escalation and promotion; the states decide only what the reader sees.
- **A report about the evidence is not a refusal.** "I don't have enough
  information" is what the laws *require*; scoring it as a refusal punished
  the assistant for obeying its own constitution. Refusal and
  lack-of-evidence are separate findings.
- **One system message may not carry two incompatible orders.** BASE_SYSTEM
  ordered INSUFFICIENT_CONTEXT unconditionally while BROTHER_LAWS forbade
  refusing a plan question. A small model follows the blunt rule that came
  first. The rule is now `context_policy` on the agent: strict is the
  default, the Brother agents are partial.
- **Iron Rule 5 draws its line at facts, not at method.** A number, level or
  threshold belongs in the pack and is reloaded. The *order Brother thinks
  in* is the way of working and belongs in the prompt — which is why the
  plan procedure moved there. A test enforces this across every Brother
  prompt.
- **Routing is a control decision, so it is deterministic** (Iron Rule 2).
  `app/agents/router.py` is regex and a test asserts it cannot reach a
  provider. Being wrong must stay cheap: the fallback is `brother`, which
  carries the client's whole tool set — never "no agent", never a refusal.
  Accuracy is measured against `tests/unit/test_agent_router.py::LABELLED`;
  grow that set when it gets something wrong, do not argue with it.
- **An explicit choice is never second-guessed.** Only `auto` routes.
- **A classification at confidence 1.0 silences everything below it.** An
  agent's `default_task_type` was passed as `declared` and disabled
  per-message classification entirely. Anything that short-circuits a
  classifier deserves the same suspicion.

## WHAT THE BUDGET AND THE LEARNING WORK CHANGED (2026-09-16, later)
- **A budget is three costs, not one.** Model load, prompt evaluation,
  generation. Measured on the box: load 31 s, prompt eval **19.8 tok/s**,
  generation 5.35 tok/s. A real request spends 86-117 s *reading the prompt*
  before it writes anything, which is why the first repaired answer arrived
  as the two words "1. The". `LOCAL_CONTEXT_CHARS` is the biggest lever:
  every 1,000 characters of evidence costs ~13 s before the model speaks.
- **Never extrapolate a rate from a sample that small.** The first
  prompt-eval figure came from a 38-token prompt with a 0.18 s duration and
  was wrong by 10x. The Evidence Law applies to our own measurements, not
  only to trading results. Measure at the size you actually run at.
- **"Timed out" must say which timeout.** Ollama sends no frames while it
  loads and reads; the first frame is the first *generated* token. "No text
  after 180 s" covered both "generation never started" and "the model
  produced nothing", and those have opposite fixes.
- **A partial answer is worth more than none**, and must never be shown as
  complete. The client streams, keeps what was generated, and marks it
  `finish_reason="timeout"`, which the validator reads as truncation.
- **Authoring is not learning.** Status says how far a solution got; origin
  (`app/learning/origin.py`) says where it started. 229 PROMOTED pack seeds
  are 229 things a session wrote, and presenting them as learning made the
  system look like it improved with use. Show every origin, including the
  zeros -- `self: 0` was the number that needed saying.
- **A local answer passes its own reproduction gate by construction.** So
  Brother's own verified answers are kept as CANDIDATE and never promoted
  automatically; the owner confirms. Anything else is a rubber stamp that
  serves its own mistakes back for `SOLUTION_TTL_DAYS`.
- **The gates check usability, not truth, so what they cannot catch is
  checked before the write.** Teaching refuses a fragment, refuses Brother's
  own "I don't have enough information" (a gap to fill, not to teach away)
  and refuses a degenerate loop. It never judges whether an answer is right:
  that is the owner's call and the point of the form.

- **A duplicate is a reason not to store; a conflict is not.** When a new
  answer disagrees with something already promoted, one of the two is stale
  and the system has just found out. Dropping it loses the discovery; storing
  it quietly leaves two answers that cannot both be true. Store it, mark it,
  and put it in front of the owner. `app/learning/conflicts.py`.
- **Search by the answer, not only the question.** A stale solution that
  contradicts a new one may be filed under a question nothing like it, which
  is exactly what a question-based search cannot see.
- **A quality gate fails open; a safety gate fails closed.** A broken vector
  store loses the duplicate check, not the lesson — a missed check costs a
  duplicate row, refusing to capture costs what was being learned. Know which
  kind each gate is before choosing its failure mode.

- **A heuristic verdict may label an answer; it may not delete one.** The
  withholding vetoes are objective findings — unsafe, looping, wrong format,
  disagrees with a calculation. `contradicts_context` is a heuristic over
  shared words and a negation, and while it sat in that set it deleted the
  first complete plan answer the system ever produced. Suppression is for
  things that are certainly wrong, not things that are probably wrong.

- **Objective findings may veto; inferences may not.** A figure absent from
  the source is objective. A polarity clash over shared content words is an
  inference — it cannot see the subject of a sentence, so "MISSING NEWS is not
  low risk" reads as contradicting "news risk is LOW" when both are true. It
  costs confidence and names itself; it does not fail an answer. The same
  signal may still raise a review flag in `conflicts.py`, because a flag is
  not a sentence.

## WHAT WEB RESEARCH CHANGED (2026-09-17, v1.9.0)
Brother can now look something up. Every law below exists because looking
something up is not the same as believing it.
- **A web search is an egress path, so it uses the egress gate.** Not a
  second privacy policy — the same `may_leave_system` the paid path uses,
  because two policies that mean the same thing drift apart and then
  disagree. It had been called from exactly one place since 1.0, so the
  RESTRICTED rule would never have been consulted when Brother typed a
  question into a search box. Granting is explicit: a client's
  `allowed_tools` must NAME a network tool. **Inheriting every tool is not
  the same as choosing the internet.**
- **A tier says who wrote it, not whether it is true.** It buys order (the
  publisher is asked before the open web, and evidence is sorted
  best-first because the context window truncates) and provenance (domain,
  tier, trust, query and time travel with the candidate). It buys no
  shortcut: a tier 1 page is validated, becomes a CANDIDATE and waits for a
  person. It does buy a floor — general-web evidence alone is read and
  reported, never learned from.
- **The source list is data.** `app/learning/sources.py` names no domain and
  a test enforces it. Adding a source is an edit to a YAML file and a test.
- **Over-calling UPDATE costs a review; over-calling DUPLICATE costs a fact.**
  So the relation ladder runs CONTRADICTION > UPDATE > DUPLICATE > NEW, and
  DUPLICATE — the only verdict that discards anything — is the narrowest.
  Neither UPDATE nor CONTRADICTION ever edits the row it relates to.
- **Free work is not paid work.** `self_web` costs nothing and reaches no
  API. A spend figure that counts it is a figure nobody can act on. Cost and
  trust are separate questions: `is_paid` and `is_external_evidence`.
- **A guard that reads prose instead of behaviour cries wolf and gets
  deleted.** Two shipped in one hour here: one tripping on its own
  docstring, one on `staticmethod` containing "cme". Assert on parsed data
  and the import graph, never on the text of the file.
- **File order is load-bearing in a rule list.** "PCE inflation" routed to
  BLS because the general inflation rule was tried before the BEA one. A
  test now holds the order that makes the specific rule win.

## HOW BROTHER REASONS ABOUT A MARKET (2026-09-17, v1.9.0)
`app/trading/`. The discipline is mostly refusals.
- **A setup is never manufactured because an entry was asked for.** READY ·
  WAIT · NO_TRADE · UNKNOWN, and none of them is a failure. An assistant
  that must always produce a number will produce one on the days the
  evidence is thinnest — which are the days it costs money. Missing or
  conflicting core inputs is UNKNOWN; inputs without a location is WAIT.
- **Prices are quoted, never generated.** Every price in a plan must appear
  in the evidence. Objective, so it may veto: a plan with an invented price
  is not a degraded plan, it is a different object.
- **A fact and a reading of it are two objects.** Merged into one sentence,
  the interpretation inherits the fact's citation and becomes a claim that
  looks sourced and is not. Stored apart, rendered with the seam showing,
  and split STRUCTURALLY (published text is evidence, the model's own words
  are interpretation) so no model has to judge which half is which.
- **One occurrence is not a rule.** "Gold always goes up after FOMC" seen
  once is n=1. The observation is kept with its n; the rule is not made. The
  refusal is about the claim's scope, never about the evidence.
- **Confidence is evidence completeness, not certainty.** It is the share of
  the twelve inputs that were present, less a penalty for disagreement.
- **The order lives in one place.** `REASONING_STEPS` renders the prompt, so
  the order Brother is told to think in and the order a record reports
  cannot drift. The order is method (prompt); every number is a fact (pack).

## THE MARKET MIRROR (2026-09-17, v1.10.0)
- **SearXNG is for research; the mirror is for price.** A web article
  saying "gold is around 4270" is not a trading price. The separation is
  enforced, not described: `web_search` carries `tool:network` and goes
  through the egress gate; the mirror reads a fixed operator-configured
  platform URL and imports nothing from the research side, which a test
  checks by reading the import graph.
- **STALE is not a degraded yes.** `usable` is true only at LIVE. The
  platform's own rule is that a stale feed produces NO levels, and a
  mirror that softened that would be the first place the Freshness Law
  leaked. Absent freshness is UNKNOWN, never assumed fine — guessing
  fresh is the dangerous guess.
- **A failure is a word, not a sentence.** NOT_CONFIGURED · UNREACHABLE ·
  REFUSED, because "the key is wrong" and "the platform is down" have
  opposite fixes. `data` is null on any of them, never `{}`.
- **A caller names an endpoint, never a URL.** Nothing a caller passes can
  steer a read at another host or another route.
- **An ISO timestamp with no offset is read as LOCAL time.** The candle
  column is aware in PostgreSQL and naive in SQLite, so the platform makes
  every stamp aware on the way out rather than trusting the driver. A
  series shifted by the reader's timezone is the clock incident again:
  not degraded data, a second parallel series.
- **`age_min` is null when there is no bar, never 0.** Zero reads as
  fresh, and there is nothing to be fresh.
- **Whose number is this?** The platform's snapshot declares its swing=3
  and simple-mean ATR, and says Pine uses 5 and Wilder. A consumer
  mirroring Pine's method on the platform's data must not relabel them.

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
