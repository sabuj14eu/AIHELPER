---
title: Sniper-System platform overview
domain: platform
repo: sabuj14eu/Sniper-System
sources: CLAUDE.md, README.md, docs/HANDOFF_PLATFORM_SESSION.md, docs/DEPLOYMENT.md, docs/SERVICE_AUDIT_2026-08-08.md, docs/audits/COMBINED_FORENSIC_AUDIT_2026-08-13.md, docs/V7_SELF_DEPENDENCE_PLAN.md, app/main.py, app/version.py, app/config.py, docker-compose.yml, Dockerfile, Caddyfile, agents/mt5_reporter/README.md
verified_on: 2026-09-16
classification: INTERNAL
---

# Sniper-System platform — overview

## What the Sniper-System platform is

The Sniper-System repository (GitHub `sabuj14eu/Sniper-System`, internally called the "Brother Bot Platform") is the multi-tenant SaaS platform for the Brother Sniper trading system. Per README.md it provides a public website, phone/email registration with OTP, a per-user trading dashboard, MT5 account management, Telegram/SMS notifications, analytics, a risk manager, subscriptions/wallet/affiliate, support tickets, and a full admin + super-admin back office, in one codebase. On top of that it carries the Trade Desk, the evidence tables, the Evidence Lab, the Model Lab / Strategy Factory, the outlook board, the engineering watchers, and the Pine workspace.

The Sniper-System platform's safety invariant, stated in README.md and CLAUDE.md Iron Rule 1: the platform NEVER dispatches trades or signals. It receives a **read-only mirror** of the v18 brain's decisions (and v7's decision stream) for display, journaling and analytics. No code path in the repo may send an order, a dispatch, or any instruction to an executor.

## Who the platform is for

The Sniper-System platform's owner and primary operator is Shyam (GitHub `sabuj14eu`). docs/HANDOFF_PLATFORM_SESSION.md describes how he works: he pastes commands into a terminal, reads screens "the way an auditor reads a ledger", and found real bugs three days running by noticing two numbers on one page that could not both be true. The platform is designed as a multi-tenant SaaS "built to scale from a handful of users to thousands", but as of the handoff all connected accounts are DEMO.

## The wider Brother Sniper system (as documented in this repo)

Per CLAUDE.md and docs/SERVICE_AUDIT_2026-08-08.md, the Brother Sniper system has these parts:

- **Pine / TradingView** — one Pine v6 indicator, `BrotherSniperULTIMATE`, fires alerts to `brain.signalmesh.dev/webhook/v18`; nginx mirrors a copy to the v7 bot. The indicator source is versioned in this repo under `pine/`.
- **v18 brain** (the "bot box", a Contabo Linux box, `/home/shyam/brain-v2/brain`) — a 6-agent AI council judges every signal, then an Ed25519-signed dispatch goes to a Windows executor on port 8080 (NSSM service SniperExecutorV18, MT5 login 52901228).
- **v7 bot** (`/home/shyam/brother_sniper_v7`, also on the bot box) — the mechanical arm with its own filters; it POSTs to a bridge/executor on port 5001 (SniperExecutorV7, MT5 login 52834417). The v7 bot never talks to MT5 directly; the executor pins its own terminal path.
- **This platform** — deployed at `/srv/brotherbot` on the Linux box named `vmi3221804`, served at `app.signalmesh.dev`. Branch `claude/brother-bot-trading-platform-58o7gr`.
- **Dashboard** — `status.signalmesh.dev` (bot-box side, `/home/shyam/brain-v2/dashboard/backend`).
- **MT5 reporter** (`agents/mt5_reporter/`) — a Windows-side agent, running as NSSM service `BrotherBotReporter` on the VPS next to the MT5 terminals, that posts heartbeats and closed candles to the platform. The platform serves it at `/downloads/mt5-reporter.py` with a `.sha256`.
- **Brother Developer agent** (separate repo `brother-developer`) — engineering intelligence that reads all three repos, writes only in a sandbox, deploys only through a human gate and never trades.

The Sniper-System platform relates to these as an observer: it mirrors what the brain and v7 decide, stores what the reporter measures, and never sends anything back. docs/INTEGRATION_V7.md: "Direction stays one-way: v7 → platform. The platform never sends anything back to a bot."

## Ownership split between sessions

docs/HANDOFF_PLATFORM_SESSION.md fixes the division: the platform session owns this repository only. The bot and brain side belongs to another Claude session; the platform session may READ `/home/shyam/brain-v2` and `/home/shyam/brother_sniper_v7` to explain a log line but never touches or proposes changes to them. Shyam relays messages between the two sessions; they do not talk directly. docs/HANDOVER_V7_DESK.md adds: "Ship a payload contract, not a pull request", because the two halves auditing each other across a data contract found most of the month's real bugs.

## Stack

Per README.md, requirements.txt, Dockerfile and docker-compose.yml, the Sniper-System platform runs on FastAPI + SQLAlchemy 2 (SQLite for dev, Postgres 16 in production), server-rendered Jinja2 with Tailwind + Chart.js via CDN (no build step), a REST API v1 with API-key auth, JWT session cookies, TOTP 2FA, hashed OTPs, and encrypted MT5 credentials. Production is a Docker Compose stack: `app` (uvicorn, 4 workers since v4.82), `db` (postgres:16-alpine), `redis` (reserved, "NOT CONSUMED" per the service audit), `caddy` (auto-HTTPS reverse proxy to `app:8000`). `tzdata` is pinned in requirements. CI (`.github/workflows/ci.yml`) runs `python -m pytest -q` on every push.

## Ports and hostnames documented in the repo

- Platform: `app.signalmesh.dev`, container port 8000 behind Caddy (80/443). Dev: `http://127.0.0.1:8000/`.
- Brain ingress: `brain.signalmesh.dev/webhook/v18`.
- v18 executor: Windows VPS port 8080. v7 executor/bridge: Windows VPS port 5001 (also serves `/candles`, `/spread`, `/symbolspec` to the platform's live chart bridge).
- Status dashboard: `status.signalmesh.dev`.
- MT5 logins: 52834417 (v7, canonical candle source `mt5:52834417`), 52901228 (v18; "NOT EXPECTED" as a reporter writer since 2026-08-27 per CHANGELOG 5.13).
- Health: `/healthz` (process up), `/readyz` (DB answers), `/metrics` (Prometheus; token- or admin-gated since v4.99).

## Repository layout

Per CLAUDE.md "LAYOUT" and the tree:
- `app/main.py` — FastAPI app factory; all routers mounted; the sweeper loop (60 s, one worker elected by flock) and startup repairs (news mapping backfill, signal status repair).
- `app/models/` — `user.py`, `trading.py`, `billing.py`, `platform.py` (SQLAlchemy).
- `app/services/` — ~70 business-logic modules (desk, collector, outlook, candle_audit, evidence_integrity, engineering, fail_soft, position_state, bar_clock, feed_diag, news_lens, trade_twins, freshness, modellab, factory, ai_analyst, ai_ledger, bridge, mgmt, market_map, sweeper, ...).
- `app/routers/` — public, auth, dashboard, accounts, settings_bot, trading, billing, account_misc, admin, api_v1, webhooks (brain mirror ingest), intel, chart, planner, session_center, scanner_page, factory_page, strategy_lab, workspace.
- `app/templates/` — `public/`, `dash/`, `admin/` on shared bases; `app/static/`.
- `app/version.py` — `VERSION = "5.24"` at HEAD; printed on every page.
- `agents/mt5_reporter/` — the Windows reporter (`REPORTER_VERSION = "1.7.0"`) and its README.
- `scripts/` — `seed.py`, `backup.sh`, `audit_candle_offsets.py`, `bias_coverage.py`, `dedupe_trade_twins.py`, `outlook_audit.py`, `page_timing.py`, `page_split_timing.py`.
- `tests/` — ~80 files, 719 test functions counted on disk (CHANGELOG 5.24 reports 723 passing).
- `docs/` — CHANGELOG.md (6,382 lines, 191 sections), OPEN_ITEMS.md, HANDOFF_PLATFORM_SESSION.md, HANDOVER_V7_DESK.md, V7_SELF_DEPENDENCE_PLAN.md, INTEGRATION_V7.md, DEPLOYMENT.md, SERVICE_AUDIT_2026-08-08.md, `audits/COMBINED_FORENSIC_AUDIT_2026-08-13.md`.
- `pine/` — `BrotherSniperULTIMATE_v18_FINAL_v6.pine`, `BrotherSniper_AssetPulse_v1.pine`, release notes v18.9–v18.12, `PINE_v18.9_SPEC.md`, `V18.10_PLAN.md`, `BREAKOUT_HARNESS_SPEC.md`.

## Major pages (routes) of the Sniper-System platform

From the routers: user-side `/dashboard`, `/signals`, `/journal`, `/analytics`, `/trading`, `/desk` (Trade Desk), `/evidence` (Evidence Lab, since v5.11), `/three-lane`, `/v7` (v7 Desk), `/chart`, `/live-bridge`, `/radar`, `/watchlist`, `/asset/{symbol}`, `/macro`, `/council`, `/funnel`, `/grades`, `/planner`, `/ai-trading`, `/session`, `/session-analysis`, `/scanner` (+ history/outcomes), `/factory`, `/modellab`, `/research`, `/research-brief`, `/decision-lab`, `/event-reaction`, `/event-impact`, `/playbook`, `/matrix`, `/readiness`, `/brain-view`, `/brain-docs`, `/calendar`, `/correlation`, `/strategy` runs/compare. Admin: `/admin`, `/admin/users`, `/admin/engineering` (watchers + incidents, v5.00), `/admin/services` (service map), `/admin/data` (data health), `/admin/email`, `/admin/ai`, `/admin/engine`, `/admin/finance`, `/admin/cms`, `/admin/system`. Public: `/`, `/pricing`, `/performance`, `/status`, `/docs-site`, `/changelog`, `/blog`, `/legal/{doc}`, `/downloads`.

## Where the platform stands (as of the last commits)

Git HEAD is `3257184 v5.24 — the drift banner says when, not "reload"` (2026-09-03). docs/OPEN_ITEMS.md "START HERE": v5.24 ready, v5.23 live with its migration applied 2026-09-03 10:35 UTC, no migration pending. Phase 1 of the V7 self-dependence plan is complete as engineering on both sides; Phase 2 (statistics-only conditional tables) has not started (docs/V7_SELF_DEPENDENCE_PLAN.md §8, docs/HANDOVER_V7_DESK.md). Everything shipped in v5.00–v5.24 is observability or display: "No gate, no threshold, no sizing and no signal path was touched; the platform still cannot place an order" (CHANGELOG 5.10).
