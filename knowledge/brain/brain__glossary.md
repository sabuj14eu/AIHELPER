---
title: Brother v18 Brain — Glossary
domain: brain
repo: sabuj14eu/brother-brain-v2
sources: CLAUDE.md, README.md, docs/PROTOCOL.md, docs/AUDIT_2026-07-31.md, docs/OPEN_ITEMS.md, docs/PINE_VS_BOT_MAP.md, docs/SESSION_COORDINATION.md, brain/src/main.py, brain/src/agents/*.py, brain/src/pine_trust.py, brain/src/compute_sltp.py, brain/src/shadow_gate.py, brain/src/platform_mirror.py, brain/mirror_outcomes.py, brain/truth_layer.py, brain/council_calibration.py, brain/weekly_source_report.py, brain/push_bias.py, executor_ic_markets/src/main.py, executor_ic_markets/src/ic_markets/*.py, executor_ic_markets/src/utils/*.py, shared/src/protocol/*.py, dashboard/backend/main.py, watchdog/src/*.py, tests/audit/2026-09-04_job3/README.md
verified_on: 2026-09-16
classification: INTERNAL
---

# Glossary of the v18 brain

**v18 brain / brain-v2** — The Contabo service (`brother-brain.service`, `/home/shyam/brain-v2/brain`) that receives Pine alerts, runs the council, signs approved signals and dispatches them. Holds only the Ed25519 signing key.

**v18** — The current generation of the Brother Sniper system (Pine script version family 18.x and the brain/executor built for it); v17 is retired.

**v7 / v7 bot** — The separate mechanical trading arm (`/home/shyam/brother_sniper_v7`) that receives the same Pine alert through the nginx mirror, applies its own dial-based filters, and trades MT5 account 52834417 through its bridge on port 5001.

**Council** — The v18 brain's sequence of Claude-backed agents (Scout → Researcher → Quant → DevilsAdvocate → RiskManager) with veto gates between stages; "6-agent council" in older docs counts ExecutorPrep, which ISO-19 retired.

**Scout** — Agent 1; decides PROCEED / SKIP / DEFER on structure, spread, stop tightness, R:R and nearby macro events, and emits a display-only teaching proposal.

**Researcher** — Agent 2; builds a web-search intelligence packet (bull/bear cases, sources, `confidence` 0–1); the most expensive agent.

**Quant** — Agent 3; produces a calibrated fair value with a 90% CI and `edge`; `preferred_side: PASS` rejects with "no edge"; must not anchor fair value on the signal's TP (anti-circularity).

**DevilsAdvocate (Devil)** — Agent 4; adversarial reviewer with veto power; attacks broken instances, never the validated PULLBACK class design.

**RiskManager** — Agent 5; Kelly-capped sizing, portfolio-grounds veto; for FX outputs only bounded `sltp_params` and a `risk_pct` it may lower, never raise.

**ExecutorPrep** — The former Agent 6 that assembled the executor payload with an LLM; retired 2026-09-05 (ISO-19); the trace key survives one release for readers.

**PositionManager** — The single-call agent on the MANAGE path (a fresh alert for a symbol with an open v18 position); returns HOLD, MODIFY or CLOSE_ONE.

**Teaching proposal** — The display-only `proposal {side, entry, sl, tp, note}` every Scout/Quant/Devil answer carries for operator education; graded by `council_calibration.py`, never executed.

**AgentError** — The exception raised when an agent call or parse fails; reclassified from "Scout rejection" on 07-02 so provider outages do not poison approval statistics.

**Fail-soft** — The bounded policy that an A/A+ entry signal whose council call failed is approved from Pine trust, at most `FAILSOFT_MAX_PER_DAY` (2) times per UTC day, then fail-closed; visible on the mirror as `fail_soft: true`.

**Fail-closed** — The default posture: unreachable executor, unreadable margin, unreadable balance, unverifiable clock or a calculator error all refuse the trade rather than assume ("UNKNOWN never becomes allowed").

**Pine trust (pine_trust / approve_from_pine)** — The AI-off or grade-gated path that approves A+/A/B signals directly from Pine's gate chain after `compute_sltp` floors the stop; scanner-origin signals are barred from it.

**compute_sltp** — The pure, deterministic stop/target calculator with per-symbol noise floors (`min_stop_pct`, `atr_mult`); only ever widens a stop; used by both pine_trust and the council path.

**Grade gate** — Cost control (06-12): council only for A/A+ and one random B in three; C/D never reach the council (GradeGate, 08-09).

**SlotGate / MarginGate / CostGate / GradeGate / PrepValidation / ShadowGate / PineTrust / AgentError** — Structured `rejected_by` values the brain journals and mirrors so the platform funnel buckets by identity instead of free text.

**Slot** — One open v18 position per broker symbol; the brain checks executor `/positions` and the executor's `open_position` refuses `slot_held` / `slot_held_pending` (pendings count as claimed exposure).

**Market vision** — Real OHLCV context (M15/H1/H4 trends, swing high/low, ATR, position in range) fetched from the executor `/candles` and injected into the snapshot for the council (`vision_*` keys).

**Opportunity** — The normalized shape the brain builds from a Pine alert: source, origin, target, title, symbol, side, entry, sl, tp, and `context.market_snapshot` with every Pine field passed through.

**Dispatch / dispatcher** — `SignalDispatcher` builds the signed envelope and POSTs it to the executor's `/signal` in `live` mode, or logs it in `print` mode (`BRAIN_DISPATCH_MODE`).

**Envelope** — The wire format `{version, issued_at, nonce, target, account_id, signal, signature}`; the Ed25519 signature covers canonical JSON of everything but `signature`.

**Nonce / NonceStore** — A per-dispatch UUID the executor remembers for 10 minutes to refuse replays; the same store class keeps seen `signal_id`s for 6 hours (idempotency).

**signal_id** — The brain's journal id for a decision; since 2026-08-21 it is Pine's own id when present (`pine`), otherwise minted (`minted_fallback`).

**pine_signal_id** — The raw Pine id carried on the platform mirror as the join key shared by both arms (v7 posts it too).

**Executor** — A thin, paranoid execution service that verifies the envelope and places orders; `executor_ic_markets` (Windows, MT5, NSSM `SniperExecutorV18`, :8080) is live; `executor_polymarket` is decommissioned.

**Bridge** — Either the v18 executor's `MT5Bridge` class (`mt5_bridge.py`) or, in most docs, the v7 bot's MT5 bridge on port 5001 that also serves candles to the analytics scripts.

**Ticket** — The MT5 position id returned by `order_send`; the unit of truth ("only TICKETS tell the truth"), the join key between decisions, the registry and outcomes.

**Registry** — `logs/open_tickets.json` on the executor: every confirmed ticket written before the HTTP response can time out; reconciled against MT5 (orphans adopted after 2 sightings, closed tickets pruned).

**Reconciler** — The executor thread (every 300s) that trips the kill switch on 3 consecutive MT5 failures or any naked (no-SL) position, reconciles the registry, and tracks closes into `outcomes.jsonl`.

**Close-tracker / outcomes.jsonl / Piece B** — The reconciler's deal-history scan that writes one row per closed position (WIN/LOSS/BE, net P/L incl. swap+commission+fee, exit reason) served at `/outcomes`.

**Journal (decisions.jsonl)** — The append-only, fsync'd, locked decision log at `brain/logs/decisions.jsonl`, one JSON row per signal, with the raw alert verbatim in `signal_raw`; "this system's history is measured, not remembered."

**signal_raw** — The full opportunity stored verbatim on every journal row so future questions are not foreclosed ("Storage is cheap; foreclosed questions are expensive").

**dispatch_mode** — The journal's precise routing label (`council_live`, `pinetrust_live`, `manage_live`, `*_rejected`, `blocked_gradegate`, `blocked_slotgate`, `blocked_unreachable`, `blocked_costgate`, `blocked_precheck`, `blocked_shadow`).

**Truth layer** — `truth_layer.py`: joins decisions to executor outcomes by ticket and buckets performance by condition, flagging n<20 as PROVISIONAL.

**Scorecard** — Named in CLAUDE.md's analytics list; the 2026-07-31 audit notes `scorecard` (and `session_caller`) "named in CLAUDE.md don't exist in the repo" — the closest artifacts are `weekly_source_report.py` and `truth_layer.py`.

**Calibration (council_calibration.py)** — Grades original signals and the rejecting agent's proposal against real M15 candles (NO_FILL / HIT / SL / OPEN) to ask whether the council's teaching levels are better.

**Session caller** — A paper caller (3x daily, `session-caller.timer`, ledger `/home/shyam/session_caller/session_calls.json`) reimplementing the PULLBACK geometry; council-gated when live; graduation needs resolved n>=20 beating the live arms.

**Source report (weekly_source_report.py)** — "THE SUNDAY VERDICT": SMART_SCALP vs PULLBACK vs SESSION_CALL vs the paper ledger over the last N days with the graduation rule.

**SMART_SCALP / PULLBACK / SESSION_CALL** — The signal families: Pine's momentum score-based scalp, Pine's armed-limit structure-tap (validated design), and the scheduled caller.

**Pullback backtest** — `pullback_backtest.py`, the honesty-ruled harness (no lookahead, touch fills, same-bar SL, 70/30 train/validate) behind the PULLBACK evidence; `fib_pullback_backtest.py` is its FIB-vs-STRUCT sibling.

**Mirror (platform mirror)** — `platform_mirror.py`: the one-way, feature-flagged, fail-silent POST of every decision to the Brother Bot Platform (`/webhooks/brain/signal`).

**mirror_outcomes** — The cron tool that posts each executor close once to `/webhooks/brain/decision` as the executor's own witness and compares the platform's `stored`/`skipped` receipts.

**exec_* keys** — `exec_sl`, `exec_tp`, `exec_entry_req`, `exec_lots`, `exec_order_type`, `exec_levels_source`: the levels the executor actually sent at placement, from its own response summary; absent means UNKNOWN, never 0.

**Backfill / reconstruct / remirror** — `backfill_journal_outcomes.py` fills journal outcomes; `reconstruct_decisions.py` rebuilds lost decisions from three witnesses (INC-0004); `remirror_decisions.py` re-posts decisions with today's payload inside the platform's 48h window.

**push_bias / push_news** — Cron posters of per-symbol market bias (fresh EMA/ATR read with honest `as_of`, one row per canonical symbol) and the ForexFactory calendar to the platform.

**as_of** — The true timestamp of a datum carried on every re-post so the platform derives real age; "nothing is ever repainted fresh."

**Canonical symbol** — The platform's display name (GOLD, SILVER, US100, BTC, ETH, XRP, OIL, NVDA) that `push_bias.canon()` maps broker and Pine names onto; the dedupe key that closed the twin-row class.

**Bot-guard** — The dashboard tiles (`bot_v18`, `bot_v7`) that read ticket truth: RED "GHOST" when approvals exist with no tickets in 24h, or three-plus "margin unreachable" rejections (stuck terminal).

**Service wall** — The dashboard's one-glance grid of systemd units, both Windows endpoints and v7 candle freshness (stale beyond 12h is RED even if `/health` is ok).

**Watchdog** — The Amsterdam pinger (`watchdog/`) that alerts on Telegram after two missed pings, 5xx, kill switch, PnL thresholds or `mt5_connected: false`; also hosts `halt_all.py`.

**Kill switch** — Per-executor stop stored in `state.json`; tripped by admin halt, daily loss cap, reconciliation drift, account-mismatched state; reset only by SSH and hand-editing the file.

**Admin halt / halt_all** — `POST /admin/halt` with an independent `x-admin-token` that works even if the brain is down; the watchdog's `halt_all.py` calls it for every executor.

**Global stop (GLOBAL_STOP)** — ISO-16's one witness file for both arms on the Windows box: present = STOP, absent = CLEAR, unreadable = STOP; refuses every OPEN, never bypassable.

**GUARDS_DISABLED** — A flag file beside `src/` that once lifted the executor's caps; since ISO-15 it is only reported on `/health` as `guards_flag_present` and obeyed by nothing.

**DRY_RUN** — Executor mode (default true unless exactly `false`) that logs the would-be order and returns `dry_run` instead of calling `order_send`.

**Daily caps** — `MAX_TRADES_PER_DAY` (6), `MAX_DAILY_LOSS_PCT` (2.0), `MAX_RISK_PCT_PER_TRADE` (0.5) on the executor; `cap_day` persists the UTC day so restarts cannot reset them.

**Min-lot guard / DECISION-A** — Skip an order whose correct size is under 0.4x the broker minimum lot (up to 2.5x risk inflation tolerated in demo), after ticket 1697829693 lost 25.18 USD on 0.41 USD of intended risk.

**Favorable-only MODIFY** — The executor's hard invariant that a stop may only move toward price (BUY: `new_sl >= cur_sl`, SELL: `new_sl <= cur_sl`); TP must stay on the correct side of entry.

**Two-witness clock (B5)** — The rule that a broker-time offset is trusted only when at least two fresh 24/7 witness ticks agree; otherwise `/candles` refuses.

**AI_ENABLED** — An empty flag file in `brain/`; its presence turns on the council path (`ai_enabled()`), toggled by the dashboard's `/api/ai-toggle`.

**Shadow symbol** — A symbol in `SHADOW_SYMBOLS` (default NVDA) judged and journaled but never dispatched; goes live only by removal from the list.

**BSv11 / LITE** — The 15-minute LITE Pine system; the brain only relays it to Telegram, v7 is the only bot that trades it.

**Alert ceremony** — Deleting and recreating every TradingView alert after any Pine save, because alerts freeze the script and its settings at creation.

**pine_ver** — The Pine version field appended to alerts; the journal's `pine_ver` distribution is the only proof of what is actually firing.

**Deploy ceremony** — backup → compile → restart → verify in logs/journal; anchor-safe edits only.

**Anchor-safe patch** — A script whose every OLD anchor must match exactly once or nothing is written; backs up, `py_compile`s, is idempotent.

**Release-gate artefact** — A Windows patch script plus golden tests proving byte-identical output to a repo commit, prepared for human-approved deployment to the non-git executor box.

**ISO-xx** — Numbered isolation/identity findings from the developer agent's Job 3 and Job 9 audits (ISO-09 login assertion, ISO-10 signed account, ISO-11 margin fail-closed, ISO-12 parked loss, ISO-13 account-scoped dedupe, ISO-14 no pending-to-market, ISO-15 no GUARDS_DISABLED bypass, ISO-16 global stop, ISO-19 code-computed payload, ISO-20 no default risk, ISO-21 no raw-stop fallback).

**ADR-004 / 005 / 006 / 008 / 009** — Developer-agent architecture decision records cited in code: identity asserted never inferred; execution values computed by code; no pending-to-market conversion; global emergency stop; account-local daily loss is a hard stop.

**Job 3 / Job 9** — Developer-agent audits: dual-MT5 isolation (2026-09-04) and LLM-computed execution values (2026-09-05).

**test_repro_ / test_golden_ / test_holds_** — Audit-test naming: a repro passes while a finding is still reproducible, a golden test passes on the fix, a holds test pins an invariant; verdicts PASS / FAIL / NOT RUNNABLE / UNKNOWN.

**INC-0001 / INC-0002 / INC-0003 / INC-0004** — Platform-tracked incidents: US10Y candle feed break (broker delisted the contract), bias alias mismatch, VPS heartbeat/reporter orphans, and the brain journal writer TypeError that lost 1–6 September decisions.

**LIVE-20260713-GHOST / LIVE-20260724-STUCKTERMINAL** — Incident tags for the ghost-approvals week and the MT5 LiveUpdate dialog outage that produced the bot-guards.

**BOT-P0-1 / BOT-P0-2 / BOT-P0-3 / BOT-BIAS-1** — Bot-side numbered items: journal outcomes never filled; brain minting its own signal_id; live bar served by `/candles`; US10Y bias staleness.

**Reporter (mt5_reporter)** — The platform repo's Windows service (`BrotherBotReporter`) that posts account/VPS heartbeats, trades and candles from the v7 terminal to app.signalmesh.dev; "ONE reporter process per box."

**Evidence Law** — Iron Rule 5: n<20 is luck, ~100 to judge, validate column decides, one organ per week.

**Freshness Law** — Platform-side law adopted here: stale or missing data is INVALID/UNKNOWN, never a positive; the reason ISO-11/ISO-12 fail closed.

**Organ** — One independently changed subsystem; the cadence rule is "one organ changed per week."

**Print mode** — `BRAIN_DISPATCH_MODE=print`: the brain signs and logs envelopes without POSTing; used for shakedowns.

**Contabo / Windows VPS / Amsterdam / Dublin / Frankfurt** — The boxes: brain and dashboard on Contabo; both MT5 executors on the Windows VPS; watchdog in Amsterdam; the retired Polymarket executor in Frankfurt (Dublin planned).

**signalmesh.dev** — The domain: `brain.` (webhook), `status.` (dashboard), `app.` (platform), `executor-pm.` (retired).
