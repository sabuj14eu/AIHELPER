# Open items — AI Helper / Brother

An item deferred in conversation is an item forgotten. If it is not here, it
does not exist. Delete an entry only when it is done and verified, and say
where the proof is. Status vocabulary: OPEN · IN PROGRESS · BLOCKED · DONE
(with proof).

## P1 — affects what the owner sees today

- **AIH-1 Trading connector not configured on the box.** `TRADING_PLATFORM_URL`
  and `TRADING_PLATFORM_API_KEY` are empty in the box's `.env`, so "bot
  status" answers "not configured". Needs a USER key from the platform's
  `/api-access` page, then `docker compose restart ai-helper`. Owner action.
  Opened 2026-09-16. OPEN.
- **AIH-2 Cause found, measured and fixed in code; not yet verified on the box.**
  The plan question returned nothing because the local call raised. The P0
  diagnosis (2026-09-16, read-only, owner ran the probes) settled why, and it
  was not a broken component — every one was healthy:

      qwen2.5:7b generation      5.35 tok/s
      prompt evaluation (warm) 208.6 tok/s
      cold model load             31.0 s
      a real request           ~2,320 input tokens -> 11.1 s before token one

  Against `LOCAL_TIMEOUT_SECONDS=180` that allows ~900 output tokens warm and
  ~740 cold. `LOCAL_MAX_TOKENS` was 1024 — above both. The app permitted an
  answer length the machine cannot produce in time, and the non-streaming call
  discarded everything when the clock ran out. Arithmetic, not a fault.

  Fixed in 1.5.0 (`e90082f`): the client streams so a partial answer survives,
  the ceiling is 600, and `KEEP_ALIVE` is 24h so the 31 s reload stops landing
  inside a request's budget.

  **Remaining, and it needs the box.** Two steps, in this order:
  1. Deploy 1.5.0 **and change `LOCAL_MAX_TOKENS=1024` to `600` in the box's
     `.env`** — the file overrides the new code default, so without this edit
     the old ceiling stays in force and nothing improves.
  2. Run one real request end to end and read the result:
     `python -m app.cli ask "In one sentence, what is the v7 bot?"` then the
     gold plan question in `/admin/chat`.
  Until step 2 returns an answer, this stays open. Opened 2026-09-16. IN PROGRESS.
- **AIH-3 48 seeded solutions were REJECTED by llama3.2:3b's reproduction
  gate** (229 promoted, 1 validated, 48 rejected on 2026-09-16 ~17:30 UTC).
  The mechanism is built: `load-knowledge --retry-rejected`, commit ff8d268,
  tests `tests/unit/test_knowledge_pack.py::TestRetryingRejectedSeeds`. It
  supersedes rather than deletes, which is what this item first proposed —
  Iron Rule 4 keeps the record of what the gate refused and why, so the
  rejection is EXPIRED with its reason and the retry earns its own status.
  **Not yet run on the box**, and it costs one local model call per seed, so
  it wants `--seed-limit` batches and it is worth doing after AIH-2 settles
  why the local model is not answering. Command in the handoff §7.
  Opened 2026-09-16. IN PROGRESS.

- **AIH-13 The architecture work: Phases 1–3 are built, Phases 4–7 are not.**
  The audit (2026-09-16) found six blocking defects. Phases 1–3 fixed five of
  them and shipped in 1.3.0, 1.3.1 and 1.4.0 — four states, prompt coherence,
  the agent router. **Phase 4** (scoped retrieval and reranking, F8) wants the
  AIH-4 evals set built first so the change is measured. **Phase 5** is now partly done: streaming and the
  budget shipped in 1.5.0, so a timeout no longer discards the answer. What
  remains of it is model routing by turn shape (the 3B for small talk and
  clarification) and one cheap local retry on a tighter prompt before giving
  up. **Phase 6** is partly done: origin
  (seeded/taught/self/paid) and self-capture of verified local answers shipped
  in 1.7.0. What remains of it is thread summarisation instead of a six-turn
  window (F12) and a clarifying-question state (F11). **Phase 7** (paid teacher) is design only and must not be built
  without an explicit decision. None of these has been run on the box. OPEN.

- **AIH-15 Web research is built and tested; no live SearXNG query has run.**
  1.9.0 ships the whole loop — egress gate, SearXNG service, trusted-source
  tiers, `self_web` origin, the typed relation, the trading record and the
  counters — against a mocked search endpoint. 740 tests pass. **Nothing has
  been observed against a real SearXNG container.** Three things are unproven
  and each would fail differently:
  1. `SEARXNG_SECRET` overriding `server.secret_key`. Documented SearXNG
     behaviour, not observed here. If it does not apply, the container logs a
     secret-key error at startup.
  2. Whether the engines behind SearXNG honour `site:`. If they do not, the
     routed query returns nothing and the run falls back to the open web —
     degraded, not broken, and visible as `tier_4` dominating
     `sources_by_tier` in `learning-report`.
  3. Whether snippets are long enough for the local model to answer from. If
     they are not, the honest outcome is a validation rejection, which the
     counters will show as `rejected_by_validation`.
  Proof needed: the 14-step run in `docs/PROOF_WEB_RESEARCH.md`, its output
  pasted back. Opened 2026-09-17. OPEN.
- **AIH-16 The twelve reasoning inputs have no live feed behind them.**
  `app/trading/plan.py` defines the order, the four statuses and the
  price-sourcing check, and the prompt tells Brother to walk it. But the
  inputs it walks come from whatever is in CONTEXT, and today that is the
  pack plus web snippets: there is **no price feed, no structure read and no
  level source**. So a real market question will honestly answer WAIT or
  UNKNOWN naming the missing inputs — correct behaviour, and not yet a
  trading assistant. Closing this needs AIH-1 (the platform mirror) and
  AIH-6 (the outlook board), which are the two real inputs that exist.
  Opened 2026-09-17. OPEN.

- **AIH-17 Market-data mirror: inspected, not built.**
  `docs/MARKET_DATA_INSPECTION.md` (2026-09-17, read-only) found that the
  platform already holds one disciplined market-data truth — candles, the
  level engine, per-timeframe structure and ATR, freshness on `bar_clock-v1`
  — and that **no API key can read any of it**: `/chart/candles.json` and
  `/chart/levels.json` authenticate with a browser session, and the
  API-key surface is `/me /portfolio /stats /trades /signals` only.
  AIH-1 and AIH-6 are blocked on four read-only GETs in Sniper-System
  (`/api/v1/market/{candles,snapshot,desk}` and `/api/v1/outlook`), approved
  in principle but **not built** — the owner scoped that turn to inspection
  and review. Three NOT VERIFIED items remain, each with the command that
  settles it, in the report's last section. Opened 2026-09-17. OPEN.
- **AIH-18 Two swing definitions inside SignalMesh — decided for Brother,
  still true of SignalMesh.** Pine uses `ta.pivothigh(high, 5, 5)`; the
  platform's `scanner.structure_state` uses `swing = 3`. They disagree about
  which bars are swings, and therefore about structure, range edges and
  equilibrium, on the same chart at the same moment.
  **Owner's decision 2026-09-17: AI Helper's canonical read is Pine's 5, and
  `scanner.py` is not modified.** Recorded as row C1 in
  `docs/METHODOLOGY_MAPPING.md`. That settles what Brother does; it does not
  settle the platform's internal disagreement, which is SignalMesh's to
  decide and is left untouched here. OPEN (for SignalMesh).
- **AIH-19 Pine and the platform also disagree about ATR.** Found while
  writing the mapping: Pine's `ta.atr(14)` is **Wilder's RMA smoothing**;
  the platform's `scanner.atr` is a **14-period simple mean** of true range.
  The same bars give two different ATRs, and ATR scales almost everything —
  Pine's impulse thresholds (1.2/1.8), its zone tolerance, its fake-breakout
  test, and the platform's SL distance and every "distance in ATR" reading.
  Brother follows Pine for Pine-defined concepts and quotes the platform's
  own ATR whenever it quotes a platform number (row C2). Not introduced here
  and not touched here. Opened 2026-09-17. OPEN (for SignalMesh).

## P2 — quality and robustness

- **AIH-4 Retrieval quality for pack questions is unmeasured.** The semantic
  embedder is live (`nomic-embed-text`), `calibrate` has not been run on the
  box since the pack loaded. Run `python -m app.cli calibrate`; expect exit 0.
  Then a fixed question set (10–20 questions about the six repos with
  expected sources) run through `python -m app.cli ask` is the evals harness
  the 1.0 handover named as the biggest gap. OPEN.
- **AIH-5 The trading mirror's field names are verified; a live read is not.**
  Every key `trading_status` renders was checked against Sniper-System
  `3257184` (`app/routers/api_v1.py`, `app/services/analytics.py`). All match;
  nothing was renamed. Two rendering defects found and fixed while checking
  (commit 7198c5c): `win_rate` is a percentage and now carries its `%`, and a
  present-but-null statistic now reads `UNKNOWN` instead of vanishing —
  `profit_factor` is null exactly when there were no losing trades, so
  dropping it turned a fact into a silence. Proof:
  `tests/unit/test_live_tools.py::TestTradingStatusTool::test_the_win_rate_carries_its_unit`
  and `::test_a_null_statistic_reads_unknown_rather_than_vanishing`.
  **Still open for the other half:** this is an audit against source, not a
  live read. No real payload has been through the connector because it is
  unconfigured (AIH-1). Confirm against a real response once AIH-1 is done.
  IN PROGRESS.

- **AIH-12 `trading_status` does not render `expectancy` or `avg_rr`.** Both
  are in the platform's `core_stats` and both are more informative than the
  raw totals already shown. Not a defect — nothing is wrong with the line as
  it stands — so it was left alone rather than widened while fixing AIH-5.
  Opened 2026-09-16. OPEN.
- **AIH-6 Outlook board is not readable.** The plan recipe says "restate
  the posted outlook" but no connector reads the platform's outlook board
  (its API v1 has no outlook endpoint; the desk page is session-authed).
  Either the platform adds `GET /api/v1/outlooks` (read-only, Iron Rule 1
  compatible) or Brother keeps saying ABSENT. Platform-side change; raise
  it there. OPEN.
- **AIH-7 Digests were written 2026-09-16 and have no refresh procedure
  beyond hand editing.** `sources/` re-syncs mechanically; the eight digests
  per repo do not. When a repo's laws change, a session must edit the
  digest and bump `verified_on`. Consider a `knowledge-status --stale-digests`
  that compares each digest's `verified_on` to the source repo's HEAD date. OPEN.
- **AIH-8 Open WebUI on port 3000 (chat.signalmesh.dev) bypasses Brother.**
  It talks to Ollama directly: no pack, no laws, no live data, and it
  showed "Arena Model: Cannot choose from an empty sequence" before models
  were pulled. Either point people to `/admin/chat` only, or remove the
  service from compose for this deployment. Owner decision. OPEN.

## P3 — deferred by design

- **AIH-9 Streaming answers.** Would need validation on a partial answer;
  the queued-job chat makes the wait tolerable. Deferred (1.0 backlog). OPEN.
- **AIH-10 Rate limiter and job queue are per process.** One worker only.
  Deferred (1.0 LIMITATIONS). OPEN.
- **AIH-11 Production gate from the 1.0 audit.** `HANDOVER_TO_FABLE.md` §3:
  the real-model calibration and the 50–100 real-question run were never
  done. The box now has real models, so this is runnable. Same as AIH-4. OPEN.

## Done this session (proof)

- Budget sized from a measurement at realistic prompt size; streaming keeps partial work → `tests/integration/test_failures.py::TestOllamaClientFailures`, commits e90082f, 89c18a7, b6e30a8.
- Seeded vs taught vs self vs paid, and Brother keeps its own verified answers → `tests/unit/test_learning_origin.py`, commit 196e79e.
- Teach refuses a fragment, a shrug or a loop → `TestTeachRefusesWhatIsNotAnAnswer`, same commit.

- **AIH-14 ~~Confirming a self-captured candidate has no one-click path.~~
  WRONG WHEN WRITTEN — it always had one.** `/admin/solutions/{id}/promote`
  has existed since 1.0, runs the full `PromotionPipeline` and writes an audit
  row; `reject` likewise. The real gap was narrower: the page listed
  `provider` but not **origin**, so a self-captured row waiting for the owner
  looked exactly like one of the 229 seeds, and there was no way to filter to
  "what is waiting for me". Fixed in 1.7.1: origin column, origin filter, and
  the button reads *Confirm* rather than *Promote* on a `self` row, because
  the gate cannot judge that one and the owner is being asked to.
  DONE — `tests/integration/test_api.py::TestBrotherChat` (the review-queue
  block), commit below. Proof: filter origin=self, status=CANDIDATE.

- Four answer states; "lacks evidence" is no longer scored as a refusal → `tests/integration/test_failures.py::TestTheFourStates`, `tests/unit/test_validation.py::TestOutputChecks::test_lacking_evidence_is_not_a_refusal`, commit d6a91f5.
- The system prompt stops ordering a refusal it elsewhere forbids → `TestBrotherAgents::test_the_brother_agents_do_not_carry_the_unconditional_refusal_order`, commit ce1fa76.
- Deterministic agent router; the gold question reaches the trading agent → `tests/unit/test_agent_router.py` (24-message labelled set), commit 5acbdec.
- Per-message task classification restored in the chat → same commit.

- A failed request names its cause → `tests/integration/test_failures.py::TestLocalModelDown::test_the_reason_there_is_no_answer_survives_the_escalation_blocked_note`, commit 443e8a5.
- `load-knowledge --retry-rejected` → `tests/unit/test_knowledge_pack.py::TestRetryingRejectedSeeds`, commit ff8d268.
- Trading mirror field names verified against the platform's source → commit 7198c5c (rendering fixes have tests; the live read is still owed, AIH-5).

- Login redirect for browsers → `tests/integration/test_api.py::TestBrotherChat::test_the_page_needs_a_session`, commit 7e989e7.
- Pack shipped in the image → `tests/unit/test_container_build.py::TestKnowledgePackShipsInTheImage`, commit 04df5f0.
- Resumable seeding → `TestSeeding::test_seeding_is_resumable_in_batches_with_progress`, commit 7235386.
- Chat independent of proxy timeout → `TestBrotherChat.ask_and_wait`, commit 9a5d2fe; observed live 2026-09-16 (an answer arrived through nginx after the change).
- Small talk and the loose marker → commit 51b5a32.
- Teaching through the gate → `tests/unit/test_teaching.py`, commit 952255d.
