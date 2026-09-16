---
title: Sniper-System platform open items
domain: platform
repo: sabuj14eu/Sniper-System
sources: docs/OPEN_ITEMS.md, docs/HANDOFF_PLATFORM_SESSION.md, docs/CHANGELOG.md, docs/V7_SELF_DEPENDENCE_PLAN.md
verified_on: 2026-09-16
classification: INTERNAL
---

# Sniper-System platform — deferred work, as the repo carries it

The Sniper-System platform's rule for deferred work (CLAUDE.md, docs/OPEN_ITEMS.md): "An item deferred in conversation is an item forgotten — if it is not in that file, it does not exist." An entry is deleted only when done and verified, with the proof named. Status below is as of docs/OPEN_ITEMS.md "START HERE (new session, 2026-09-02 23:30 UTC)" and the v5.24 handoff; the repo has no later record.

## State at handoff (OPEN_ITEMS "START HERE", HANDOFF §3)

- Platform v5.24 ready; v5.23 LIVE with its migration applied 2026-09-03 10:35 UTC (8 twin groups removed, `uq_trade_ticket` present, `open_rows_for_ticket = 0`, GOLD ghost #1900277473 cleared). Test count 721 (OPEN_ITEMS) / 723 (HANDOFF and CHANGELOG 5.24). No migration pending.
- Three days of screen-honesty fixes shipped (v5.14–v5.17); CHANGELOG 5.16 and 5.17 are "the working description of how this system fails".
- FAIL-SOFT visible (v5.18); keeping the brain's bounded exception to Iron Rule 1 is Shyam's call.
- Bias gaps CLOSED 2026-09-03 09:30 (SILVER, US100 refreshed; XRP LIVE); XRPUSD/USA500/USOIL RETIRED by Shyam (C11 done).
- Nothing about the trading logic changed and nothing may.

## Pending — Shyam's, no deadline (HANDOFF §4)

- Two MT5 clicks: close GOLD #1900277473 (later cleared on its own per OPEN_ITEMS); the SILVER orphan stop.
- INC-0001 APPROVE/RESOLVE and INC-0003 RESOLVE on `/admin/engineering`.
- DD-guard numbers: the bot-side EquityGuard is effectively OFF (0.99); real limits require Shyam to NAME them (their example: daily 5% / weekly 10% / total 20%); Iron Rule 3 forbids inventing them.
- PLAT-EXPOSURE-1: NVDA and US100 as ONE exposure on any page that sums risk — a risk-semantics change that ships alone, with tests, as his logged decision.
- PULLBACK through v7: bot session recommends leaving it (auto_live IS the pullback engine, collecting in shadow); revisit Friday.
- Delete the USOIL alert in TradingView (30s). Secret rotations at the finish line (PLAT-SEC-1).

## Pending — the platform's, when asked (HANDOFF §5, OPEN_ITEMS)

- **PLAT-HOLDOUT-1** — the Model Lab holdout re-arms on every retrain (Quant Lab Law breach, opened 2026-08-31, bot-session audit #7). Ships alone with tests proving a second spend is refused; the delicate part is defining a NEW experiment. "The one real debt."
- **Startup schema guard** — code ahead of its migration is DOWN, not degraded; the app should refuse to start rather than 500 everywhere.
- **Legend audit** — the desk legend documents states nothing tests; render every documented state once. Three screen-vs-legend disagreements in four days (v5.16 EMA, v5.17 PASSED, v5.19 POSITION OPEN). "Now the top platform debt."
- Identity journal (B9 — new table + migration). Spread history (A5 — schema; only the newest spread sample is stored, so regular vs after-hours cannot be shown side by side, v5.09).
- `trades.updated_at` — add the next time `trades` is migrated for another reason (v5.23 watch-item).
- **PLAT-CF-1** — the counterfactual classifier over WAIT lane observations (replay refused candidates through the same fixed resolve rules, cut by the refusing gate, CANNOT SEPARATE under the floor, labelled COUNTERFACTUAL). Accepted 2026-08-30 for "the next platform release", harness-style offline first. Not built as of v5.24.
- **Item 11: macro transmission read model** — event → T+1D/5D/20D legs (DXY, US10Y, asset) from stored 1d candles over `event_reactions`; read model only, no schema.
- **ICT feature layer**, dark, queued in order FVG → Order Block → CISD → Rejection Block → Opening Gap, as columns on lane observations like `entry_dist_atr`; one per week after the collection week.
- Recording trend context INTO evidence rows (alignment leg #2) — future organ.
- 5-minute candles if T+5 is wanted (config `BB_CANDLE_TFS`, no code).
- The management ruleset `mgmt-v1` and NY machine `ny-v1` stay labelled UNVALIDATED until `desk_messages` is replayed against outcomes in Phase 2.
- A broker daily-maintenance-break model (the ~21:00 metals gap) waits for measured per-symbol bar-stop histograms, never a hardcoded table.
- The macro panel still shows retired US10Y as UNKNOWN without its reason (v5.05 known limitation).

## Security — deferred by explicit user decision

**PLAT-SEC-1** — rotate the shared secrets that have been through a chat window: the v7 webhook secret (`BB_BRAIN_WEBHOOK_SECRET`, pasted weeks ago), the bridge key (issued 2026-08-19), and the MT5 reporter API key (pasted in full 2026-08-21; carries heartbeat-write permission, so rotation is create key → `nssm edit` env → restart → revoke old). Also from the 2026-08-08 audit: both MT5 accounts stored with TRADING passwords (re-save with INVESTOR passwords). Status: deferred while everything is DEMO — "Do this before any real-money account exists, not after." Rotation procedures are written in OPEN_ITEMS and DEPLOYMENT.md §10.

## Watch-items (observation only, each with its falsifier)

1. Outlook scorecard grades after expiry — finding if the weekly written 26 Aug (expired 2026-09-02 18:08 UTC) had not appeared in the scorecard by the morning of 2026-09-03. Outcome: UNKNOWN in the repo.
2. Auto-weekly successor at expiry — finding if the desk shows a GAP (the honest display; nudge the bot box). Outcome: UNKNOWN in the repo.
3. UNSTAMPED sensor count must stop growing — baseline 2026-09-02: 439 unstamped · 17 v18.12 · 15 session_caller; pass if it freezes at 439 and new rows arrive stamped 18.13. Outcome: UNKNOWN in the repo.
4. NVDA Phase-0 falsifiers (baseline 2026-09-02): any row under `NVDA.%` in candles; lane observations stop growing while 15m candles keep arriving; trend context still "insufficient history" past ~200 closed 15m bars (~3 trading days). Decision in ~four weeks is Shyam's.
5. `feed-diag-v1` — finding if a SYMBOL_ONLY turns out to have been platform-wide, or FEED_WIDE fires while peers are current.
6. DXY 1d feed — flag as stalled if the daily series had not advanced past 2026-08-20 by Tuesday 2026-08-25. Outcome: UNKNOWN in the repo.
7. FALLBACK_ID share on /funnel should fall toward zero after the brain adopted Pine's id (brain commit 6063676, 2026-08-22); "if it has not fallen within a few trading days, that is a FINDING." The v5.00 `fallback_id` watcher (>20% RED) measures it.
8. Trade closes into the mirror (deployed 2026-08-24): verify the next real close drops its levels off /chart within a minute, not at the 12h TTL.

## Bot-box items the platform is waiting on (OPEN_ITEMS ledger)

- BOT-P0-1 journal outcomes — CLOSED 2026-08-19 both sides (202 trades backfilled; platform status vocabulary fixed v4.18).
- BOT-P0-2 canonical `signal_id` — BOT SIDE DONE (brain 6063676); platform acceptance watch on FALLBACK_ID share.
- `entry_dist_atr` into v7 telemetry — DONE (v7 89185a3, deployed 2026-08-22 01:27), forward-only; second population clock started.
- Outlook posts — `post_outlook.py` built bot-side; ABSENT chips correct until posts arrive. Auto-weekly cron Sunday 21:30 UTC ("bot box auto-weekly-v1").
- Executor file: the bot box must send `sniper_executor.py` with the sha256 of the bytes as sent (nssm's UTF-16 console broke the first attempt); `/downloads/sniper-executor.py` 404s honestly until a hash-verified copy lands.
- Periodic spread sampler spec (build only if Shyam wants it): POST `/webhooks/brain/bias` items with exactly `symbol, spread, spread_points, spread_source: "mt5_tick_sampler", spread_at` at least every 10 minutes per open symbol; no other keys.
- BOT-NEWS-1 partially closed 2026-08-26 (GDP/PCE flowing); MAJOR_EARNINGS rows (Nvidia → US100 playbook) still not seen.
- US10Y direction conflict (brain push BEARISH vs Pine AssetPulse bullish, 2026-08-28) — reconcile at the source.
- Weekly readiness push (v4.83): one POST to `/webhooks/brain/artifact` (kind "doc", path containing AUTONOMY_READINESS) after the Sunday report; `/readiness` goes ⛔ OVERDUE at 8 days.
- v4.82 perf order: measure `python -m scripts.page_timing GOLD SILVER ETH` after deploy against the 2026-08-26 numbers.
- Friday agenda (2026-08-29): GOLD verdict (⚖️ /v7 card + their journal), gate counterfactuals, Phase 1 formal close (their coverage 14,941 resolved vs target 200). Outcome: UNKNOWN in the repo.
- Git↔Production: boxes must send `git_commit`/`file_sha256` in heartbeats before the check can say MATCH (reporter 1.7.0 does; other services UNKNOWN).
- VPS heartbeat rows ~38 days old — resolved as demo rows written once (v5.06).
- Pine provenance (PINE-1): `pinev18.6` is an empty repo and brother-brain-v2 holds a stale v18.7 copy; the real v18.12 lives in `Sniper-System/pine/`, and only `pine_ver` on the journal proves what is live. Deleting/marking the stale copies is bot-box housekeeping.
- Broker instrument facts (probe 2026-08-17): LINKUSD does not exist on the account; SOLUSD volume_min/step 1.0 (whole lots); ADAUSD volume_min 100; SOLUSD `digits` still unconfirmed (display precision SOL=3 is an assumption).
- The alert ceremony for v18.13 (delete + recreate every alert) — still owed as of 2026-08-31; if the ⚠ returns, capture the one-line red text first.
- Timestamp incident rebuild: reporter v1.5.0 built; GOLD 1d rebuilt SEASON_AWARE (v4.47); whether SILVER/BTC/ETH 4h/1d were fully wiped and rebuilt on production is UNKNOWN in the repo (OPEN_ITEMS still lists the rebuild as ⬜ with the ordered steps; the CHANGELOG records only the GOLD pilot).
- Shyam's Windows-box tasks recorded 2026-08-20: `Restart-Service BrotherBotReporter` after the backfill; run `python mt5_reporter.py backfill` with `BB_BACKFILL_BARS=5000` for young feeds (DXY 464 rows, US10Y 474, XRP/LTC/GBPUSD ~400).

## What is NOT in this repo (checked 2026-08-20)

- No counterfactual lane exists (PLAT-CF-1 is unbuilt work).
- `setup_edge` is a RENDERER of the bot box's artifact, not a computation.
- Genuinely platform-side and real: `market_memory` (v4.2), `reaction` (v4.24), `collector` (v4.0), `desk.distance_confounders` (v4.37).

## Phase ledger (docs/V7_SELF_DEPENDENCE_PLAN.md §8)

Phase 1 COLLECT: recorder shipped v4.0; dataset complete v4.8; exit gate met (412 resolved) by 2026-08-17; "complete as engineering on both sides" per OPEN_ITEMS 2026-08-17 review. Phase 2 ANALYZE, Phase 3 TRAIN, Phase 4 SHADOW, Phase 5 CONTROLLED DEPLOYMENT: not started. The plan's §8 ledger was last updated 2026-08-17 and does not carry the later Phase-2 preparatory work (evidence lab, condition cuts) — a documentation gap, not a code one.
