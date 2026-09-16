---
title: Sniper-System platform laws and locked decisions
domain: platform
repo: sabuj14eu/Sniper-System
sources: CLAUDE.md, docs/V7_SELF_DEPENDENCE_PLAN.md, docs/HANDOFF_PLATFORM_SESSION.md, docs/OPEN_ITEMS.md, docs/HANDOVER_V7_DESK.md, docs/CHANGELOG.md, pine/V18.11_RELEASE_NOTES.md, pine/PINE_v18.9_SPEC.md, app/services/factory.py, app/services/modellab.py, agents/mt5_reporter/mt5_reporter.py
verified_on: 2026-09-16
classification: INTERNAL
---

# Sniper-System platform — iron rules and locked decisions

Every rule below is quoted from CLAUDE.md or the named document, with the incident or rationale the repo records for it. "Locked" means an explicit user (Shyam) decision recorded with a date; a session may not renegotiate it on its own.

## The six IRON RULES of the Sniper-System platform (CLAUDE.md)

**Iron Rule 1 — read-only mirror, never dispatch.** "NOTHING here dispatches signals. The platform receives a read-only mirror of signals/decisions from the v18 brain for display, journaling and analytics. No code path in this repo may send an order, a dispatch, or any instruction to an executor. The CMS manages accounts/routing metadata, NEVER signals." Rationale (bot-box CLAUDE.md, mirrored here): the last bypass, an MT5 scanner, lost 60R. Enforced by guard tests, e.g. the mgmt engine has no network client (CHANGELOG 4.29), the chart path has no `db.add` (4.28), `position_state` imports nothing (5.19).

**Iron Rule 2 — payload contract is APPEND-ONLY.** "The signal mirror stores the raw payload verbatim (`Signal.raw_payload`) and never renames/removes fields the brain sends (system, signal, direction, signal_id, symbol, tf, entry, sl, tp, tp1, tp2, rr, grade). Unknown keys pass through." Rationale: Pine, the brain, v7 and the platform all read the same JSON; a rename breaks a reader somewhere. The rule paid for itself in v4.18, when 202 backfilled v7 trades arrived with a status word the platform did not know — the raw payload still held it and a startup repair fixed the column without a re-send. The `payload_contract` watcher (v5.00) type-checks the last 50 mirrored payloads against it.

**Iron Rule 3 — never widen risk silently.** "Risk limits, lot sizes and emergency-stop state are explicit user/admin decisions, and every change is written to the audit log with its actor." Consequences recorded: the DD-guard numbers (bot-side EquityGuard at 0.99) wait for Shyam to NAME them (OPEN_ITEMS, 2026-08-31); NVDA+US100 as one exposure (PLAT-EXPOSURE-1) ships only as his logged decision; the freshness gate anchor was not moved in v5.17 because that would widen every window by a bar.

**Iron Rule 4 — secrets never committed or printed.** "Secrets (.env, tokens, MT5 passwords, API keys) are never committed and never printed in logs, templates, or chat. Stored credentials are encrypted at rest; API keys and OTPs are stored hashed." Incidents: a reporter API key pasted in chat (SERVICE_AUDIT 2026-08-08 and OPEN_ITEMS PLAT-SEC-1); a Brevo key pasted into a chat window during the v4.92 email fix, which produced `/admin/email` in v4.93 so no secret is typed in a terminal again.

**Iron Rule 5 — health endpoints lie; only tickets/journal tell the truth.** "Status displays must be driven by reported heartbeats with staleness windows, never by 'the endpoint returned 200'." Rationale (bot-box CLAUDE.md): an executor served 200s for 6 days while placing nothing. Applied in v5.06: a fresh heartbeat reporting `mt5_running=false` is RED, not GREEN.

**Iron Rule 6 — every schema change ships with a migration note in docs/CHANGELOG.md.** "Deploys follow: backup -> migrate -> restart -> verify logs." Corollary learned in v5.00 and repeated in v5.07: "code ahead of its migration is DOWN, not degraded" — SQLAlchemy selects every mapped column, so a missing column 500s every page that touches the model.

## QUANT LAB LAW (locked 2026-08-08, explicit user decision)

CLAUDE.md: the Strategy Factory / Model Lab objective is "find statistically robust, reproducible, out-of-sample edges, with the ability to conclude that no robust edge exists. 'NO ROBUST STRATEGY' is a first-class, successful outcome. Never build or accept 'find the most profitable strategy'."

Corollaries enforced in code (CLAUDE.md, app/services/factory.py, app/services/modellab.py):
- Variant families are predefined and hard-capped (24); no free-form dredging.
- Search touches only the first 80% of a dataset; the newest 20% is the FINAL HOLDOUT, spent exactly once per experiment and never re-armed.
- Verdicts come from OUT-OF-SAMPLE segments; raw return never ranks.
- Selection bias ("best of N") is disclosed on every report.
- Research uses CLOSED candles only; the 200-candle floor never lowers.
- Evidence Law: n<20 is luck, ~100 to judge — labels say so.
- Model Lab artifacts can never emit a signal or reach an executor.

Known breach, recorded not hidden: PLAT-HOLDOUT-1 (OPEN_ITEMS, opened 2026-08-31 by the bot-session audit #7) — the Model Lab holdout re-arms on every retrain. It waits for its own release because the fix must define what counts as a NEW experiment.

## FRESHNESS LAW (locked 2026-08-11, explicit user decision)

CLAUDE.md: "STALE DATA MUST NEVER BECOME A VALID POSITIVE SIGNAL."
- STALE BIAS ≠ neutral — it is INVALID and unused (gate: `BIAS_MAX_AGE_H` = 24 market-clock hours, enforced in `scanner.build_snapshot` so every consumer inherits it).
- MISSING NEWS ≠ low risk — it is UNKNOWN (`news_risk` returns UNKNOWN on an empty calendar; UNKNOWN fails "news ≤ X" conditions by default). v4.72 extended this to a DEAD calendar (newest event older than 72h with nothing upcoming is UNKNOWN, never LOW).
- STALE PLAN ≠ ready (12h signal expiry, `SIGNAL_FRESH_H`) · STALE SERVER ≠ healthy (heartbeats only) · STALE SIGNAL ≠ current opportunity · UNKNOWN ≠ any direction.
- "Every displayed number needs: source → timestamp → freshness → authority → meaning → expiry."

Origin (CHANGELOG 2.2.1): a 16-day-old "81% bullish" bias was gating trades. The law was written as Priority 0 hardening and then reached the display layer in 2.4.1. Corollary from v4.55: a spread-only push can never refresh the bias clock. Corollary from v4.71: "do not backfill an old opinion with a new timestamp" — a fresh clock on an old view is the one lie the Freshness Law cannot catch.

## A CLOCK NEEDS TWO WITNESSES (locked 2026-08-21, after the incident)

CLAUDE.md, corollary of the Freshness Law aimed at ingested time. On 2026-08-20 23:50 UTC the reporter read ONE tick — gold's, during the metals rollover break — and inferred the broker offset from it. "A single tick cannot separate 'the clock is +3h' from 'this quote is an hour old': both look identical." It concluded +2h (truth +3h) and every bar pushed for 25 minutes was stamped an hour late.

The rules:
- "Timestamps are inferred from ≥2 fresh, independent witnesses, at least one of which trades 24/7, or not inferred at all. Staleness is measured by comparing witnesses to each other, never assumed."
- "A wrong clock is not degraded data, it is corrupted data." The candle key is (symbol, tf, ts), so a shifted bar creates a second parallel series, and on fine timeframes overwrites a different bar's prices. The agent REFUSES to run rather than guess (never "Assuming 0").
- "A push is not 'delivered' until the receiver says what it stored." Both ends now report and compare counts (`upsert_candles_report`).
- "A SCALAR OFFSET CANNOT CONVERT A MULTI-YEAR SERIES." The broker runs EET/EEST and MT5 returns server wall-clock, so the seasonal hour is inside the data; convert PER BAR through the broker's DST calendar (reporter v1.5.0, `BB_BROKER_TZ` = Europe/Athens).
- "INTERNAL CONSISTENCY IS NOT CORRECTNESS": a uniformly-wrong series passes every self-consistency test. A correct series has TWO daily grids (21:00 summer / 22:00 winter), so "the tidy one is the suspect".
Code: `agents/mt5_reporter.detect_broker_offset`, `webhooks.upsert_candles_report`, `services/candle_audit.season_check`.

## EVIDENCE AUTHORITY (locked 2026-08-20, both sides agreed)

CLAUDE.md, two rules "earned the day the first real finding appeared":
- "PAPER LANES ARE A HYPOTHESIS GENERATOR, NEVER A GATE AUTHORITY." The platform's own lanes place limits and record what happened; that population is not v7's. "A lane statistic may PROPOSE a rule change; only v7's own filled trades may justify one. Two independent populations agreeing is the standard. One of them alone is a note."
- "A SPLIT SAMPLE IS A SMALLER SAMPLE." Before a bucketed result is read as a finding, cut it by side and by with-trend vs against-bias and check n IN EACH CELL. "620 pooled can be 12 in the cell that answers the question." Under the floor the honest verdict is CANNOT SEPARATE, a first-class outcome exactly as "NO ROBUST STRATEGY" is. See `desk.distance_confounders` (v4.37).

## PINE IS THE SENSOR AND IT STAYS FROZEN (locked 2026-08-20, bot box)

CLAUDE.md: "Do NOT propose moving intelligence into Pine." Every Pine save requires deleting and recreating every alert, so the script that fires is frozen at alert-creation time; a Pine that changes weekly means a ceremony every week and history that is no longer comparable. "A sensor that keeps changing measures nothing. Pine emits; the layer that WATCHES it gets smarter. New intelligence belongs in the evidence tables and their read models, never in the instrument."

Pine iron rules mirrored in the `pine/` workspace: alert-payload contract is APPEND-only; compiled-token ceiling ~80K (v18.8 compiled at ~79,950 of 80,000 — comments free, operations cost); "evidence before Pine" — new strategy organs ship DARK (`FEATURE_*` flags, default-off inputs) until the journal validates them; the council/bot is the single risk authority — Pine never blocks signals on quota/PnL (explicit user decision 2026-07-30, v18.11 E3).

## V7 SELF-DEPENDENCE MASTER PLAN (locked 2026-08-14)

docs/V7_SELF_DEPENDENCE_PLAN.md, binding. Five organs: the deterministic Trade Desk is the SENSOR, the evidence tables are the MEMORY, a statistics/ML layer (Phases 2–3, under Model Lab laws) is the PATTERN RECOGNITION, the risk engine stays the GUARDIAN, and v7 on the bot box remains the DECISION MAKER. Five phases with hard exit gates, none skippable:
1. COLLECT — calculate → record → resolve; exit: dataset fields complete, ≥200 resolved lane candidates. (MET: 412 resolved at handover, per docs/HANDOVER_V7_DESK.md.)
2. ANALYZE — statistics only, no ML; exit: one condition cell reaches n≥100.
3. TRAIN — only P(fill), P(TP1 before SL | filled), E[R]; never price prediction; "NO ROBUST MODEL" is success.
4. SHADOW — learned TRADE/WAIT recorded beside v7; exit ≥100 comparable rounds and ladder separation (`MIN_COMPARABLE_N = 100`).
5. CONTROLLED DEPLOYMENT — bot box, demo first, risk engine above everything, automatic fallback.

Standing rules (§5): frozen engines (auto-v1, scalp/session/swing-v1, `_resolve`) never change in place — new behavior is a NEW versioned engine, locked by `test_the_original_auto_v1_maths_is_frozen`; thresholds come from recorded tables, never advisors' round numbers; append-only columns; "No LLM in the decision path, ever"; recorded market state is history, never rewritten (v4.2 user decision: `market_snapshots` rows are frozen at insert, `SnapshotImmutable` guard). §7: no new plugins for Phases 1–2; Phase 3 may add scikit-learn inside the Model Lab only.

## The v7 Desk rule (docs/HANDOVER_V7_DESK.md, 2026-08-17)

Shyam's words: "no need new rules or code only take data." The `/v7` page is a read-only mirror of v7's own state: it must not compute a v7 entry/SL/TP/grade the bot did not send, re-derive or "correct" anything, add a gate or score, or reach an executor. A number not in v7's payload renders UNKNOWN. The Trade Desk's lanes are the platform's own engines and stay separate from v7's numbers.

## OTHER LOCKED DECISIONS recorded in the repo

- **Canonical SignalOpportunity (v3.0.1, user architecture decision):** BSv18 and BSv7 both receive the same Pine signal — two Signal rows with one `pine_signal_id` are ONE opportunity with two bot responses, never two independent research samples. Pine originates → v18/v7 respond → AI is the only genuinely independent lane.
- **AI budget (v4.5, user decision "10 dollar week ok because this is demo"):** `BB_AI_WEEKLY_BUDGET_USD` = 10; every call metered in `ai_calls`; the AI is research-only through the single door `services/ai_ledger.call_messages`.
- **Bridge key provisions itself (v4.23, user decision "take key from system automatic. if i put then always mistake").**
- **C10 — US10Y means the YIELD, permanently (2026-09-02).** Pine's `yield_dir` is the yield; the broker's UST10Y candles were the note PRICE and move inversely. Any note-price series gets its own name; an existing name's meaning is never re-pointed.
- **Naming contract (v5.03):** the platform's canonical symbol names are the contract; `SYMBOL_ALIASES` in `routers/webhooks.py` is where a name is agreed, append-only; lineages are never merged after the fact.
- **Retirement is a HUMAN decision, never an inference (v5.05, v5.22).** `RETIRED_SYMBOLS` entries carry a date and reason; an entry missing either retires nothing. XRPUSD/USA500/USOIL retired by Shyam 2026-09-03; US10Y retired 2026-08-27 (contract roll, no successor).
- **Secret rotation deferred by explicit user decision (PLAT-SEC-1):** security, passwords and API keys wait until demo development ends; all accounts are DEMO. Recorded "so the decision is a choice and not an oversight".
- **The RUNNER FINAL GATE (2026-08-31, bot-session order, verbatim):** no broker-side stop movement until replay comparison complete (n≥20) · management evidence sufficient · no-widen invariant proven · state-machine invariant proven · real shadow sample collected · explicit human approval. Until then SHADOW ONLY; runner logic frozen at the v4.88 baseline.
- **FAIL-SOFT (v5.18):** the brain's bounded exception to Iron Rule 1 (approve on Pine trust when the council API errors on an A/A+, at most `FAILSOFT_MAX_PER_DAY=2` per UTC day, then fail closed). The platform renders it; "whether to keep that bounded exception is Shyam's call".
- **NSSM tombstone (SERVICE_AUDIT 2026-08-08) later corrected (v5.13):** the reporter now runs AS NSSM service `BrotherBotReporter` and that is the intended launcher; the 08-08 lesson is kept dated, not erased.

## The working laws of the platform session (docs/HANDOFF_PLATFORM_SESSION.md §6)

These are "not optional" and were paid for between v5.00 and v5.17:
- A field that is only ever compared to one value is a boolean, and the fact it was meant to carry is already gone (v5.19).
- Never infer a fact from silence. LIVE, STALE, NEVER_POSTED, UNREACHABLE, NOT_EXPECTED, RETIRED are distinct facts; the last two come from a human, never from a timer (refused three times: v5.05, v5.06, v5.13).
- One word carrying two facts is the fault to hunt (UNKNOWN, "news", STALE, ACTIVE, PASSED — v5.16/v5.17).
- Two right numbers with no anchor are a bug ("21m old" vs "6m since close"; "4.56 ATR" vs "4.81 ATR"). Label the anchor; do not change the number.
- A threshold is never moved as a side effect (Iron Rule 3 applied to display fixes).
- Recorded evidence is never redefined midway (`entry_dist_atr` feeds stored buckets; add a labelled second number, never replace).
- Historical is a normal state, not a defect: render `written at · value at writing · value now · age`.
- Render the branch; do not grep for the words (v5.14: every conditional template block gets a test that ENTERS it).
- A test written from the same wrong model as the code cannot falsify it (v4.36 → v5.17); prefer property tests.
- When the suite catches you, fix the code, not the test.
- Measured, never invented: CANNOT SEPARATE or "a broker fact this distance cannot see", never a guess.
- Add keys, never rename or remove them.
- Measure "cheap" on the box before believing it (v5.12: 2,180 ms).
- Secrets never reach chat, logs, templates or commits — including things that merely look like tokens.

Two standing rules from OPEN_ITEMS earned 2026-08-20: "BUILD TO THE WIRE, NOT TO THE SPEC" (curl a feed once and read the real keys before integrating; a parser must say which keys it got when it recognises none) and "RENDER THE REASON, NEVER THE ABSENCE" (any block that can fail renders in every state — dormant, active, or FAULT with the reason; a read model may not raise; Jinja `[key]` lookups are banned in favour of `.get`).
