---
title: Brother Sniper v7 — validated evidence and open questions
domain: v7
repo: sabuj14eu/brother_sniper_v7
sources: CLAUDE.md, INTENT_v5.md, docs/START_HERE.md, docs/V7_AUDIT_2026-08-01.md, docs/STRATEGY_INTELLIGENCE.md, docs/AUTONOMY_READINESS_2026-08-30.md, docs/V7_AUTONOMY_PLAN.md, docs/ADAPTIVE_GATES_SPEC.md, docs/OPEN_ITEMS.md, docs/PINE_UPDATE_NOTE.md, docs/UI_WORK_ORDER_2026-09-02.md, core/sl_engine.py, filters/ai_filter.py, bot.py, patch_v7_atr_floor.py, auto_live.py, utils/asset_gate.py
verified_on: 2026-09-16
classification: INTERNAL
---

# How to read this file

Every number below names its source and date. Populations are never mixed:
"backtest harness" (Pine/brain-side, train/validate split), "v7 journal"
(`learning/trades.jsonl`, actually filled demo trades), "paper lanes"
(the platform's lane_observations, ruleset lane-resolve-v1, NO costs), and
"telemetry" (v7 rejects + opens). A finding from one population is a note; a
rule moves only when two independent populations agree (Evidence Law). Where
the repo does not carry the number, it says UNKNOWN.

# Constitution-level evidence (CLAUDE.md "CURRENT EVIDENCE", change only with new data)

- PULLBACK trigger validated: n=640 backtest, out-of-sample PF 1.30–1.45,
  stop 1.5xATR (0.8xATR FAILED validation). Asia is its BEST session (73.6%
  WR). Source: CLAUDE.md; backtest harness (pullback_backtest in the brain
  dir). Note: v7 does NOT trade PULLBACK (C4 decision); auto_live is the
  pullback path.
- Fixed 2R take-profits FAILED validation on structural levels. The
  high-win-rate small-R ladder (session TP 1.0/1.8 ATR) is the validated
  design. Source: CLAUDE.md.
- SMART_SCALP grades/scores are ANTI-predictive (score <= 6 beat 9+; grade B
  beat A+). Do not hand-reweight; the engine is on trial by journal. Source:
  CLAUDE.md. Consequence in v7: v18 `pine_score` is NOT blended into the
  filter (grade gate only), and the grade gate keeps A/A+/B.
- Counter-trend entries are the #1 documented loss driver (SELL bleed -406).
  Source: CLAUDE.md; F8 comment in filters/ai_filter.py adds "SELL PF 0.54,
  WR ~19%" (2026-07-02).
- GOLD is the weakest asset (macro-driven; technicals bleed there); SILVER
  and US100 are the strongest. Source: CLAUDE.md.
- FIB-retracement levels: promising challenger (validate PF 1.82, n=62) —
  watch-list, builds only at PF ~1.5+ with n >= 100 validate. Source: CLAUDE.md.

# v7 mechanical evidence encoded in code comments (dated)

- 2026-06-26 (core/sl_engine.py): metals SL floors raised to 1.0% because
  "<1% stops bled -432 (17%WR) vs >1% +280 (80%WR)".
- 2026-06-18 (Patch P0): trust mode accepted Pine's raw SL verbatim -> "noise-
  tight stops (gold 2.5pt deaths)"; ATR floor added.
- 2026-06-25: TP inflation removed — SL adaptive, TP stays as Pine sent it.
- 2026-07-02 (F2): MIN_RR raised 0.5 -> 1.0; "bot was live-trading 0.63R
  setups (needs 61% WR to break even)". Widen-ratio guard 1.6x added.
- 2026-07-02 (F3): `round(x, 2)` corrupted 5-digit forex stops (EURUSD
  1.17345 -> 1.17 = SL moved ~35 pips) -> per-symbol `_PX_DIGITS`.
- 2026-07-02 (F4): indices were missing from specs; USTEC/US30 sized with
  GOLD's tick math; "$1/point/lot assumed — VERIFY against MT5" (still
  flagged UNVERIFIED in code).
- 2026-07-02 (F7): auto-SL fabrication removed; a signal without SL is noise.
- 2026-07-02 (F9): DST-aware sessions; the static UTC table "mislabeled
  sessions, cluster keys and the Asia-bleed analysis" all summer.
- 2026-07-10 (patch_v7_atr_floor.py): trust-mode floor was a legacy ~1.5%
  percent-of-price floor; SILVER floor 0.908 vs Pine 0.3696 (4.7x live ATR)
  -> v7 rejected essentially every v18 scalp signal; floor became 1.2 x live
  M15 ATR (SILVER example: floor 0.908 -> 0.231 with ATR 0.19257).

# V7 AUDIT 2026-08-01 — data verdicts (docs/V7_AUDIT_2026-08-01.md, addendum)

- Breakeven zero was a JOURNAL bug, not detection: 23 of 47 studyable trades
  reached MFE >= 1R of their actual stop and `grep -c "[BE]" logs/bot.log*`
  found 33 breakeven lines; `be_done` never reached trades.jsonl. FIXED
  (close_trade carries be_done/partial_done). Partial-close 0 is by design
  (`if False` [BE-ONLY]).
- MAE study (n=47, run on the live box): survival rises with stop width
  (31.9% @1.0xATR -> 55.3% @2.0x) but decided-case avg R stays ~ -0.89 at
  every width and net R stays deeply negative (-29R -> -20R). Verdict:
  "tight stops lose because they are attached to bad trades, not because
  they are tight" — selection levers (asset gate, counter-trend penalty)
  over stop-width changes. Re-run at n >= 100.
- Shadow-eye scoring: baseline WR 48.5% (n=169). Trades deepseek voted BLOCK
  that ran anyway won 59.1% (n=22) — its blocks look ANTI-predictive; at
  confidence >= 60 the blocked-but-ran trades won 100% (small n). deepseek
  TAKE n=4 PROVISIONAL; gemini mostly abstains (NONE=112). Neither model
  earns enforcement. 44 early votes carry model="?" (excluded).
- GOLD: no gold-specific mechanical defect found (lot math, digits, floors,
  caps all correct or protective); the gold bleed is strategic.
- Sample at the time: 152 trades (Task 1); "170 v7 / 89 brain trades describe
  OLD-Pine logic" (docs/STRATEGY_INTELLIGENCE.md) — a baseline to beat, not a
  verdict.

# Asset bleed re-derived on v7's own journal (docs/START_HERE.md, 2026-08-21)

SILVER n=48 EV_lcb -0.00; GOLD n=33 EV_lcb -0.50; ETHEREUM n=22 EV_lcb -0.48.
"Independently confirms the constitution's oldest asset claim. Actionable
when someone chooses to change one organ." (Second population for GOLD.)

# Entry distance (paper lanes ONLY — one population)

Platform paper lanes: `>3 ATR -> -0.19R (n=620)`, with-trend `-0.643R
(n=368)` (docs/START_HERE.md); readiness report restates the far bucket as
`-0.21R pooled n=827; with-trend -0.643R n=368`, near buckets positive.
Nothing moves until v7's own filled trades agree; `entry_dist_atr` entered
v7 telemetry on 2026-08-21 (forward-only; the n >= 20–30 per-bucket clock
started then). Verdict on "does entry distance kill edge": ONE POPULATION,
not yet a finding for v7.

# Weekend Autonomy Readiness Report (docs/AUTONOMY_READINESS_2026-08-30.md)

Paper/research population (lane-resolve-v1, no costs): 33,789 observations,
16,495 trade candidates, 14,941 resolved. Per engine (measured 2026-08-30):
auto-v1 n=2,659 WR 23.3% +0.263R gross (+699.7R total); scalp-v1 n=4,907
WR 29.0% +0.053R; session-v1 n=648 WR 21.0% -0.094R; swing-v1 n=75 WR 22.7%
-0.119R. Council rounds n ~ 21 — too thin for any council-level verdict.

auto-v1 spread-cost-discounted per symbol (the DECISION TABLE): NET POSITIVE
SILVER +1.303R (n=285), GBPUSD +1.168R (n=195), US30 +0.843R (n=149), BTC
+0.133R (n=150). NET NEGATIVE: GOLD -0.091, ETH -0.265, EURUSD -0.407, US100
-0.742, USDCAD -0.782, USDJPY -1.660, SOL -1.755, XRP -0.258. This table is
why `auto_live.py` trades only SILVER, GBPUSD, US30 (auto_live.py docstring)
and why GOLD is excluded from auto-live-v1. GOLD overall on paper: -0.085R
gross, -0.091R net (n=163).

Pine/bot agreement: n=7 agree vs n=14 disagree on evaluated rounds — BELOW
FLOOR, CANNOT SEPARATE. Pine-independence of GENERATION proven (16,495
no-Pine decisions); head-to-head superiority NOT claimed.

Readiness gates: DATA INTEGRITY PASS (audit_candle_offsets GOLD/SILVER/BTC/
ETH: 0 off-grid, 0 twins); FRESHNESS PASS; ENTRY ENGINE PASS; PINE
INDEPENDENCE PASS; RISK ENGINE PASS (auto_live reuses v7's chain);
MANAGEMENT REPLAY NOT RUN; STATE MACHINE NOT RUN; EXECUTION SAFETY
DEVELOPING; ADAPTIVE PROFILE DEVELOPING; NEWS ENGINE DEVELOPING (feed live 4
days); EVIDENCE PASS on entry engine. FINAL: SHADOW ONLY — MORE EVIDENCE
REQUIRED. Recorded WAITs: 17,294.

Phase 1 exit gate MET (2026-08-29): resolved_trades 14,941 vs target 200,
spread recorded on 31,749 rows, vol_ratio on 33,281 (docs/V7_AUTONOMY_PLAN.md).
Phase 2 (Analyze) is the current phase.

# Operational measurements recorded in OPEN_ITEMS / docs

- v7 record at the 2026-09-03 round-4 read: W86 / L95, USDJPY BUY open.
- Grade collection week: C/D signals fired (16 `C ok`, 13 `D` in bot.log)
  but were blocked downstream for being counter-trend; "Do Pine grades
  predict? UNKNOWN" (docs/START_HERE.md).
- AI budget: brain weekly AI budget exhausted ($10.37/$10.00) since Aug 22
  -> council signals fail-soft to pine_trust twice a day then FAIL CLOSED
  (docs/V7_AUTONOMY_PLAN.md, 2026-08-24). A known unnecessary blocker,
  since fixed per the readiness report.
- Pending-order finding: a SILVER SELL 0.03 sat PENDING 10 days with no
  SL/TP -> organ candidate PENDING-ORDER TTL (2026-08-24).
- NVDA.NAS-24 probe (terminal 52834417, 2026-09-02): digits 2, vol
  min/step/max 0.1/0.1/1000.0, contract 1.0, trade_mode 4 (FULL), currency
  USD; US session re-probe 15:46 UTC: bid/ask 226.86/226.88, spread 2 pts =
  $0.02 (~0.9 bp); overnight spread UNMEASURED. Platform 5.08: NVDA 15m 101
  rows, 1h/4h/1d 100, 1m 120, lane_observations 6, bias rows 0.
- Perf triage (2026-08-29, platform): candles 957,526 rows / 219 MB,
  lane_observations 33,789 / 35 MB; composite candle index already exists;
  the bottleneck is a single app worker + uncached read models, not indexing.
- Candle timestamp incident (2026-08-20): ~30,209 mis-stamped rows across
  GOLD/SILVER/BTC/ETH 4h/1d from a +2 instead of +3 broker offset; GOLD, ETH,
  SILVER rebuilt, BTC pending at handover (docs/START_HERE.md).
- Pine calculation error (2026-08-31): three `request.security_lower_tf`
  calls (v18.12 F3 DXY squelch) blew the per-study memory limit on the
  heaviest 24h symbols — SILVER silent 3 days, US100 5 days, panels vanished
  mid-position. One event, three symptoms (docs/PINE_UPDATE_NOTE.md).

# Evidence thresholds that would flip a prepared dial (none flipped as of 2026-09-16)

- F8 counter-trend 0.65 -> 0.50 (`F8_CT_50`): flip if counter-trend trades
  since 2026-07-02 still show PF < 0.9 at n >= 20 (filters/ai_filter.py).
- Asset gate size-down GOLD:0.5: GOLD PF < 0.9 at n >= 30 lifetime AND last
  30 days net negative; bench GOLD entirely: PF < 0.7 at n >= 30
  (utils/asset_gate.py). Flip = one .env line + restart, logged in the
  weekly review.
- Freshness gate enforce: after reading shadow numbers, n >= 20.
- Adaptive CAUTION mapping: only where a NEGATIVE CELL is MEASURED (n >= 20)
  and both populations agree (docs/ADAPTIVE_GATES_SPEC.md).

# Explicitly NOT yet proven (UNKNOWN / NOT RUN / DEVELOPING as of the repo)

- Whether Pine grades predict outcome on v7 (UNKNOWN; C/D data accrues only
  when every other filter agrees).
- Whether entry distance kills v7's edge (one population; v7 buckets filling).
- Whether news-window trades measure better or worse (news_minutes on every
  trade; NEWS01 observe mode now collects `news_observe` verdicts; "High news
  is NOT auto-negative anywhere; it is uncut data").
- Whether post-news retest beats the first impulse (event engine 4 days old
  at the report).
- Whether management (BE/partial/trail) adds value: `mgmt_replay.py` exists,
  NOT RUN as a report; TP1/trail/runner/news-aware are UNKNOWN because the
  monitor records only sampled MAE/MFE extremes.
- State-machine integrity: `audit_mgmt_state.py` exists; NOT audited in the
  report.
- The GOLD demo-collection verdict (RE-GATE or KEEP): reads on the
  platform's /v7 rejected-vs-traded card, not in this repo — UNKNOWN here.
- Whether the EV/cluster learning layer is structurally inert (external
  review claim, NOT YET VERIFIED).
- US30/USTEC index tick values ($1/point/lot assumed, unverified);
  NVDA overnight spread; DXY_U6 roll (mid-September).
- The v18.9 dark flags SB_PENDING, BIAS_INFO, ASSET_PULSE, BREAKOUT await
  harness validation; usd_lag_backtest (DXY_U6 vs gold) harness not built
  (CLAUDE.md QUEUED WORK).
- ISO-19 shadow soak n >= 20; v18 pending-order expiry policy (OPEN_ITEMS).
- The Pine/bot agreement cut becomes measurable only after v18.13's
  `structure` accrues (captured since 2026-08-29).
- Whether auto_live's real replies from the running bot were clean for one
  week (gate for DEMO auto-exec) — the dry log lives on the box.
