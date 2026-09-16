---
title: V7 self-dependence master plan
domain: platform
repo: sabuj14eu/Sniper-System
sources: docs/V7_SELF_DEPENDENCE_PLAN.md
verified_on: 2026-09-16
commit: 3257184
classification: INTERNAL
---

# V7 SELF-DEPENDENCE — MASTER PLAN (locked 2026-08-14, explicit user decision)

**Read this before touching the desk, the lanes, the lab, or anything that
records an outcome.** This is the destination the platform has been building
toward. Any session (any model) modifying related code must keep every rule
in this file, or explicitly renegotiate it with the user first.

## 0. Mission — one sentence

Use 1–2 months of deterministic, labelled evidence collected by this
platform to make **v7 self-dependent within hard rules** — a bot that asks
"what has THIS exact setup actually done?" before acting, instead of a
human relaying dashboards.

**What this is NOT (user decision, verbatim intent):**
- NOT "AI decides everything". No LLM ever produces a trade decision.
  The AI research lane stays a *measured competitor*, never a driver.
- NOT a new strategy hunt. The Quant Lab Law stands: the goal is robust,
  reproducible OOS edges — "NO ROBUST STRATEGY" remains a first-class
  successful outcome.
- NOT a rewrite. The Trade Desk stays deterministic; learning is a layer
  ON TOP of frozen engines, never a change inside them.

## 1. Locked architecture — five organs, five responsibilities

```
MARKET DATA  →  DETERMINISTIC ENGINE  →  DATA COLLECTION  →  LEARNING LAYER  →  V7 DECISION → MT5
 (candles,       (structure/levels/       (fills, MAE/MFE,     (statistics/ML:     (TRADE/WAIT
  news, bias,     SL/TP/distance —         outcomes, context)   P(fill), P(win),    + confidence,
  macro)          FROZEN per version)                           E[R] — no price     inside hard
                                                                prediction)         risk rules)
```

| Organ | Role | Lives where |
|---|---|---|
| Trade Desk + lanes | **Sensor** — generates deterministic candidates | platform (`services/desk.py`, `services/autonomous.py`) |
| Evidence database | **Memory** — immutable labelled records | platform (Postgres: `decision_records`, `session_candidates`, …) |
| Learning layer | **Pattern recognition** — conditional statistics, later ML | platform (Phase 2–3, new `services/learning.py` + Model Lab) |
| Risk engine | **Guardian** — hard limits, never widened silently | bot box (EquityGuard etc.) + platform display |
| v7 | **Decision maker** — TRADE/WAIT using the learned numbers | bot box (`brother_sniper_v7`) |

The platform NEVER executes (Iron Rule 1 — unchanged, forever). The
learning layer's output crosses to the bot box as *data* (numbers with
sample sizes), never as an order.

## 2. What already exists (inventory for future sessions — do not rebuild)

Engines, all FROZEN by regression test `test_the_original_auto_v1_maths_is_frozen`:
- `auto-v1` — 15m/40-bar structure pullback (`services/autonomous.py`)
- `scalp-v1` (15m/12), `session-v1` (1h/24), `swing-v1` (4h/40) — same
  arithmetic, other lookbacks (`services/desk.py: tf_candidate, HORIZONS`)
- Fixed outcome rules — `ai_analyst._resolve` (trigger-first, same-bar
  SL-first, R units, 24h horizon, NO-FILL ≠ loss, NO_DATA after 5 days)

Records (append-only / write-once):
- `decision_records` — per round: context (blind), bot/ai/auto calls,
  outcomes ±R, `entry_dist_atr` inside auto_call, prompt version
- `session_candidates` — PRE-COUNCIL funnel with council verdict + own outcome
- `signals` + `opportunity.group_signals` — production mirror, deduped analytics
- Gate traces, news scenarios, shadow outcomes of rejected signals

Measurements already live: fill-rate-by-distance buckets, setup-class
history (`structure×direction`), evidence ladder (`stats.evidence_status`),
Wilson CIs, head-to-head lanes, candidate→council conversion.

## 3. THE DATASET — the whole project is this table

One row per candidate per lane. Fields marked ✅ are recorded today; ⬜ are
the Phase-1 gaps to close.

| Field | Status | Where / note |
|---|---|---|
| asset, session, timeframe, engine version | ✅ | candidate dicts |
| structure, direction, entry/SL/TP1/TP2, ATR, R:R | ✅ | candidate dicts |
| entry distance in ATR *at birth* | ✅ | `entry_dist_atr` (v3.21) |
| bias (validated), news state | ✅ | snapshot sections |
| macro (DXY/US10Y/OIL state) | ✅ | snapshot `macro` (in fingerprint) |
| regime (RANGE/TREND) | ✅ | `lane_observations.regime` (v4.0) |
| spread at decision time | ✅ (v4.8) | bot box samples the live MT5 tick (`mt5_tick_at_decision`) and ships it on the bias heartbeat; recorded only while under 10 min old, else UNKNOWN |
| volatility context (ATR vs its own average) | ✅ | `vol_ratio` (v4.0), None until 115+ bars |
| filled? / outcome TP1/SL/TIMEOUT/NO-FILL | ✅ | `_resolve` |
| time-to-fill | ✅ | `time_to_fill_min` (v4.0) |
| MAE / MFE (worst/best excursion after fill, in R) | ✅ | `mae_r`/`mfe_r` (v4.0) |
| structural invalidation hit before fill? | ✅ (finding) | `invalidated_before_fill` — structurally unreachable for this engine family (stop beyond entry); documented in code + test |
| final R | ✅ | `*_r` columns |
| **ALL FOUR desk horizons recorded, all symbols** | ✅ | `collector.record_all` (v4.0), one row per closed bar, WAITs included |

**All dataset fields are now ✅ (v4.8).** What remains for Phase 1 is
volume, not fields: the exit gate is 200 resolved trade candidates.

**Phase-1 definition of done = every ⬜ above is ✅**, recorded by the
sweeper on a fixed cadence, resolved by the same fixed rules, and disclosed
on the desk. New columns are ADDED (append-only migrations); existing
outcome semantics are never redefined — if a rule must change, it becomes a
new named ruleset version, like `ai_prompt_version` did (mixed protocols
are disclosed, never pooled).

## 4. Phases with hard gates — no phase starts before the previous one's exit test

**Phase 1 — COLLECT (now → ~2 weeks).** No learning, no decisions.
calculate → record → resolve. Close the ⬜ gaps; record every horizon for
every tracked symbol each sweep. *Exit:* dataset fields complete, ≥200
resolved lane-candidates total, Data Health shows the recorder's own
liveness.

**Phase 2 — ANALYZE (statistics only, no ML).** Conditional tables the
user can read: setup class × session × distance bucket × news state ×
regime → n, fill %, WR CI, expectancy. Pages, not models. *Exit:* at least
one condition cell reaches n≥100 and the Evidence Law verdicts are shown on
every cell. Findings like "GOLD entries beyond 2 ATR almost never fill"
must come from these tables — never from intuition.

**Phase 3 — TRAIN.** Only targets allowed: `P(fill)`, `P(TP1 before SL |
filled)`, `E[R]`. NEVER price prediction. Model Lab laws apply verbatim:
80% train / newest 20% FINAL HOLDOUT spent once, calibration reported,
selection bias disclosed, artifacts can never emit a signal. Simple,
inspectable models first (binned frequencies → logistic regression);
anything fancier must beat them out-of-sample to exist. *Exit:* holdout
calibration is honest (predicted vs realized within CI) — otherwise the
correct verdict is "NO ROBUST MODEL", which is success, not failure.

**Phase 4 — SHADOW.** v7 keeps deciding exactly as today. The learned
layer's TRADE/WAIT is *recorded beside* every v7 decision (a fourth lane in
the existing head-to-head machinery — reuse `head_to_head`, the evidence
ladder, MIN_COMPARABLE_N=100). *Exit:* ≥100 comparable shadow rounds AND
the ladder says the learned layer ≥ old v7 on expectancy with CI
separation. No early peeking upgrades.

**Phase 5 — CONTROLLED DEPLOYMENT (bot box, demo first).** v7 consumes the
learned numbers inside hard rules: risk engine untouched and above
everything, per-setup-class kill-switches, position limits, "one position,
council on top" (user's recorded decision). Any degradation vs shadow
expectations → automatic fallback to old v7. Real accounts only after the
user's separate security pass and explicit sign-off.

**The example that defines the finish line** (keep it in every review):
SILVER HH/HL BUY, 0.75 ATR away, London, DXY bearish, news LOW, n=84 →
fill 61%, E +0.42R → TRADE. Same chart but NY, DXY strongly bullish, CPI
in 12 minutes, n=31, E −0.18R → **WAIT, even though the chart looks good.**

## 5. Standing rules for ANY future session touching this work

1. **Frozen engines never change in place.** New behavior = new engine
   version string with its own records. The regression lock test must pass.
2. **Measure before changing** — thresholds (like max entry distance) come
   from the recorded tables, never from advisors' round numbers.
3. **Evidence Law everywhere**: n<20 luck, ~100 to judge, Wilson CIs, the
   evidence ladder is the only vocabulary for "winning".
4. **A number without a source/timestamp/freshness is a bug** (Freshness
   Law). UNKNOWN stays UNKNOWN; synthetic metrics (e.g. "adjusted R:R")
   are refused — measure the real thing instead (fill probability).
5. **Append-only**: new columns yes, redefining stored meanings no.
   Migrations in CHANGELOG (Iron Rule 6).
6. **The platform never executes; v7 executes on the bot box.** The
   interface between them is data with ids (`pine_signal_id`/`SC-…` style
   exact joins), posted to the existing webhooks.
7. **No LLM in the decision path.** The AI lane remains a measured research
   competitor with a versioned protocol.
8. Coordinate bot-box changes through the user's brain-v2 session; this
   repo's audits live in `docs/audits/`.
9. **Recorded market state is history — never rewritten** (v4.2 user
   decision). `market_snapshots` rows are frozen at insert; only the
   outcome columns fill in, and only after the observation window has
   closed. An outcome written early is look-ahead, and one contaminated
   row poisons every statistic Phase 2 computes. The Daily Brief may grow
   in what it *records*; it may never grow a path into a decision.

## 6. Division of labor

| Platform (this repo) | Bot box (brain-v2 / v7 repos) |
|---|---|
| Phase 1 recorder + gap fields | Ship spread in heartbeat/candles (else UNKNOWN) |
| Phase 2 condition tables (+ /learning page) | Keep bias heartbeat + `SC-` id discipline |
| Phase 3 models under Model Lab laws | Fix remaining P0s (journal outcomes, minted ids) |
| Phase 4 shadow lane + comparison | Phase 5: consume learned numbers in v7, risk engine on top |

## 7. Tooling ("do we need a plugin?")

**No new plugins/services for Phases 1–2.** Everything is SQLAlchemy +
stdlib statistics that already exist here — adding tools now adds failure
modes, not speed. Phase 3 adds **scikit-learn (+ numpy/pandas) inside the
existing Model Lab only** — local, pinned in requirements, no external ML
SaaS, no data leaving the server. Nothing else is approved; if a future
session believes it needs more, that's a user conversation, not a
dependency bump.

## 8. Status ledger (update this section as phases progress)

- 2026-08-14 — Plan locked. Phase 1 IN PROGRESS: sensor + memory + fixed
  rules live (v3.23, 216 tests); gap fields of §3 are the open work.
- 2026-08-14 — **Phase 1 RECORDER SHIPPED (v4.0, 225 tests).** New table
  `lane_observations` + `services/collector.py`: all 4 engines × every
  tracked symbol, one immutable row per closed bar, WAITs included.
  Closed from §3: MAE/MFE, time-to-fill, volatility ratio, regime, macro,
  invalidation flag, all-horizons-all-symbols recording.
  `resolve_detailed` is pinned to `ai_analyst._resolve` by test (same
  outcome + R on every case); horizons declared per engine
  (scalp 12h / auto 24h / session 48h / swing 120h), stamped as
  `ruleset=lane-resolve-v1`. Progress panel + exit gate on /desk.
  STILL OPEN: **spread** — UNKNOWN on every row until the bot box ships
  it (bot-side task, never guessed here).
  FINDING recorded in code + test: for this engine family the stop sits
  BEYOND the entry, so `invalidated_before_fill` is structurally
  unreachable and stays False; kept, measured and documented rather than
  shipped as a decorative flag.
  EXIT GATE: 200 resolved trade candidates — watch the /desk panel.
- 2026-08-14 — **Daily Market Brief shipped (v4.1, 241 tests)** — a
  RESEARCH layer beside the pipeline, not part of any phase. Scenarios are
  decided deterministically from stored levels; the LLM narrates verified
  facts and is rejected if it uses a number the facts do not contain; the
  brief has no write path to the desk, v7, the council or MT5. This is the
  only sanctioned place an LLM may write user-facing market prose, and
  rule §5.7 (no LLM in the decision path) is unchanged by it.
- 2026-08-14 — **Market-state memory shipped (v4.2, 252 tests)** — table
  `market_snapshots`: one immutable, machine-readable row per brief holding
  ONLY what was known at that moment (levels with provenance and distances,
  scenario in its own columns, bias/news/freshness/macro, price with its
  own timestamp). ORM guard `SnapshotImmutable` refuses any edit to an
  information-state column; outcomes are NULL until the 24h observation
  window closes and are then filled by `snapshot-outcome-v1` (first event
  wins + MFE/MAE in ATR + time-to-event). This is a SECOND dataset beside
  `lane_observations`: lanes record *candidate trades*, snapshots record
  *market states*. Phase 2 reads both; neither feeds a decision.
  The brief itself is now AI-optional: a template narrator prints the same
  structure and prices in fixed sentences, held to the same grounding rule.
- 2026-08-17 — **§3 DATASET COMPLETE (v4.8, 280 tests).** The bot box
  shipped spread at decision time (MT5 tick, `spread`/`spread_points`/
  `spread_source` on the bias heartbeat, decision posts and candles).
  Platform stores it with its OWN timestamp on `market_bias` and records
  it on every lane observation while under `SPREAD_MAX_AGE_MIN`=10 min
  old; older or missing stays UNKNOWN and is never back-filled — an old
  spread is not a tight spread. Phase 1 now has NO open fields; only the
  200-resolved-candidate exit gate remains.
  Also confirmed done bot-side: candidates POSTed pre-council, exact
  `SC-` id join (price tolerance is legacy-only), bias recomputed with
  honest `as_of`, weekend gate corrected to Fri 22:00 → Sun 22:00 UTC.
  Recorded gaps that are DATA-SOURCE limits, not bugs: US10Y and VIX are
  absent from this MT5 account and Pine's yields never reach the brain.
- Phase 2 — not started. Phase 3 — not started. Phase 4 — not started.
  Phase 5 — not started (blocked on Phases 1–4 + user security pass).
