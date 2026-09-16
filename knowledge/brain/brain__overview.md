---
title: Brother v18 Brain — Overview
domain: brain
repo: sabuj14eu/brother-brain-v2
sources: CLAUDE.md, README.md, brain/README.md, brain/src/main.py, brain/src/agents/council.py, brain/src/agents/*.py, brain/src/agents/PINE_SOURCE.md, docs/PINE_VS_BOT_MAP.md, docs/decisions.md, docs/AUDIT_2026-07-31.md, docs/SESSION_COORDINATION.md, dashboard/README.md, dashboard/backend/main.py, watchdog/README.md, executor_ic_markets/README.md, executor_polymarket/README.md, deploy/brother-brain.service, brain/push_bias.py, brain/push_news.py, brain/mirror_outcomes.py
verified_on: 2026-09-16
classification: INTERNAL
---

# Brother v18 Brain — what it is

The v18 brain (repo `sabuj14eu/brother-brain-v2`) is the intelligence tier of the Brother Sniper trading system. One TradingView Pine script (BrotherSniperULTIMATE, Pine v6) fires alerts to `brain.signalmesh.dev/webhook/v18`; the brain's 6-agent AI council judges every signal, and an approved signal is Ed25519-signed and dispatched to the Windows executor, which places the order on MetaTrader 5. All accounts are DEMO (CLAUDE.md "WHAT THIS IS"). The README calls the design "One Brain. Two Executors. One Watchdog. Zero shared wallet keys." — the brain holds only the Ed25519 signing key, never a wallet key or broker password (brain/README.md "What the Brain MUST NOT have").

The v18 brain is the successor to v17, which the README declares retired ("Old v17 / v8 rebuild files. Deleted, do not resurrect."). Its predecessor lesson is encoded in the executor: SL/TP are always attached on the initial `order_send`, never as a follow-up modify, because "the v17 bot had a known issue where SL/TP weren't always set correctly" (executor_ic_markets/README.md).

# Where the v18 brain runs

Per CLAUDE.md, the v18 brain runs on a Contabo Linux box at `/home/shyam/brain-v2/brain` as the systemd unit `brother-brain.service` (docs/decisions.md 2026-05-13: Restart on-failure, hardened with NoNewPrivileges/ProtectSystem=strict). It listens on port 8443 (`WEBHOOK_PORT`, brain/src/main.py) behind nginx, which terminates TLS for `brain.signalmesh.dev` and proxies to 127.0.0.1:8443 (decisions.md 2026-05-20). nginx also mirrors a copy of every Pine alert to the v7 bot (CLAUDE.md). The nginx geo block allows only TradingView's four webhook IPs plus loopback to reach `/webhook/*`; `/health` stays open (decisions.md 2026-05-21).

The v18 executor runs on a Windows VPS at `C:\brother_v18\executor_ic_markets` as NSSM service `SniperExecutorV18` on port 8080, attached to MT5 demo account 52901228 (CLAUDE.md; docs/EXECUTOR_DEPLOY_2026-07-31.md). The v7 bot, a separate mechanical arm in `/home/shyam/brother_sniper_v7`, uses its own bridge on port 5001 (NSSM `SniperExecutorV7`, MT5 52834417). The dashboard `status.signalmesh.dev` runs from `/home/shyam/brain-v2/dashboard/backend` as `brother-dashboard.service` on local port 9090 behind nginx (dashboard/README.md).

# Services and ports of the v18 system

| Component | Host | Service / port | Source |
|---|---|---|---|
| v18 brain (council + dispatcher) | Contabo | `brother-brain.service`, :8443 | CLAUDE.md, deploy/brother-brain.service |
| v18 executor (IC Markets, MT5 52901228) | Windows VPS | NSSM `SniperExecutorV18`, :8080 | CLAUDE.md |
| v7 bot bridge (MT5 52834417) | Windows VPS | NSSM `SniperExecutorV7`, :5001 | CLAUDE.md |
| Dashboard status.signalmesh.dev | Contabo | `brother-dashboard.service`, :9090 local | dashboard/README.md |
| MT5 scanner (DRY-RUN by design) | Contabo | `brother-scanner-mt5.service` | dashboard/backend/main.py service wall |
| Session caller (paper, 3x daily) | Contabo | `session-caller.timer` | dashboard/backend/main.py |
| v7 bot / analyst | Contabo | `sniper-bot.service`, `analyst-eye.service` | dashboard/backend/main.py |
| Polymarket executor | DigitalOcean (Frankfurt then Dublin planned) | `brother-executor-pm.service`, :8080 | decisions.md 2026-05-22, 2026-05-30 |
| Polymarket scanner | Contabo | `brother-pm-scanner.service` | decisions.md 2026-05-23 |
| Watchdog | Amsterdam droplet | systemd, pings every 30s, Telegram | decisions.md 2026-05-26, watchdog/README.md |

The Polymarket executor is DECOMMISSIONED: `dashboard/backend/patch_dashboard_remove_pm.py` says "executor-pm.signalmesh.dev, May build, server deleted", and `/api/services` labels the Polymarket scanner "RETIRED — project closed". Whether the watchdog droplet is still running is UNKNOWN from this repo (the dashboard shows it as "remote (Amsterdam) ... status not pollable").

Cron jobs on the brain box (from script docstrings): `push_bias.py` every 30 minutes (`*/30 * * * *`), `push_news.py` hourly at :17, `mirror_outcomes.py` every 10 minutes. All three post one-way to the platform at `app.signalmesh.dev` and can never place, modify or block a trade.

# The council members and what each judges

The v18 brain's council (`brain/src/agents/council.py`) runs Scout → Researcher → Quant → DevilsAdvocate → RiskManager with veto gates between stages; each agent is a separate Anthropic Claude call with its own system prompt and a JSON-only output contract (`brain/src/agents/base.py`). The default model is `ANTHROPIC_MODEL` (code default `claude-opus-4-7`), overridable per agent via `ANTHROPIC_MODEL_<AGENTNAME>` for cost tiering (08-17).

- **Scout** (`scout.py`): first pass, answers PROCEED / SKIP / DEFER. Skips on ambiguous setup, wide spread, stop far too tight vs ATR, R:R worse than 1:1 (except the PULLBACK class), macro event within 30 minutes. It is told never to second-guess absolute price levels ("Pine reads TradingView's live price feed") and always emits a display-only teaching `proposal`.
- **Researcher** (`researcher.py`): builds an intelligence packet via the `web_search` tool (bull case, bear case, sources, `confidence` 0-1). It must not restate scheduled economic events, which arrive from the calendar feed. Its `run()` override is allow-listed but must still call the budget guard and spend ledger (`brain/tests/test_agent_outbound_path.py`).
- **Quant** (`quant.py`): calibrated fair value with a 90% CI and `edge`; `preferred_side` of PASS rejects with "no edge". Anti-circularity rule (07-09): fair_value must be derived independently of the signal's TP. For PULLBACK signals it is given measured base rates (Asia 73.6% / NY 54.8% / London 52.5% WR to TP1, PF 1.45).
- **DevilsAdvocate** (`devils_advocate.py`): adversarial, holds veto power; attacks broken instances, never the validated PULLBACK class design. A Devil failure is retried once and, if it fails again, tagged `failed: true` and skipped (fail-soft, audit P1-1).
- **RiskManager** (`risk_manager.py`): sizes the position (Kelly-capped: one-tenth Kelly for Polymarket, quarter Kelly for FX), can veto on portfolio grounds, and for FX outputs no prices — only bounded `sltp_params` and a `risk_pct` it may lower but never raise.
- **ExecutorPrep** (`executor_prep.py`): the former sixth agent that assembled the executor payload. Since ISO-19 (2026-09-05, ADR-005) it is retired from the pipeline: `build_execution_payload()` in council.py computes entry/SL/TP/risk in code and `_validate_prep_payload()` belts the result. The trace key `executor_prep` is kept one release for mirror and dashboard readers.
- **PositionManager** (`position_manager.py`): a single call on the MANAGE path when a fresh alert arrives for a symbol with an open v18 position; returns HOLD, MODIFY (favorable-only stop) or CLOSE_ONE. Budgeted per ticket (3 calls, 30-minute cooldown, `manage_state.py`).

# How the v18 brain relates to Pine, v7, the platform and the developer agent

**Pine is the signal factory and first filter.** docs/PINE_VS_BOT_MAP.md: "Pine is the signal FACTORY and the first (biggest) filter. The bots are the JUDGES and the risk police." The canonical Pine lives in `Sniper-System/pine/BrotherSniperULTIMATE_v18_FINAL_v6.pine`; a stale v18.7 copy was removed from this repo on 2026-08-19 because "a second copy of a file that must have exactly one version is a trap" (brain/src/agents/PINE_SOURCE.md). TradingView alerts freeze the script at creation, so only the journal's `pine_ver` field proves what is running.

**v7 is the independent mechanical arm.** The same Pine payload reaches the v7 bot through the nginx mirror; v7 re-decides with its own dials, survivable-stop floor and margin gate, on a different MT5 account (52834417). The v18 brain and v7 share contracts (platform mirror `pine_signal_id` join key, candidate id `SC-<SIDE>-<UTCstamp>`, outcome truth by ticket) per docs/SESSION_COORDINATION.md. Both arms read one shared emergency-stop file (`GLOBAL_STOP`, ISO-16).

**The platform (Sniper-System, app.signalmesh.dev) is a read-only display.** `brain/src/platform_mirror.py` states the law: "the platform DISPLAYS what the council decided. It never dispatches trades, never modifies signals, never becomes an input to a trading decision." The brain posts decisions (`/webhooks/brain/signal`), executor outcomes and backfills (`/webhooks/brain/decision`), bias (`/webhooks/brain/bias`), the economic calendar (`/webhooks/brain/news`) and a brain_status heartbeat (`/webhooks/brain/artifact`).

**The developer agent (brother-developer) audits and proposes; the human deploys.** The ISO-xx findings, ADR references (ADR-004 identity, ADR-005 code computes execution values, ADR-006 no pending-to-market conversion, ADR-008 global stop, ADR-009 daily loss hard stop), Job 3 (dual-MT5 isolation) and Job 9 (LLM-computed execution values) come from that agent's spec; this repo carries the reproductions under `tests/audit/` and `brain/tests/audit/`, the fixes, and anchor-safe release-gate patch scripts for the non-git Windows box.

# Signal routing in one paragraph

A Pine alert hits `/webhook/v18`, passes an optional body secret and a 300-second in-memory dedupe, and `BSv11` (LITE) payloads are Telegram-only and never judged (07-09, Shyam's order). The webhook answers TradingView immediately and runs `_run_v18_council` in the background (TradingView times out at 3 seconds, decisions.md 2026-05-21). Grades C/D are journaled and mirrored at zero cost (GradeGate, 08-09). With the `AI_ENABLED` flag file absent, the AI-OFF path checks the executor slot and approves from Pine trust; with AI on, an occupied slot routes to PositionManager under a cost gate, a free slot passes the margin gate (floor max(10% balance, $100)), market vision (real OHLCV from executor `/candles`), and the grade gate (council only for A/A+ and one-in-three B). An approved payload gets `signal_id` appended, is signed with `account_id`, and is POSTed to the executor's `/signal`; the decision is journaled to `logs/decisions.jsonl` and mirrored to the platform. Shadow symbols (default NVDA) are judged and journaled but never dispatched.
