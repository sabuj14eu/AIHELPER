---
title: Sniper-System platform evidence ledger
domain: platform
repo: sabuj14eu/Sniper-System
sources: CLAUDE.md, docs/CHANGELOG.md, docs/OPEN_ITEMS.md, docs/V7_SELF_DEPENDENCE_PLAN.md, docs/HANDOVER_V7_DESK.md, docs/audits/COMBINED_FORENSIC_AUDIT_2026-08-13.md, docs/SERVICE_AUDIT_2026-08-08.md, pine/V18.9_RELEASE_NOTES.md, pine/V18.10_RELEASE_NOTES.md, pine/V18.11_RELEASE_NOTES.md, pine/V18.12_RELEASE_NOTES.md, pine/BREAKOUT_HARNESS_SPEC.md, pine/PINE_v18.9_SPEC.md, app/services/factory.py, app/services/outlook.py
verified_on: 2026-09-16
classification: INTERNAL
---

# Sniper-System platform — validated findings, numbers and verdicts

Every entry names its source and date. Where the repo records a refusal to conclude (CANNOT SEPARATE, NO ROBUST STRATEGY, UNKNOWN, NOT ENOUGH EVIDENCE) that refusal is listed as the finding, because the platform treats it as a first-class outcome.

## The Evidence Law and its vocabulary

The Sniper-System platform's Evidence Law (CLAUDE.md, Quant Lab Law; bot-box CLAUDE.md rule 5): n<20 is luck, n≥20 minimum before PLAUSIBLE, ~100 to judge, Wilson confidence intervals, one organ changed per week. The evidence ladder (`stats.evidence_status`, locked in CHANGELOG 3.1) is the only vocabulary for "winning": EARLY EVIDENCE (n<100) → NO EDGE DEMONSTRATED → REQUIRES CONFIRMATION (CI wide) → PROMISING → ROBUST EDGE. Sample-strength labels (v4.52, informational only): SMALL <50 · DEVELOPING 50–199 · MEASURED ≥200. `MIN_COMPARABLE_N = 100` (`ai_analyst.py`): below this the UI must not declare a winner between lanes.

## Trading evidence inherited from the bot box (CLAUDE.md of brother_sniper_v7 / brother-brain-v2, mirrored in pine/ notes)

- PULLBACK trigger validated: n=640 backtest, out-of-sample PF 1.30–1.45, stop 1.5×ATR (0.8×ATR FAILED validation). Asia is its best session (73.6% WR). Source: bot-box CLAUDE.md "CURRENT EVIDENCE"; pine/V18.10_RELEASE_NOTES.md triage; pine/V18.11_RELEASE_NOTES.md refusal arithmetic (designed TP1 RR 0.67 Asia / 1.20 London-NY, so a 1.6 RR gate would block 100% of fires).
- Fixed 2R take-profits FAILED validation on structural levels; the validated design is the high-win-rate small-R ladder (session TP 1.0/1.8 ATR). Source: bot-box CLAUDE.md.
- SMART_SCALP grades/scores are ANTI-predictive (score≤6 beat 9+; grade B beat A+). Source: bot-box CLAUDE.md. The forensic audit (2026-08-13, BOT-P1-1) notes the Pine-score blend was never normalised (0-9 clamped into 0-100: scores 0→53, 9→56), so the "anti-predictive" finding may be an artefact and must be re-derived after the fix.
- Counter-trend entries are the #1 documented loss driver (SELL bleed −406). Source: bot-box CLAUDE.md; used in CHANGELOG 4.37 as the reason the far bucket must be split by alignment.
- GOLD is the weakest asset (macro-driven); SILVER and US100 are the strongest. Source: bot-box CLAUDE.md. Platform confirmation (CHANGELOG 4.97, live GOLD read): GOLD's adaptive cell is NEGATIVE, −0.062R, n=133.
- FIB-retracement levels: promising challenger (validate PF 1.82, n=62) — watch-list; builds only at PF~1.5+ with n≥100 validate. Source: bot-box CLAUDE.md.
- Baseline every Pine experiment must beat (pine/PINE_v18.9_SPEC.md Section D): STRUCT levels, SL 1.5×ATR, session TP ladder — validated three times (n≈640, OOS PF 1.30–1.45). Breakout harness gate (pine/BREAKOUT_HARNESS_SPEC.md, 2026-08-02): n≥100 per variant out-of-sample, additive PF ≥ 1.3, because the engine trades different days than the pullback baseline.

## Phase 1 dataset (V7 self-dependence plan)

- Phase 1 recorder shipped v4.0 (2026-08-14, 225 tests); dataset fields all ✅ at v4.8 (2026-08-17, 280 tests) when the bot box shipped spread at decision time. Source: docs/V7_SELF_DEPENDENCE_PLAN.md §8.
- Phase-1 exit gate (200 resolved trade candidates) MET: 412 resolved trade candidates, 2,056 observations, every field populated. Source: docs/HANDOVER_V7_DESK.md (2026-08-17); CHANGELOG 4.11 ("412 / 200 resolved trade candidates (100%)").
- Structural finding kept in code and test (CHANGELOG 4.0): for this engine family the stop sits BEYOND the entry, so `invalidated_before_fill` is structurally unreachable and stays False.
- Spread coverage before v4.11 was 16 of 2,056 rows, because the heartbeat posts every ~30 min and the freshness gate (10 min) correctly rejects older samples; the collector now prefers the observed bar's own spread.
- Bot-side Phase-1 coverage at the 2026-08-28 Friday agenda: 14,941 resolved vs target 200 (OPEN_ITEMS "one-time bot-side list", item 8).
- Population growth observed: +5,954 lane observations in 23 minutes, auto-v1 alone +2,571 over 18 symbols (CHANGELOG 4.69), which is why provenance (born live vs replayed) is stamped before any verdict.

## Entry distance (the far-bucket question)

- Buckets: ≤0.5 / 0.5–1 / 1–1.5 / 1.5–3 / >3 ATR, fill rate + expectancy per bucket, `entry_dist_atr` recorded at birth since v3.21 (auto-v1) and v4.52 (tf lanes). Hard-blocking at 1.5 ATR was refused because it "would have deleted the only data that could ever justify 1.5 ATR" (CHANGELOG 3.21).
- Observation: >3 ATR expectancy −0.19R (CHANGELOG 4.37, before the confounder split). Verdict vocabulary of `desk.distance_confounders` (v4.37): DISTANCE SURVIVES / LIKELY COUNTER-TREND / CANNOT SEPARATE (with-trend cell under n=20). Nothing is gated on it.
- Contamination report verdict read live 2026-08-21 22:47 UTC (OPEN_ITEMS, Evidence Integrity item 1): CLEAN SAMPLE SUFFICIENT — 492 of 599 with-trend observations beyond 3 ATR were born outside the timestamp-incident window (2026-08-20 23:50 → 2026-08-21 21:45 UTC, GOLD/SILVER/BTC/ETH).
- Two populations, as the Evidence Authority rule requires: "612 total" (candidates, contamination table) and "n=418" (resolved filled, expectancy) are different populations and are labelled so (CHANGELOG 4.56). The second population — v7's own telemetry with `entry_dist_atr` captured verbatim from Pine — started forward-only on 2026-08-22 (bot commit 89185a3); "nothing touches Pine's Location-Gate max-distance cap until both populations agree".
- The 17 DXY rows flagged by `distance_consistency` were the CHECK's arithmetic, not the data: DXY tick 0.01 ≈ 0.3 of its ATR (~0.03), six times the fixed ±0.05 tolerance; all 17 deltas (0.06–0.20 ATR) sat inside one-tick rounding. Tolerance is now `max(±0.05 ATR, one tick ÷ ATR)` (CHANGELOG 4.61, 2026-08-24, both sides).
- Desk evidence line at v5.11: `EVIDENCE · MEASURED · n=… · expectancy +0.106R` (pooled, resolved filled; under 20 filled it reads LOW SAMPLE).

## Setup-class and lane statistics (examples the repo records)

- Setup-class cells are keyed structure×direction and POOL every symbol; CHANGELOG 4.78 found SILVER and US30 both showing `LH/LL-SELL: n=14 · exp -1.00R` byte-identical, now labelled "(ALL symbols pooled)" with "this symbol alone" beside it, CANNOT SEPARATE when empty.
- Example vocabulary from CHANGELOG 3.1: "HH/HL-BUY: n=7 · exp +0.4R · LOW SAMPLE" or "HISTORICAL EDGE: UNKNOWN — n=0".
- Event-reaction recorder (v4.24): at n=3 the page says NOT ENOUGH EVIDENCE; promotion path n≥30 then a validation split, and any rule lives on the bot box.
- Runner replay (v4.89, `runner-replay-v1`, COUNTERFACTUAL): under n=20 the verdict is CANNOT SEPARATE; above it numbers only — "'better' is the ceremony's word, not this table's". First live runner render (v4.95): TP1 ✓, ≥2R ✓, best 26.9R on a 5-day BTC BUY, shadow MOVE SL 72380.2 → 77976.6 journaled, never sent.

## Strategy Factory / Model Lab verdict rules

- Factory score (CHANGELOG 1.9.1): `OOS_PF − 0.01·maxDD − 0.005·max(0,100−trades)`; gates first: OOS PF ≥ 1.05, ≥30 trades, no overfit flag, Monte Carlo p5 ≥ −35%. Parameter stability: an isolated peak takes −0.15 and is labelled curve-fitting's signature. Champion/challenger from passing variants only; "best of N" printed; NO ROBUST STRATEGY is a verdict with per-variant reasons.
- Research leaderboard (CHANGELOG 1.8.4): 🟢 ROBUST requires OOS PF ≥ 1.1, ≥100 trades, no overfit; never ranks by raw return.
- Model Lab (2.0): chronological 70/15/15 split with H-bar embargo, TRAIN-only standardization, deterministic logistic regression, metrics beside the base rate, calibration as a reliability table.
- Outlook scorecard (v4.53): expired outlooks graded against CLOSED 1d candles of their own window; a window under 60% stored (`COVERAGE_FLOOR = 0.6`) refuses the negative and stays UNKNOWN; a forming daily never grades.

## Data-integrity findings with numbers

- Timestamp incident 2026-08-20 23:50–00:16 UTC: one manual run, XAUUSD/XAGUSD/BTCUSD/part of ETHUSD, reporter inferred +2h (truth +3h). The audit then read every row: 30,209 off-grid rows, bar dates back to 2007 and 2011, direction MIXED (GOLD dailies at 00:00 UTC = the old "Assuming 0" fallback; 4h rows at +3600s) — at least two bad episodes. Source: OPEN_ITEMS "DATA INCIDENT", CHANGELOG 4.41–4.42.
- SCALAR_SUSPECTED on every multi-season series: SILVER's 11,375 dailies held ONE residue (21:00 UTC) from 2007 to 2026, "which a season-aware series is arithmetically incapable of producing" (CHANGELOG 4.42). Purge gate held: `BLOCKED — 30,209 candidate rows, 0 safe to delete`.
- Depth probe 2026-08-21 (CHANGELOG 4.45/4.46): GOLD 1d stored 7,684 / flagged 201 / MT5 serves 7,483 (exact); SILVER 1d 11,375 / 5,101 / 6,274; BTC 1d 8,960 / 4,305 / 4,655; ETH 1d 3,465 / 200 / 3,265 — `stored − flagged == MT5 serves` on all four, independent proof the flagged rows were never bars. GOLD 1d history starts 1998-04-21; XAUUSD 4h reaches 2002-08-28.
- Rebuild pilot (CHANGELOG 4.47): GOLD 1d refilled through the per-bar writer came back `SEASON_AWARE: summer={75600: 4436} winter={79200: 3047}` — two grids one hour apart, "the shape this database had never once contained".
- Trade twins (CHANGELOG 5.23, migration applied 2026-09-03 10:35 UTC): rows 155 and 156 for ticket 1900277473 created 70 ms apart by two of five concurrent reporter processes; the dry run found 8 twin groups, 0 refused; `uq_trade_ticket` partial index created; `open_rows_for_ticket = 0`.
- US10Y feed: 12,949 rows over 19 months, stopped 2026-08-27 20:58 UTC — the instrument ended (broker contract roll with no successor), confirmed on both terminals 2026-09-02 (`RETIRED_SYMBOLS`, CHANGELOG 5.05).
- Bot-side relays measured by the watchers 2026-09-01 (OPEN_ITEMS): US10Y candle feed dead 122h (INC-0001); bias push stopped USA500 34d, USOIL 20d, XRPUSD 19d (INC-0002); VPS heartbeat rows ~38 days old and identical — later shown to be demo rows written once on 2026-07-25 (CHANGELOG 5.06).
- Sensor-version population baseline 2026-09-02 (OPEN_ITEMS watch-item 3): 439 unstamped · 17 v18.12 · 15 session_caller; pass if it freezes at 439 and new rows arrive stamped 18.13.
- NVDA Phase-0 baseline 2026-09-02 ~17:00 UTC: 101 rows of 15m candles under `NVDA`, 0 under `NVDA.%`, 6 lane observations, no `market_bias` row yet.
- Bias-gap baseline at the bot-side fix (c378012, 2026-09-02): XRP 1d, SILVER 2d, US100 5d stale; prediction "XRP refreshes next cycle; SILVER/US100 once the bridge serves enough bars" held (CHANGELOG 5.22: `pushed=15 … updated: 15, refused: []`).

## Performance measurements on the box

- 2026-08-26 bot-session diagnosis: timeouts at 0.35% CPU with 271 GB DB NET OUT = request queuing, not computation (CHANGELOG 4.82). Fix: 60s read-model cache, 4 uvicorn workers, sweeper off the event loop, market clock frozen only while closed.
- `scripts.page_timing` on 896,009 candles and 25,092 lane observations (CHANGELOG 4.75): mgmt panel 275 ms with an open position vs 35 ms without; adaptive symbol_card 110–246 ms → 38 ms after column trimming; ETH mgmt panel 451 ms → SQL aggregates (4.76).
- v5.12 measurement: `desk_view` 127.9 ms, `desk_summary` 2,179.8 ms, DESK TOTAL 2,307.7 ms; the "cheap" read model was the Lab's 2,457 ms aggregation, now cached 10 min and warmed by the sweeper; expected /desk ≈ 130 ms.

## Audit verdicts (2026-08-08 and 2026-08-13)

- Service audit 2026-08-08: the two bots CANNOT cross-execute at config level (v7's executor pins its own terminal path; no cross-credentials; the platform cannot execute). Canonical candle source `mt5:52834417`. Confirmed problems: duplicate 52901228 registration under a different platform user; both MT5 accounts stored with TRADING passwords (should be investor passwords); an API key exposed in chat.
- Combined forensic audit 2026-08-13: platform SAFE WITH FIXES (163 tests then), bot box NOT READY (seven P0s, three reproduced by execution), the interface the weakest link (`pine_signal_id` only on an unmerged brain branch). Platform P0s PLAT-P0-1/2/3 and P1-1/2, P2-1 were all fixed in v3.2 (170 tests). Bot box: 39 gates documented, 11 emit nothing countable.

## Standing refusals to conclude (recorded as outcomes, not gaps)

- `feed_diag` SYMBOL_ONLY: a stopped feed and a broker session break look identical in stored candles — CANNOT_SEPARATE, and the platform has no model of a broker's daily maintenance break until a per-symbol histogram of bar stops is measured (OPEN_ITEMS, v5.16).
- Price alone cannot tell whether a limit order filled — a broker fact (V7_FACT); the desk states the caveat instead of inferring it (v5.17, correcting v4.36).
- Whether the bot's fail-soft exception to Iron Rule 1 should be kept is Shyam's call (v5.18).
- The earnings date for a single stock stays UNKNOWN until the calendar carries a MAJOR_EARNINGS row (v5.09).
- v18 bias push says US10Y BEARISH while Pine's AssetPulse shows bullish (2026-08-28): "two sensors disagreeing is a SOURCE question, not a display bug" — reconciled at the source, not averaged here.
- The counterfactual "do gates protect or suffocate" number (PLAT-CF-1) is not yet computed; nothing in the repo replays refused signals as of 2026-08-20 ("No counterfactual lane exists here").
