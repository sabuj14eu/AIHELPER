---
title: Brother Sniper v7 — architecture and data flow
domain: v7
repo: sabuj14eu/brother_sniper_v7
sources: bot.py, sniper_executor.py, gunicorn.conf.py, core/ic_markets.py, core/sl_engine.py, core/v7_status.py, core/signal_memory.py, filters/ai_filter.py, filters/news_gate.py, filters/freshness_gate.py, filters/deepseek_vote.py, filters/news_semantic.py, risk/equity_guard.py, governance/discipline.py, learning/weight_engine.py, learning/cluster_engine.py, learning/regime_detector.py, learning/trade_memory.py, learning/telemetry.py, learning/platform_mirror.py, learning/strategy_dna.py, learning/conditional_profile.py, learning/signal_bus.py, learning/vote_worker.py, learning/brain_scorer.py, learning/consult_brain.py, utils/asset_gate.py, auto_live.py, post_outlook.py, post_readiness.py, post_incident.py, post_weekly_outlooks.py, autonomy_scorecard.py, docs/STRATEGY_INTELLIGENCE.md, docs/SESSION_COORDINATION.md, docs/PINE_UPDATE_NOTE.md, docs/A2_NGINX_MIRROR_SECRET.md
verified_on: 2026-09-16
classification: INTERNAL
---

# End-to-end data flow of the v7 bot

Pine alert -> `brain.signalmesh.dev/webhook/v18` -> nginx mirror ->
`127.0.0.1:5000/webhook` (v7 bot, gunicorn 1 worker x 4 threads) ->
`_guard` (IP allowlist, XFF from loopback only, 10 req/min/IP) ->
`_header_secret` (A2) -> `handle_signal` (the gate chain below) ->
`ICMarketsClient.open_trade` -> `POST EXECUTOR_URL` (`/execute` on the
Windows bridge `:5001`) -> `mt5.order_send` on account 52834417 -> response
with fill facts -> slot state (`state.json`), journal (`learning/trades.jsonl`),
telemetry (`learning/telemetry.jsonl`), Telegram -> `webhook()` post-hooks:
reject telemetry + `record_decision` (`learning/decisions.jsonl`,
`learning/v7_status.json`, POST to the platform). A 60 s monitor thread
manages open tickets (BE at +1R, MAE/MFE, close detection, heartbeat).

# The handle_signal gate chain, in execution order (bot.py)

1. **Secret**: auto-inject `WEBHOOK_SECRET` for trusted Pine systems (BSv16/
   17/18/11, `version` v9*, `bot` BS_*); mismatch -> `unauthorized`.
2. **Record all signals** in `core.signal_memory` before validation
   (`signal_memory.json`, stores `htf_align` with `htf_agree` fallback, C2).
3. **Optional HMAC** (`TV_HMAC_SECRET`, header `X-Webhook-Token`).
4. **Redacted raw log** `[WEBHOOK RAW]` (secret shown as `***`).
5. **v17 noise filter**: `signal` INFO/WARN or `type` in SCALP, MICRO,
   BOS_UP/DOWN, ALL_TF_BULL/BEAR, LIQ_SWEEP_*, *_INDUCEMENT -> `ignored`.
6. **BSv17/BSv18 quality gate**: `type` must be `SMART_SCALP` (C4: PULLBACK
   stays v18-only on purpose), `grade` in A/A+/B, `v4_rr` True; then a
   Telegram "v18 signal" notice and fall-through.
7. **Field parsing**: symbol via `SYMBOL_MAP` (exchange prefix stripped);
   direction from `direction` | `signal` | `action`; `entry`; `sl`; TP-FLOOR
   rule (tp1 if >= 1.0R, else tp2, else tp1/tp); GATE-PRICE per-symbol
   sanity ranges (e.g. GOLD 1000–10000, EURUSD 0.5–3.0); DIR-FLIP reject on
   inverted SL/TP; no SL -> reject (F7 2026-07-02, "auto-SL fabrication
   removed"); no TP -> 3R auto-TP; `atr` from payload else `fetch_atr`
   (bridge `/candles`, 15m, ATR(14), stale guard 3 bars); `swing_low/high`;
   `htf_trend` = `htf_trend` or `trend`; flow-vector log (`learning/
   flow_vector.jsonl`); `pine_score` (None for v17/18, else pine_score|score);
   breakout_prob/strength/dir; `signal_age_seconds_v` from `time` (ms or s);
   atr_pct, atr_vs_avg (or from vol_regime HIGH 1.5/MEDIUM 1.0/LOW 0.5), adx,
   bb_width.
8. **Symbol allowed** (`ALLOWED_SYMBOLS`) -> else `unsupported`.
9. **Asset gate** (`utils/asset_gate.py`, off by default) -> `skipped`.
10. **Direction and prices** valid.
11. **Dedupe**: `sid = _make_sid(payload)`; `_is_dup` within
    `SIGNAL_DEDUP_MIN = 10` minutes -> `skipped: duplicate`; `_mark_seen`.
12. **Paused / streak**: `state.paused` or `consecutive_losses >= 3` ->
    `paused — POST /reset`.
13. **Per-asset-class slot** (metals / crypto / forex / other): one open
    trade per class -> `skipped: <class> slot already open`.
14. **GATE-MARGIN** (fail-closed): balance None or < `MARGIN_FLOOR = 500.0`
    -> `skipped: margin floor / balance unreadable`.
15. **Priority 1 EquityGuard** (`risk/equity_guard.py`) -> `blocked`.
16. **Priority 2 News** (NEWS01) -> `blocked` unless mode observe (trade
    proceeds, verdict captured as `news_observe`).
17. **Priority 3 Regime** (`learning/regime_detector.py`).
18. **Priority 4 Discipline / EV gate** (cluster lookup + governor) -> `blocked`.
19. **Priority 5 AI filter** `score_signal` -> `filtered`.
20. **AI-SHADOW emit** to `learning/signal_bus.jsonl` (never enforced).
21. **Priority 6 SL engine** + trust mode + floor + widen-reject -> `rejected`.
22. **Priority 7 R:R** `validate_rr(..., MIN_RR = 1.0)` -> `rejected`.
23. **Priority 8 sizing**: `effective_risk = guard.risk_pct x regime.risk_scale
    x disc.position_scale x cluster_scale`, clamped to [0.003, 0.01], then
    `x _ag_mult` (asset gate, applied AFTER the floor); `calc_lot`.
24. **Freshness gate v1** (shadow default; `enforce` -> `blocked` with
    `DECISION BLOCKED — DATA FRESHNESS`).
25. **Execute** via the bridge; on success: slot, `mem_open(TradeRecord)`,
    telemetry `capture_open`, Telegram, return `ok`. On exception: RECONCILE
    (sleep 2 s, read `/positions`, adopt a position whose comment is
    `BS_<sid>`; RECOVERY_CONFLICT alerts for extras).

Result statuses: `ok`, `ignored`, `rejected`, `blocked`, `filtered`,
`skipped`, `paused`, `error`. `core/v7_status.classify_gate` maps
(status, msg-regex) to gate tags GATE-GRADE, GATE-V4RR, GATE-PRICE,
GATE-DIRECTION, GATE-SL-MISSING, GATE-SL-SANITY, GATE-SL-FLOOR, GATE-RR,
GATE-SL-LIMITS, GATE-DEDUP, GATE-ASSET-BENCH, GATE-SLOT, GATE-MARGIN,
GATE-SKIP, GATE-PAUSED, GATE-NEWS, GATE-EV, GATE-EQUITY-GUARD, GATE-AI-FILTER,
ERROR, with stances TRADE / WAIT / REJECT / ERROR.

# The Pine payload fields the v7 bot reads (append-only contract)

Base contract (never renamed): system, signal, direction, signal_id, symbol,
tf, entry, sl, tp, tp1, tp2, rr, grade. Also read by v7: type, time, atr,
trend / htf_trend, entry_dist_atr (v18.12), structure (v18.13: "HH/HL" |
"LH/LL" | "MIXED"), pine_ver (since v18.8), score / pine_score, session,
v4_rr, htf_align (htf_agree legacy), zone / loc_zone, dxy_dir, yield_dir,
vol_regime, adx, rsi, bb_width, atr_pct, atr_vs_avg, macro_score, trend_day,
ny_regime, oil_spike, news_window, breakout_prob / breakout_strength /
breakout_dir, swing_low / swing_high, version, bot, action, secret. The
mirror also forwards payload_schema and fired_at (OPEN_ITEMS C3). "Never
change the MEANING of an existing field (a silent semantic change is worse
than a rename)" (docs/PINE_UPDATE_NOTE.md).

# Dedupe and identity keys (bot side)

`_make_sid(p)`: if the payload carries `signal_id`, the key is
`f"{symbol}:{signal_id}"` (C1, 2026-09-02: Pine ids like `SS-BUY-<ts>` carry
no symbol, so two symbols on the same bar collided); otherwise
`sha256(f"{symbol}-{direction}-{round(entry,2)}")[:16]`. The persisted key in
`state.json["seen_signal_ids"]` is `f"{V7_MT5_LOGIN}:{sid}"` (ISO-08,
2026-09-15). The order comment sent to the bridge is `BS_<sid>` as
`signal_id`; the bridge stamps the MT5 comment `"BS_" + md5(signal_id)[:8]`
and magic 70007. `core/v7_status.broker_comment(signal_id)` reproduces the
bridge formula so decision records and heartbeat slots carry `broker_comment`
(V7ATTR01, 2026-09-15). `decision_id = sha256(f"{V7_MT5_LOGIN}:{signal_id}:
{status}:{msg}:{ts}")[:16]` identifies one evaluation.

The platform receives v7 under TWO namespaces (forked contract, 08-19):
`core/v7_status.record_decision` posts the RAW Pine id to
`/webhooks/brain/decision`; `learning/platform_mirror` posts `v7-<id>` to
`/webhooks/brain/signal` (closes via `mirror_v7_close`, and the platform's
`pine_signal_id` join key). Query both when asking "did the platform get X".

# The equity guard (risk/equity_guard.py)

`EquityState` tracks peak, day-open and week-open balances, day/week PnL,
`hard_stopped`, the last 50 trades and the owning `account` (ISO-07). Limits:
`DAILY_DD_LIMIT_PCT = TOTAL_DD_LIMIT_PCT = WEEKLY_DD_LIMIT_PCT = 0.99`
("effectively OFF — a deliberate, logged demo decision by Shyam", A6; a
startup warning says so). `check(bal, consecutive_losses, max_losses=3)`:
None balance -> blocked "balance UNKNOWN" before any state is touched; hard
stop; total/weekly/daily limits; streak >= 3; then `RISK_SCALE_TABLE`:
equity >= 90% of peak -> 1.0% risk, >= 80% -> 0.75%, >= 70% -> 0.5%, below ->
0 ("Equity below 70pct floor"). `/reset` clears the streak/pause/hard-stop and
resets a stale peak (> 30% above real balance).

# Regime, clusters, discipline and weights (the learning layer)

- `learning/regime_detector.detect_regime` votes TREND / RANGE / VOLATILE
  from adx, atr_vs_avg, atr_pct, bb_width, htf_trend; each regime carries
  `atr_multiplier` (1.2 / 0.9 / 1.8), `score_threshold` (50 / 58 / 68; the
  filter runs in "PILOT MODE" and ignores it) and `risk_scale` (1.0 / 0.85 /
  0.5). UNKNOWN when no indicator is present.
- `learning/cluster_engine`: key `symbol_session_regime_vol` (vol state from
  atr_vs_avg: spike > 2.0, high > 1.3, normal >= 0.7, low); a cluster is
  used at `MIN_CLUSTER_TRADES = 8`, trusted when confidence
  `n/(8*3) >= 0.60`; `ev` is the cluster expectancy; store `learning/clusters.json`.
- `governance/discipline.DisciplineGovernor`: `MAX_WEIGHT_DELTA 0.25` per
  calibration, weights FREEZE when daily DD > 4% (`FREEZE_DD_THRESHOLD`),
  unfreeze below 2%, `DECAY_DAYS 30` with `DECAY_CAP 0.40`, `MIN_EV_FLOOR
  -0.5` (EV gate), regime-confidence position scale 1.00 / 0.75 / 0.50 at
  0.65 / 0.40 / below. State file `governance/discipline_state.json`.
- `learning/weight_engine`: six factor weights (session, news, rr,
  atr_context, trend, volatility) in `learning/weights.json`, `MIN_SAMPLES
  20`, `EMA_ALPHA 0.3`, clamp [0.30, 2.00], `DEFAULT_THRESHOLD 5`;
  `recalibrate()` runs from the calibration worker every 24 h and `/recalibrate`.
- Cluster sizing scale in bot.py: n < 10 -> 0.25x, n < 30 -> 0.50x, else 1.0x
  (the "learning-phase sizing" the adaptive-gates spec names as CAUTION).
  Finding G-2 (unfixed by decision): the `max(0.003, ...)` floor re-inflates
  the 0.25x/0.5x scale (0.5% x 0.25 = 0.125% -> 0.3%).

# The AI filter (filters/ai_filter.py)

`score_signal` sums six factors with maxima session 25, news 20, rr 20,
atr_context 15, trend 10, volatility 10, each multiplied by its learned
weight. Session scores overlap 25 / london 20 / new_york 18 / asian 10 /
dead 0 from DST-aware exchange clocks (`_get_session`: LSE 08:00–16:30
Europe/London, NYSE 09:30–16:00 America/New_York, Tokyo 09:00–18:00
Asia/Tokyo; F9 2026-07-02 replaced a static-UTC table). News: unknown 15,
< 30 min 0, < 60 min 8, < 120 min 14, else 20. R:R: >= 3.0 -> 20, >= 2.0 ->
16, >= 1.5 -> 10, >= 1.0 -> 4. ATR context: ratio sl/atr 0.8–2.0 -> 15,
no ATR -> 12 neutral. Trend: with 10, range 6, unknown 5, counter 0.
Non-v18 `pine_score` blends 30%. Confirmed counter-trend multiplies the final
score by 0.65 (F8; `F8_CT_50=true` makes it 0.50, default off). `passed =
final >= threshold`; `recommended = final >= threshold + 15`. Model vote:
shadow only (ISO-24), never asked on a news-flagged block (F6).

# SL engine, trust mode and R:R (core/sl_engine.py, bot.py)

`calculate_institutional_sl`: anchor = swing (if beyond entry) else raw SL,
minus/plus `ATR_MULTIPLIER 1.2 x ATR` and a per-symbol `FAKEOUT_PAD` (GOLD 8.0,
SILVER 0.12, BTC 300, ETH 25, forex 0.0005, US30/USTEC 3.0); floors
`MIN_SL_PCT` (GOLD/SILVER 1.0%, BTC 1.2%, ETH 1.5%, forex 0.10%, indices
0.15%; "metals floors raised 2026-06-26: <1% stops bled -432 (17%WR) vs >1%
+280 (80%WR)"); caps `MAX_SL_PCT` -> rejection. Known defect G-1: `sl_final =
round(sl_raw, 2)` corrupts 5-digit forex SLs on the institutional path.

TRUST MODE applies for BSv17/BSv18/BSv11 or v9.x with score >= 7: sanity band
0.02% (v18) / 0.05% (v9) to 8% of price; floor = 1.2 x live M15 ATR (F9
2026-07-10; legacy engine floor when ATR unknown); if the floor exceeds
1.6 x Pine's stop the signal is REJECTED ("R:R collapsed", F2 2026-07-02);
otherwise the SL is widened to the floor and TP is left as Pine sent it
(TP-inflation removed 2026-06-25). `validate_rr` requires `MIN_RR = 1.0`
(was 0.5; "bot was live-trading 0.63R setups").

# Execution client and bridge contract (core/ic_markets.py, sniper_executor.py)

`ICMarketsClient` is an HTTP client (the class name `xtb` is historical; the
XTB socket client was removed 2026-08-01). `open_trade` maps GOLD->XAUUSD etc.
(`SYMBOL_MAP_CT`), caps lots by `DEMO_MAX_LOT` (GOLD/SILVER 0.50, BTC 0.10,
ETH 0.50, forex/indices 1.00) with `MIN_LOT` 0.10 for US30/USTEC/US500, checks
`is_market_open` (crypto 24/7; metals/forex closed Sat, Sun before 22:00 UTC,
Fri after 22:00 UTC), and POSTs `{secret, symbol, direction, lot, sl, tp,
signal_id: "BS_<sid>", account_id: V7_MT5_LOGIN}` with a 15 s timeout.
Bridge `/execute` checks: secret (403), `account_id` present (400
`no_account_id`) and equal to `V7_MT5_LOGIN` (403 `account_mismatch`), global
stop CLEAR (503 `global_stop`), numeric/NaN sanity, direction, `ensure_mt5`
(503), `symbol_select`, tick, then the seen-store (400 `no_signal_id`, 503
`seen_store_unknown`, 409 `duplicate_signal`), then `order_send` with
`ORDER_FILLING_IOC`, `magic = V7_MAGIC`. Success (retcode 10009) returns
`order_id, volume, price, requested_price, fill_price, slippage` (positive =
filled worse), `bid, ask, spread, latency_ms, retcode, retry_count, requotes`.
`get_balance` / `get_account` read the bridge `/health` (`account, balance,
equity, trade_mode` 0 demo / 1 contest / 2 real, `global_stop, git_commit,
service_version`); None = UNKNOWN.

# The monitor thread (bot.py `_monitor`, every 60 s)

1. `[SLOT-RECON]`: read `/positions`; adopt untracked positions whose comment
   starts `BS_` into a free slot as `ADOPTED_<ticket>` (Telegram "Orphan
   adopted"); conflict alert if the slot is busy. `bridge_ok` = the sweep
   reached the bridge.
2. `update_heartbeat(state, equity_guard.to_dict(), bridge_ok, symbols_enabled,
   account_login, trade_mode)` every cycle (display-only).
3. If any slot is open: fetch `/positions` ONCE; non-200 or no `positions` key
   -> "positions UNKNOWN ... skipping cycle" (truth guard). For each tracked
   ticket still open: accumulate MAE/MFE from `price_current` (persisted);
   at +1R move SL to entry +/- 5% of risk if `_tighter` (BE-ONLY; the 50%
   partial branch is `if False`, disabled at 0.01 lots). For a ticket gone:
   fetch `/history?hours=24` (cached across slots); missing deal -> hold the
   slot up to 10 cycles, then an UNVERIFIED fallback close at entry that
   counts neither as a loss nor a streak; real deal -> net = profit + swap +
   commission, W/L counters, `mem_close(... be_done, partial_done, mae, mfe)`,
   `equity_guard.record_trade`, `mirror_v7_close`, Telegram, then pause if
   streak >= 3 or the guard blocks.

Other threads: keepalive (ping every 90 s), spec worker (refresh symbol specs
every 6 h), calibration worker (recalibrate every 24 h; skipped on UNKNOWN
balance).

# HTTP routes of the v7 bot (bot.py)

`POST /webhook` (signals); `GET /health` (no auth; `status ok|degraded`,
`balance`, `balance_state MEASURED|UNKNOWN`, slots, guard, weights,
discipline, `git_commit`, `service_version: v7-bot`; 503 when degraded);
`GET /clusters?secret=`, `GET /stats?secret=`, `GET /status?secret=`;
`POST /recalibrate` (503 on UNKNOWN balance), `POST /reset`, `POST /close`
(`asset_class` metals|crypto|forex|other|all) — all secret-gated.

# Journal and state files (what lives where)

- `state.json` — slots (`open_trades` by class), counters, `paused`,
  `seen_signal_ids`, `equity` (guard dict). Written atomically.
- `signal_memory.json` — every raw signal (RAM ring persisted).
- `learning/trades.jsonl` — `_type: open` rows (TradeRecord: ~40 fields
  incl. entry/raw_sl/inst_sl/tp/rr/session/atr_ratio/sl_method/htf_trend/
  trend_aligned/news_minutes/pine_score/ai_score/score_breakdown/
  balance_at_open/risk_pct/lot/asset_class/breakout_*/signal_age_bars/regime)
  and `_type: close` rows (close_price, gross/swap/commission/net_profit, won,
  hold_time_seconds, mae, mfe, be_done, partial_done). Version tag `v8`.
- `learning/telemetry.jsonl` — one row per open and per reject with the
  stable schema groups ids / versions / market (incl. entry_dist_atr) /
  structure (incl. pine_structure, strategy_id) / ai / timing / execution
  (fill_price, slippage, spread, latency). `load_unified()` joins to trades
  by signal_id.
- `learning/decisions.jsonl` — every v7 verdict (durable evidence journal);
  `learning/v7_status.json` — heartbeat + last 50 decisions (display ring).
- `learning/flow_vector.jsonl`, `learning/signal_bus.jsonl`,
  `learning/eye_votes.jsonl`, `learning/analyst_reads.jsonl`,
  `learning/mirror_queue.jsonl`, `learning/weights.json`,
  `learning/clusters.json`, `learning/cluster_stats.json`,
  `learning/edge_report.json`, `learning/audit_report.json`.
- `logs/bot.log` (rotating 5 MB x 3), `access.log`, `error.log`,
  `logs/auto_live.jsonl`, `logs/auto_scenarios.jsonl`,
  `logs/auto_live_state.json`, `logs/mgmt_audit_last.json`.
- Bridge: `sniper_executor.log` (rotating 5 MB x 3; logs full `/execute`
  request bodies), `v7_seen_signals.json`, `C:\brotherbot\GLOBAL_STOP`.

# Heartbeat and decision records (core/v7_status.py)

`v7_heartbeat` fields: ts, schema `v7-status-1`, paused, hard_stopped,
consecutive_losses, total_trades/wins/losses, peak_balance, day_pnl,
week_pnl, balance, equity, bridge_ok, account_login, trade_mode, open_slots
(per class: symbol, ticket, side, entry, sl, tp, mae, mfe, opened_at,
signal_id, comment, broker_comment), symbols_enabled, last_decision_ts,
reconciliation, bot_version `v7`; None keys dropped; pushed with `system:
"v7"`, `kind`, `generated_at`, `title` at most every 240 s. `v7_decision`
fields: signal_id, symbol, direction, pine_system, type, session, tf, grade,
pine_score, pine_ver, entry, sl, tp, rr, atr, stance, status, gate,
gate_detail, reason, executed, order_id, broker_comment, lot, ai_score, ev,
cluster, regime, decision_id.

# auto_live.py — the Pine-independent engine (shadow)

auto-live-v1 ports the platform's auto-v1 math verbatim (`atr`,
`structure_state` over a 40-bar structural window, `SL_ATR 1.0`, `MIN_RR
1.0`, `TF_MIN 15`, `MIN_BARS 60`). It fires only when a CLOSED 15m bar
touches the structural level and the structure is still intact, never tracks
levels farther than `AUTO_LIVE_MAX_DIST` (3.0 ATR), refuses stale candles
(> 3 bars) with the freshness state, and refires the same level+side no more
than once per 24 h. `scenario()` logs every state per symbol to
`logs/auto_scenarios.jsonl`: WAIT / DEVELOPING / BUY READY / SELL READY /
DATA FRESHNESS with bullish_condition, bearish_condition,
missing_confirmation, invalidation, next_thing_to_watch, news context from
`filters/news_semantic.py`, and `pine_dependency = NONE`. `AUTO_LIVE_ARM`
unset = DRY RUN (logs to `logs/auto_live.jsonl`, posts nothing); armed
candidates are POSTed to `http://127.0.0.1:5000/webhook` with the secret
added at POST time only. `AUTO_LIVE_SYMBOLS` accepts `CANON=BROKER` pairs;
the canonical name keys every record, the broker name goes on the wire.

# Posting tools: contracts and refusals

- `post_outlook.py --symbol --horizon weekly|monthly --thesis --source
  [--scenario above|below:level:reading]... [--valid-hours] [--dry-run]`
  -> `POST /webhooks/brain/outlook` (X-Brain-Secret). Refuses locally:
  confidence/probability/chance words, blank thesis or source, a level with
  no reading, bad `when`, non-numeric level; prints `PLATFORM REFUSED (code)`.
  Defaults valid_hours weekly 168 / monthly 720.
- `post_weekly_outlooks.py` authors one weekly outlook per tradable symbol
  from bridge closed-bar candles (last close, week range, close vs prior week,
  conditional-profile cell), scenarios at the week's HIGH/LOW; skips a symbol
  with missing/stale candles; refuses when `EXECUTOR_URL` or the platform
  pair is unset; signed `bot box auto-weekly-v1`.
- `post_readiness.py` posts the newest `docs/AUTONOMY_READINESS_*.md` as
  `kind: "doc"` to `/webhooks/brain/artifact` (content under both `content`
  and `markdown`); refuses when none exists.
- `post_incident.py INC-xxx --root-cause --fix-ref --tests [--status
  investigating|patch_proposed|fix_proposed] [--dry-run]` -> env
  `INCIDENT_INGEST_PATH` default `/webhooks/brain/incident`; sends BOTH
  `incident_id` and `public_id`; refuses `resolved`; prints the board's status
  and any `refused` reason.
- `autonomy_scorecard.py --post` posts `AUTONOMY_SCORECARD_<date>.md` as a doc.

# Shadow-intelligence modules (never in the decision path)

`filters/deepseek_vote.deepseek_tiebreak` (EYE_MODEL gemini|deepseek|shadow;
fail-safe None; votes to `learning/eye_votes.jsonl`); `learning/vote_worker`
(separate process tailing `signal_bus.jsonl`); `learning/brain_scorer`
(per-cluster VETO/CONFIRM scorecard with Beta smoothing); `learning/
consult_brain.ai_gate` (fail-open ALLOW, not wired); `risk/analyst_eye`
(independent LLM read of live candles, log-only, cost-controlled by free
slot + margin); `learning/strategy_dna.classify` (S1 trend_continuation,
S2 pullback_sniper, S3 breakout, S4 mean_reversion, S5 news_reaction, S0
unclassified); `learning/conditional_profile` (hierarchical backoff over
symbol/side/aligned/session/grade/dist/news, FLOOR 20, MEASURED_N 100);
`nightly_edge` (empirical-Bayes shrinkage `PRIOR_K 6`, one-SE lower-bound
expectancy, advisory weights only); `filters/news_semantic` (event class ->
surprise -> stance -> pressure map; UNKNOWN stays UNKNOWN).
