---
title: Sniper-System platform constitution (CLAUDE.md)
domain: platform
repo: sabuj14eu/Sniper-System
sources: CLAUDE.md
verified_on: 2026-09-16
commit: 3257184
classification: INTERNAL
---

# CLAUDE.md — Brother Bot Platform Constitution

Read this before touching anything. This repository is the multi-tenant SaaS
platform (public site, user dashboard, admin) for the Brother Sniper trading
system. The trading brain (v18 council) and the v7 bot live elsewhere; this
platform observes and manages — it never trades.

## IRON RULES — NEVER VIOLATE
1. NOTHING here dispatches signals. The platform receives a **read-only
   mirror** of signals/decisions from the v18 brain for display, journaling
   and analytics. No code path in this repo may send an order, a dispatch, or
   any instruction to an executor. The CMS manages accounts/routing metadata,
   NEVER signals.
2. Payload contract is APPEND-ONLY. The signal mirror stores the raw payload
   verbatim (`Signal.raw_payload`) and never renames/removes fields the brain
   sends (system, signal, direction, signal_id, symbol, tf, entry, sl, tp,
   tp1, tp2, rr, grade). Unknown keys pass through.
3. Never widen risk silently. Risk limits, lot sizes and emergency-stop state
   are explicit user/admin decisions, and every change is written to the
   audit log with its actor.
4. Secrets (.env, tokens, MT5 passwords, API keys) are never committed and
   never printed in logs, templates, or chat. Stored credentials are
   encrypted at rest; API keys and OTPs are stored hashed.
5. Health endpoints lie; only tickets/journal tell the truth. Status displays
   must be driven by reported heartbeats with staleness windows, never by
   "the endpoint returned 200".
6. Every schema change ships with a migration note in docs/CHANGELOG.md.
   Deploys follow: backup -> migrate -> restart -> verify logs.

## LAYOUT
- `app/main.py` — FastAPI app factory; all routers mounted here.
- `app/models/` — SQLAlchemy models (user, trading, billing, platform).
- `app/services/` — business logic (otp, analytics, notify, audit, billing).
- `app/routers/` — public site, auth, user dashboard modules, admin, API v1,
  and the brain mirror ingest (`webhooks.py`).
- `app/templates/` — Jinja2: `public/`, `dash/`, `admin/` on shared bases.
- `scripts/seed.py` — seed plans, symbols, demo admin + demo data.
- `tests/` — smoke tests over the full route surface.

## QUANT LAB LAW (locked 2026-08-08, explicit user decision)
The Strategy Factory / Model Lab objective is: **find statistically robust,
reproducible, out-of-sample edges, with the ability to conclude that no
robust edge exists.** "NO ROBUST STRATEGY" is a first-class, successful
outcome. Never build or accept "find the most profitable strategy".
Corollaries, enforced in code — keep them enforced:
- Variant families are predefined and hard-capped; no free-form dredging.
- Search touches only the first 80% of a dataset; the newest 20% is the
  FINAL HOLDOUT, spent exactly once per experiment and never re-armed.
- Verdicts come from OUT-OF-SAMPLE segments; raw return never ranks.
- Selection bias ("best of N") is disclosed on every report.
- Research uses CLOSED candles only; the 200-candle floor never lowers.
- Evidence Law: n<20 is luck, ~100 to judge — labels say so.
- Model Lab artifacts can never emit a signal or reach an executor.

## FRESHNESS LAW (locked 2026-08-11, explicit user decision)
STALE DATA MUST NEVER BECOME A VALID POSITIVE SIGNAL.
- STALE BIAS  ≠ neutral — it is INVALID and unused (gate: BIAS_MAX_AGE_H,
  market clock, enforced in build_snapshot so every consumer inherits it).
- MISSING NEWS ≠ low risk — it is UNKNOWN (news_risk returns UNKNOWN on an
  empty calendar; UNKNOWN fails "news ≤ X" conditions by default).
- STALE PLAN ≠ ready (12h signal expiry) · STALE SERVER ≠ healthy
  (heartbeats only) · STALE SIGNAL ≠ current opportunity · UNKNOWN ≠ any
  direction. Every displayed number needs: source → timestamp → freshness
  → authority → meaning → expiry.

## A CLOCK NEEDS TWO WITNESSES (locked 2026-08-21, after the incident)
Corollary of the Freshness Law, aimed at INGESTED time rather than
displayed time. On 2026-08-20 the reporter read ONE tick — gold's,
during the metals rollover break — and inferred the broker offset from
it. **A single tick cannot separate "the clock is +3h" from "this
quote is an hour old": both look identical.** It concluded +2h, and
every bar pushed for 25 minutes was stamped an hour late.
- **Timestamps are inferred from ≥2 fresh, independent witnesses, at
  least one of which trades 24/7**, or not inferred at all. Staleness
  is measured by comparing witnesses to each other, never assumed.
- **A wrong clock is not degraded data, it is corrupted data.** Because
  the candle key is (symbol, tf, ts), a shifted bar does NOT overwrite
  the correct one — it creates a second parallel series, and on fine
  timeframes it silently overwrites a different bar's prices instead.
  So the agent REFUSES to run rather than guess (never "assuming 0").
- **A push is not "delivered" until the receiver says what it stored.**
  The reporter logged "5000 candles pushed" while the platform silently
  dropped rows; both ends now report and compare counts.
- **A SCALAR OFFSET CANNOT CONVERT A MULTI-YEAR SERIES.** The broker
  runs EET/EEST and MT5 returns history in server wall-clock, so the
  seasonal hour is inside the data. Subtracting one number from a deep
  backfill is wrong by an hour for every bar of the opposite season
  even when detection succeeds. Convert PER BAR through the broker's
  DST calendar, or store the raw server stamp plus its timezone and
  convert at read time.
- **INTERNAL CONSISTENCY IS NOT CORRECTNESS**, and this is the trap
  that outranks the rest: a uniformly-wrong series passes every
  self-consistency test, because the error is uniform. Checking the
  MODE of a distribution is not checking the distribution. Before
  deleting anything on grid evidence, ask what a CORRECT series would
  look like — here it has TWO grids, so the tidy one is the suspect.
See `agents/mt5_reporter.detect_broker_offset`,
`webhooks.upsert_candles_report`, `services/candle_audit.season_check`.

## EVIDENCE AUTHORITY (locked 2026-08-20, both sides agreed)
A number is not a conclusion. Two rules, earned the day the first real
finding appeared:
- **PAPER LANES ARE A HYPOTHESIS GENERATOR, NEVER A GATE AUTHORITY.** The
  platform's own lanes place limits and record what happened to them.
  That population is not v7's: different generator, different capital,
  different cancellation behaviour. A lane statistic may PROPOSE a rule
  change; only v7's own filled trades may justify one. **Two independent
  populations agreeing is the standard.** One of them alone is a note.
- **A SPLIT SAMPLE IS A SMALLER SAMPLE.** Before a bucketed result is
  read as a finding, cut it by the obvious confounders (side, and
  with-trend vs against-bias) and check n IN EACH CELL. 620 pooled can be
  12 in the cell that answers the question. When the deciding cell is
  under the Evidence Law floor the honest verdict is **CANNOT SEPARATE**,
  and refusing to conclude is a first-class outcome exactly as "NO ROBUST
  STRATEGY" is. See `desk.distance_confounders`.

## PINE IS THE SENSOR AND IT STAYS FROZEN (locked 2026-08-20, bot box)
Do NOT propose moving intelligence into Pine. Every Pine save requires
deleting and recreating every alert, so the script that fires is frozen
at alert-creation time — a Pine that changes weekly means a ceremony
every week AND, worse, history that is no longer comparable: you could
never tell whether last month's results came from last month's logic.
**A sensor that keeps changing measures nothing.** Pine emits; the layer
that WATCHES it gets smarter. New intelligence belongs in the evidence
tables and their read models, never in the instrument.

## V7 SELF-DEPENDENCE MASTER PLAN (locked 2026-08-14)
The long-term destination is documented in **docs/V7_SELF_DEPENDENCE_PLAN.md**
and is binding: the deterministic Trade Desk is the SENSOR, the evidence
tables are the MEMORY, a statistics/ML layer (Phases 2-3, Model Lab laws)
is the PATTERN RECOGNITION, the risk engine stays the GUARDIAN, and v7 on
the bot box remains the DECISION MAKER — self-dependent within hard rules.
Five phases (Collect → Analyze → Train → Shadow → Controlled deployment),
each with exit gates; no phase may be skipped. Frozen engines (auto-v1,
scalp/session/swing-v1, _resolve) never change in place — new behavior is
a NEW versioned engine. No LLM in the decision path, ever. Read the plan
before modifying the desk, lanes, lab, or any outcome recorder.

## SESSION HANDOFF (read this second, before OPEN_ITEMS)
**docs/HANDOFF_PLATFORM_SESSION.md** is the living handoff for the
platform session: what this side owns and does not, how Shyam works
and therefore how commands are written, the state at handoff, and the
working laws learned between v5.00 and v5.17 that this file does not
carry (never infer from silence; one word carrying two facts is the
fault to hunt; a threshold is never moved as a side effect; render the
branch, do not grep for the words). It ends with the paste-ready
opening prompt for a new window. Update it at every handoff.

## OPEN ITEMS (read before declaring anything finished)
**docs/OPEN_ITEMS.md** carries the deferred work of BOTH sides — the
platform's un-rotated v7 webhook secret (deferred by explicit user
decision while everything is DEMO) and the bot box's two P0s (journal
outcomes never filled; the brain minting its own signal_id instead of
adopting Pine's, which is why `FALLBACK_ID` still appears on /funnel).
An item deferred in conversation is an item forgotten — if it is not in
that file, it does not exist. Delete an entry only when it is done and
verified, and say where the proof is.

## HOW TO WORK HERE
Findings first, then code. Small verified diffs over rewrites. Run
`pytest -q` before every commit. All user-visible money/risk numbers come
from the database, never hardcoded in templates.

## PINE WORKSPACE (memory pointer — read before touching anything in pine/)
`pine/` holds the TradingView side of the system, versioned here so every
session (and every new window) sees the same state:
- `BrotherSniperULTIMATE_v18_FINAL_v6.pine` — the indicator, currently
  **v18.12.x** (five releases on 2026-07-30/08-01: display truth → correctness
  → execution integrity → full backlog → panel truth).
- `BrotherSniper_AssetPulse_v1.pine` — separate session best-asset panel
  (own token budget, no alerts, by the D12 separate-script rule).
- `V18.9…V18.12_RELEASE_NOTES.md` — the full history: triage verdicts on two
  external reviews, refusals **with arithmetic** (pullback RR gate would delete
  a PF-1.30-1.44-validated engine; payload renames violate append-only),
  token ledger, deploy ceremony.
Pine iron rules mirror this file: alert-payload contract is APPEND-only;
compiled-token ceiling ~80K (comments free, operations cost); evidence before
Pine — new strategy organs ship DARK (`FEATURE_*` flags, default-off inputs)
until the journal validates them; the council/bot is the single risk
authority — Pine never blocks signals on quota/PnL (explicit user decision,
2026-07-30).
