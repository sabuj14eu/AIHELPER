---
title: Brother v18 Brain — Architecture and Data Flow
domain: brain
repo: sabuj14eu/brother-brain-v2
sources: README.md, docs/PROTOCOL.md, docs/AUDIT_2026-07-31.md, docs/PINE_VS_BOT_MAP.md, brain/src/main.py, brain/src/agents/council.py, brain/src/compute_sltp.py, brain/src/pine_trust.py, brain/src/position_check.py, brain/src/market_vision.py, brain/src/shadow_gate.py, brain/src/signals/dispatcher.py, brain/src/utils/decision_journal.py, brain/src/platform_mirror.py, brain/mirror_outcomes.py, brain/backfill_journal_outcomes.py, brain/reconstruct_decisions.py, brain/remirror_decisions.py, brain/push_bias.py, brain/push_news.py, shared/src/protocol/envelope.py, shared/src/protocol/nonce_store.py, shared/src/protocol/halt_admin.py, shared/src/utils/clock.py, shared/src/utils/event_log.py, executor_ic_markets/src/main.py, executor_ic_markets/src/ic_markets/mt5_bridge.py, executor_ic_markets/src/ic_markets/reconciler.py, executor_ic_markets/src/utils/state.py, executor_ic_markets/src/utils/registry.py, executor_ic_markets/src/utils/global_stop.py, executor_ic_markets/src/clock_witness.py, dashboard/backend/main.py, dashboard/README.md, watchdog/src/main.py, watchdog/src/halt_all.py, scanner_mt5/scanner_mt5.py, scanner_polymarket/scanner.py, executor_polymarket/src/main.py, docs/decisions.md
verified_on: 2026-09-16
classification: INTERNAL
---

# Repository layout of brother-brain-v2

| Folder | Role | Deploys to |
|---|---|---|
| `brain/` | webhook listener, council agents, gates, dispatcher, journal, platform mirror, analytics scripts | Contabo, `/home/shyam/brain-v2/brain` |
| `executor_ic_markets/` | v18 executor: signed-signal verification, MT5 bridge, reconciler, state, registry, global stop | Windows VPS, `C:\brother_v18\executor_ic_markets` (not a git clone) |
| `executor_polymarket/` | Polymarket CLOB executor (decommissioned) | DigitalOcean |
| `scanner_mt5/`, `scanner_polymarket/` | candidate scanners (MT5 scanner DRY-RUN by design; PM scanner retired) | Contabo |
| `shared/` | Ed25519 signer/verifier/keygen, envelope, nonce store, admin halt router, NTP clock check, JSONL event log | imported by every component |
| `dashboard/` | read-only FastAPI backend + static frontend for status.signalmesh.dev | Contabo |
| `watchdog/` | 30-second health pinger with Telegram alerts and `halt_all.py` | Amsterdam droplet |
| `deploy/` | systemd units, nginx template, UFW script, NSSM install notes | — |
| `tests/`, `brain/tests/` | unit tests and dated `audit/` evidence directories with golden fixtures | — |
| `docs/` | PROTOCOL, DEPLOY_RUNBOOK, HANDS_OFF_DEPLOY, AUDIT_2026-07-31, OPEN_ITEMS, decisions, PINE_VS_BOT_MAP, SESSION_* | — |

The repo also carries `brother_v18_v1.1.zip`, `dashboard.tar.gz` (ignored for this pack) and `brain/brain.out`, a committed nohup log of the brain from 2026-05-31 to 2026-06-01.

# End-to-end data flow of the v18 brain

```
TradingView Pine alert (bar close)
  -> nginx (brain.signalmesh.dev, TradingView IP allowlist; also mirrors to v7 :5001)
  -> brain/src/main.py  POST /webhook/v18   (secret check, 300s dedupe, BSv11 -> Telegram only)
  -> asyncio background task _run_v18_council(signal_id, ts_received, opportunity)
       GradeGate (C/D journaled at $0)  ->  AI OFF: SlotGate -> approve_from_pine
                                        ->  AI ON : slot state -> MarginGate -> market vision -> grade gate
                                                    -> Council.evaluate (Scout..RiskManager) -> build_execution_payload (code)
                                                    -> _validate_prep_payload
                                                    occupied slot -> CostGate -> Council.manage (PositionManager)
       AgentError fail-soft (bounded) / fail-closed
  -> write_decision -> logs/decisions.jsonl  (+ mirror_decision -> platform, daemon thread, one-way)
  -> ShadowGate (NVDA: journaled, never dispatched)
  -> SignalDispatcher: SignalEnvelope(target, signal, account_id) -> Ed25519 sign -> httpx POST executor /signal
  -> executor_ic_markets main.py: bearer -> parse -> target -> signature -> account_id -> age<60s -> nonce
       -> kill switch -> global stop -> roll day -> pending loss -> duplicate signal_id -> trade cap -> loss cap -> risk_pct
  -> MT5Bridge.open_position: symbol map -> slot guard (positions + pendings) -> margin floor (fail closed)
       -> _compute_lots (min-lot guard, margin lot cap) -> live tick price -> order_send with SL/TP attached
  -> registry.add(ticket, signal_id)  ->  Reconciler thread (naked-SL check, orphan adoption, close-tracker -> logs/outcomes.jsonl)
  -> Telegram; journal; dashboard (read-only); truth_layer / mirror_outcomes join by ticket
```

The audit of 2026-07-31 (docs/AUDIT_2026-07-31.md §3) states where a signal can be rejected (secret, dedupe, gates, any agent, grade gate, executor gates, broker retcode), modified (compute_sltp widen-only, lot rounding), and duplicated (same-symbol race before first fill; brain restart within the dedupe window).

# The webhook listener and the opportunity shape

`_build_v18_opportunity(body)` in brain/src/main.py normalizes a Pine alert into the council's shape: `source: "v18_tradingview"`, `origin` (`""` for Pine, `"mt5_scanner"` for the scanner), `target: "ic_markets"`, `title` (alert_name or signal_id), `symbol`, `side` (from `side` or `direction`, upper-cased), `entry`, `sl`, `tp`, and `context` with `today`, `market_snapshot`, `macro_calendar` (always empty in practice — audit P2-2), `open_positions`, and `risk_caps {max_risk_pct: 0.5, max_trades_per_day: 6}`.

The snapshot whitelist `_PINE_SNAPSHOT_FIELDS` names: tf, score, grade, vetoes_passed, v1_trend, v2_htf, v3_sweep, v4_rr, v5_struct_tp, v6_spread, macro_score, dxy_dir, oil_spike, atr_expand, trend, htf_align, choch, inducement, sweep, zone, rsi, adx, session, htf_full, ny_regime, killzone, trap_bias, atr_pad, dxy_squelch, mode, system, type, tp1, tp2, rr, adj_score, news_window, vol_regime, trend_day, yield_dir, loc_gate, loc_zone, signal_id. Since 07-20 every remaining scalar key of the body also passes through into `market_snapshot` ("APPEND-TOLERANT LISTENER"), so later Pine appends such as `pine_ver`, `payload_schema`, `fired_at`, `trades_today`, `struct`, `entry_dist_atr` arrive automatically. Consumed structural keys are `side, direction, alert_name, symbol, entry, sl, tp, origin, market_snapshot, macro_calendar, secret, signal, action`.

The dedupe key is `symbol|side|entry|sl|origin` over a 300-second in-memory window (06-12 incident: a state wipe caused a double post). The 07-02 fix made the key read `side` or `direction` or `signal`, because the body carried no `side` key and every key had `side=None`, so an opposite-direction signal could be swallowed as a duplicate.

# Signal identity: signal_id and pine_signal_id

`canonical_signal_id(body, opportunity, ts)` (brain/src/utils/decision_journal.py, BOT-P0-2 2026-08-21) adopts Pine's `signal_id` verbatim (trimmed, capped at 128 chars) with source `"pine"`; only a missing or unusable id falls back to `new_signal_id()`, which mints `v18-tradingview_<symbol>_<side>_<YYYYMMDD_HHMMSS>_<4hex>` with source `"minted_fallback"`. The source is journaled in `market_snapshot.signal_id_source`, and the platform-side acceptance test is "the FALLBACK_ID share on /funnel falling toward zero." Pine ids look like `SS-BUY-<yyyymmddHHMMSS>`, `SC-SELL-<yyyymmddHHMMSS>`, `PB-BUY-<yyyymmddHHMMSS>` (prefix = engine, side, then the BAR-OPEN time `YYYYMMDDHHMMSS`; reconstruct_decisions.py uses that stamp as a clock witness: a brain line may sit 0..70 minutes after it).

The platform mirror sends `signal_id` (the brain's journal id) AND `pine_signal_id` (= `market_snapshot.signal_id`, the raw Pine id) as the join key shared with the v7 arm, "since the v18 journal id and v7's 'v7-<id>' share no common root" (platform_mirror.py). The dispatched executor payload carries `signal_id` (appended 07-31, audit P1-3) as the executor's idempotency key; the executor stores it for 6 hours keyed `"<asserted_login>:<signal_id>"` (ISO-13) and refuses `duplicate_signal_id`.

# Gates before the council

- **GradeGate** (08-09): grades C/D are journaled with `dispatch_mode blocked_gradegate` and mirrored, no council spend.
- **SlotGate** (`position_check.py`): asks the executor `GET /positions` (two attempts, 1s apart); unreachable = fail-closed skip; a symbol with an open position is skipped on the AI-OFF path or routed to MANAGE on the AI-ON path. Pine symbols map to broker symbols (`SILVER->XAGUSD`, `GOLD->XAUUSD`, `BITCOIN->BTCUSD`, `ETHEREUM->ETHUSD`, `US100/NAS100->USTEC`).
- **CostGate** (`manage_state.py`): per-ticket AI-call budget (`MAX_AI_CALLS_PER_TRADE` default 3) and cooldown (`MODIFY_COOLDOWN_MINUTES` default 30).
- **MarginGate** (06-15): reads `/positions.account`; one retry after 2.5s for the MT5 IPC blip at bar close (07-03); still fail-closed; floor `max(0.10 * balance, 100.0)` on `margin_free`.
- **Market vision** (`market_vision.py`, 06-24): fetches M15/H1/H4 closed candles from the executor `/candles` (params `symbol, tf, n`; the 06-30 fix discovered the old `timeframe/count` params were ignored so HTF trends were fake M15 copies) and adds `vision_*` keys (trend per timeframe, swing high/low, pos_in_range_pct, ATR, distances).
- **Grade gate** (06-12): council for A/A+ and 1-in-3 B; otherwise `approve_from_pine`.
- **AI flag**: `ai_enabled()` is true when the file `brain/AI_ENABLED` exists (`pine_trust.py`); the dashboard exposes `/api/ai-status` and `/api/ai-toggle`.

# Pine trust and the deterministic stop calculator

`approve_from_pine(opp)` (brain/src/pine_trust.py) accepts grades A+/A/B only, requires numeric entry/sl/tp, refuses scanner origin, runs `compute_sltp`, optionally rejects below `PINETRUST_MIN_RR` (default 0.0), and emits `{action: OPEN, symbol, side, order_type: MARKET, entry_price, stop_loss, take_profit, risk_pct: 0.5, magic_number: 180000, comment: "v18-pinetrust-<grade>"}`. Since ISO-21 a calculator error is a rejection, never a raw-stop fallback.

`compute_sltp` (brain/src/compute_sltp.py) is a pure function: `floor_distance = max(min_stop_pct * entry, atr_mult * atr)`, `new_sl_distance = max(pine_sl_distance, floor_distance)` — it only ever widens. Per-symbol floors: xauusd 0.0018/1.5, silver 0.0040/1.5, ethusd 0.0050/1.5, btcusd 0.0040/1.5, usdjpy 0.0010/1.5, eurusd 0.0010/1.5, default 0.0020/1.5. TP is left as Pine sent unless `preserve_rr=True`. The council path (`build_execution_payload`) calls the same calculator with the RiskManager's bounded params (`atr_mult` 1.0–3.0, `min_stop_pct` 0.0005–0.01) and `risk_pct = min(0.5, model's)`, order type always MARKET, comment `v18-council-<grade>`.

`_validate_prep_payload` (council.py, audit P0-3) then asserts: action OPEN, bare symbol equal, side equal, entry within 5% of the signal entry, BUY geometry `sl < entry < tp` / SELL `tp < entry < sl`, SL/TP within 20% of entry, `0 < risk_pct <= 2.0`.

# The signed envelope and dispatch

`SignalEnvelope` (shared/src/protocol/envelope.py) has `version: 1`, `issued_at` (UTC, second resolution), `nonce` (uuid4), `target` (`polymarket` | `ic_markets`), `account_id` (ISO-10, signed; `None` only in legacy/print envelopes), `signal`, and `signature` added last. The signable bytes are canonical JSON (sorted keys, compact separators). `MAX_SIGNAL_AGE_SECONDS = 60`. `SignalDispatcher` (brain/src/signals/dispatcher.py) reads `BRAIN_DISPATCH_MODE` (`print` logs only; `live` POSTs), the per-target URL, bearer token and `EXECUTOR_IC_MARKETS_ACCOUNT`; live dispatch without an account_id returns `{"status":"error","reason":"no_account_id","actually_posted":false}`. Its return `{mode, status, response, nonce}` is journaled verbatim under `dispatch` (07-19 fix: the old journal read keys the dispatcher never emitted).

The IC Markets signal payload (docs/PROTOCOL.md) is `{action: OPEN|CLOSE|MODIFY|CANCEL, symbol, side, order_type: MARKET|LIMIT|STOP, entry_price, stop_loss, take_profit, risk_pct, magic_number: 180000, comment, thesis_hash}`; the brain's MANAGE path sends `{action: MODIFY, symbol, ticket, stop_loss, take_profit}` or `{action: CLOSE_ONE, symbol, ticket, comment}`. The executor also accepts `CLOSE_ALL`.

# The v18 executor (executor_ic_markets)

`src/main.py` refuses to start unless NTP drift is under 5 seconds (`require_synced_clock`). All MT5 calls go through ONE worker thread (`ThreadPoolExecutor(max_workers=1)`, 2026-06-29 timeout fix: a blocking `order_send` on the event loop froze `/health` and `/positions` for ~15s). Endpoints: `GET /health` (status, dry_run, mt5_connected, account_login, trade_mode, kill_switch, global_stop, guards_flag_present, trades_today, balance, pnl_pct_today, git_commit), `GET /positions` (count, symbols, account margin dict, our-magic positions), `GET /outcomes?n=` (rows of `logs/outcomes.jsonl`), `GET /candles?symbol&tf&n` (closed bars only, UTC via two-witness clock else 503), `GET /spread`, `GET /cansize` (read-only min-lot preview for the session caller), `POST /signal`, `POST /admin/halt`, `GET /admin/status`.

`/signal` order of checks (executor main.py): bearer → signature present → parse envelope → target ic_markets → Ed25519 verify (event `bad_signature`) → `no_account_id` / `account_mismatch` against `asserted_login` → age > 60s stale → nonce replay (409) → event `signal_verified` → GUARDS_DISABLED file logged but IGNORED → kill switch → for OPEN: global stop (STOP or UNKNOWN refuses) → `roll_if_new_day` → pending unknown-balance loss (`pnl_unknown_pending`) → `duplicate_signal_id` → `daily_trade_cap` (`MAX_TRADES_PER_DAY` default 6) → `daily_loss_cap` (`MAX_DAILY_LOSS_PCT` default 2.0, trips kill switch) → `no_risk_pct` → `risk_pct = min(sent, MAX_RISK_PCT_PER_TRADE default 0.5)` → `open_position`. Daily caps apply to OPEN only; MODIFY/CLOSE_ONE reduce risk and are never blocked by caps (the kill switch still freezes everything).

`MT5Bridge` (`src/ic_markets/mt5_bridge.py`): `DRY_RUN` defaults to true unless exactly `false`; `MAGIC_NUMBER` default 180000; login asserted on init and on every probe with auto-reconnect throttled by `MT5_RECONNECT_COOLDOWN` (default 5s). `open_position` guards: slot (positions and pendings with our magic → `slot_held` / `slot_held_pending`), margin level floor `MIN_MARGIN_LEVEL_PCT` (default 150, unreadable → `margin_unknown`), `_compute_lots` (tick-value sizing; skip when `raw_lots < volume_min * 0.4`; `USABLE_MARGIN_PCT` default 40 caps lots to free margin), market orders priced at the live ask/bid, pendings validated side-of-market and rejected `pending_price_stale` if invalid, `order_send` with `sl`/`tp`, `deviation 10`, IOC filling. The response `summary {symbol, side, lots, entry, sl, tp, type, comment, magic}` is what the platform later receives as `exec_*`.

State and truth files on the executor: `logs/state.json` (`ExecutorState`: today, trades_today, pnl_pct_today, kill_switch, kill_reason, cap_day, pending_pnl_money, pnl_unknown_since, account), `logs/open_tickets.json` (registry, atomic writes), `logs/outcomes.jsonl` (close-tracker: ticket_id, deal_ticket, symbol, outcome WIN/LOSS/BE, pnl_net incl. swap+commission+fee, exit_reason TP/SL/STOPOUT/EXPERT/MANUAL, closed_at, volume, close_price), `logs/nonces.json`, `logs/signal_ids.json`, `logs/events/events_YYYY-MM-DD.jsonl` (append-only event log, gz-rotated, 90-day retention), and the global stop file `C:\brotherbot\GLOBAL_STOP` (override `GLOBAL_STOP_FILE`).

The `Reconciler` thread (`RECON_INTERVAL_SECONDS` default 300) trips the kill switch after 3 consecutive MT5 query failures or on any our-magic position without a stop-loss, reconciles the registry (orphans adopted after 2 sightings, closed tickets pruned), and tracks closes from deal history to feed `on_close` → `pnl_pct_today`. Audit P2-4 notes the docstring's position-count and net-exposure checks are not implemented.

# The decision journal

`write_decision` (brain/src/utils/decision_journal.py) appends one row to `logs/decisions.jsonl` (`BRAIN_LOGS_DIR`, default `/home/shyam/brain-v2/brain/logs`) under a threading lock and an fcntl file lock `decisions.jsonl.lock` shared with `backfill_journal_outcomes.py`. Row fields: ts_received, ts_decided, latency_ms, signal_id, source, target, alert_name, symbol, side, entry, sl, tp, rr, approved, rejected_by, rejection_reason, `council {scout, researcher, quant, devils_advocate, risk_manager, executor_prep}`, `dispatch {mode, status, nonce, response, error}`, anthropic_cost_est_usd, signal_grade, ticket_id, dispatch_status, dispatch_nonce, `signal_raw` (the full opportunity verbatim), and the outcome fields `outcome, pnl_net, exit_reason, closed_at` (null until backfilled). `dispatch.mode` values: `council_live`, `pinetrust_live`, `manage_live`, `*_print`, `*_rejected`, `blocked_gradegate`, `blocked_slotgate`, `blocked_unreachable`, `blocked_costgate`, `blocked_precheck`, `blocked_shadow`. Since INC-0004 (2026-09-06) the writer can only fail into a log line, never into its caller.

# The platform mirror and mirror_outcomes (brain -> platform, one way)

`mirror_decision` (brain/src/platform_mirror.py) is feature-flagged by `PLATFORM_MIRROR_ENABLED`, runs on a daemon thread, is fail-silent, and POSTs to `<PLATFORM_WEBHOOK_URL>/webhooks/brain/signal` with header `X-Brain-Secret`. Payload keys (all append-only): ticket, executor_account, signal_id, system, symbol, direction, entry, sl, tp1, tp2, rr, grade, `council {approve, total}`, status (`approved` | `rejected`), confidence (0-100), pine_signal_id, pine_ver, payload_schema, fired_at, session, tf, score, rr_in_grade (SMART_SCALP true, PULLBACK false, SESSION_CALL false), rejected_by, rejection_reason (or "<Agent> refused without reasoning text"), executor_status, executor_reason, `exec_sl / exec_tp / exec_entry_req / exec_lots / exec_order_type / exec_levels_source` (from the executor's placement summary; keys ABSENT = UNKNOWN, never 0), `reason` (alias of rejection_reason), fail_soft, fail_soft_reason, fail_soft_count, fail_soft_max, plus spread/spread_points/spread_source sampled from the executor `/spread` on the mirror thread ("the ORDER PATH NEVER WAITS FOR THIS").

`brain/mirror_outcomes.py` (cron every 10 minutes) posts each closed outcome from executor `/outcomes` ONCE to `/webhooks/brain/decision` as the executor's own witness: `system v18, kind executor_outcome, witness executor, status executed, executor_status closed, signal_id (joined by ticket from the journal), unmatched, symbol, broker_symbol, direction, ticket, deal_ticket, executor_account, outcome, pnl_net, exit_reason, closed_at (verbatim), volume, close_price, ts, decided_at, reason, source`, plus the same `exec_*` keys when the journal row carries a placement summary. State `logs/outcomes_mirrored.json` maps deal_ticket → posted-at; `--exec-update` re-posts already-mirrored closes once with `exec_update: true`; receipts (`stored`/`skipped`, platform v5.38) are compared and mismatches printed.

Companion tools: `backfill_journal_outcomes.py` (BOT-P0-1: fills the four outcome fields from `/outcomes` by ticket, atomic rewrite, aborts if any decision field would change), `remirror_decisions.py` (re-posts journal decisions with today's payload and `remirror: true` inside the platform's 48h idempotency window), `reconstruct_decisions.py` (INC-0004: rebuilds lost decisions from brain journalctl lines, the v7 journal and executor events, posts only resolved rows with `backfill: true, reconstructed: true, witnesses [...]`, never writes decisions.jsonl), `push_bias.py` (fresh EMA20/50/200 + ATR bias per canonical symbol from the v7 bridge, journal fallback with true `as_of`, one row per canonical name), `push_news.py` (the ForexFactory weekly JSON the v7 news gate already uses, all impacts).

# Dashboard bot-guards and the service wall

`dashboard/backend/main.py` `/api/services` builds the top bar and Bot Control panel. The `bot_v18` bot-guard (07-19, LIVE-20260713-GHOST) reads the executor `/outcomes?n=50` and the last 400 KB of decisions.jsonl: `_ghost = approvals_in_24h_with_live_mode > 0 and tickets_in_24h == 0` turns the tile RED "GHOST — approvals but NO tickets in 24h"; quiet thresholds are 24h on weekdays and 72h at weekends; the `patch_botguard_margin.py` addition (07-26, LIVE-20260724-STUCKTERMINAL) counts "margin unreachable" rejections, three or more in 24h = the stuck-terminal signature. `bot_v7` reads the age of `/home/shyam/brother_sniper_v7/learning/trades.jsonl`. The service wall (07-10) checks systemd units and both Windows endpoints, and marks the v7 bridge RED when the newest GOLD M15 candle is older than 12h even if `/health` says ok. Auth: nginx IP allowlist plus `?t=<DASHBOARD_TOKEN>`. The dashboard has "zero dispatch capability" (audit).

# Watchdog, scanners and the Polymarket executor

The watchdog (`watchdog/src/main.py`) pings `/health` of the configured services every `PING_INTERVAL_SECONDS` (30), alerts on Telegram after `MISS_THRESHOLD` (2) misses, 5xx, `kill_switch`, `pnl_today` / `pnl_pct_today` thresholds and `mt5_connected: false`, throttled by `ALERT_COOLDOWN_MINUTES` (15). `halt_all.py` POSTs `/admin/halt` with the per-executor admin token — "bypasses the Brain entirely ... Works even if Brain is down or compromised."

`scanner_mt5/scanner_mt5.py` (BSv18-SCANNER) reads executor candles, scores EMA/RSI/pullback setups and would POST to `/webhook/v18` with `origin: "mt5_scanner"` only when the file `POST_ENABLED` exists; it is DRY-RUN by default and the dashboard labels it "DRY-RUN by design". The council-bypassing scanner that lost 60R is retired (Iron Rule 1); scanner-origin signals are barred from pine_trust in code. `scanner_polymarket/scanner.py` fetched Gamma API markets hourly and posted up to 3 candidates to `/webhook/polymarket`; it is retired. `executor_polymarket/src/main.py` implements the same 10-check envelope verification for the CLOB (py-clob-client V2, EOA path); the server was deleted (patch_dashboard_remove_pm.py).
