---
title: The map of Shyam's projects and where each runs
domain: brother
repo: sabuj14eu/AIHELPER
sources: Sniper-System/CLAUDE.md, brother_sniper_v7/CLAUDE.md, brother-brain-v2/CLAUDE.md, brother-developer/CLAUDE.md, Accounting-/CLAUDE.md
verified_on: 2026-09-16
classification: INTERNAL
---

# The six repositories

Shyam's work lives in six GitHub repositories under the account sabuj14eu.
Five of them form one trading system plus its engineering agent; the sixth is
an unrelated accounting business, separated on purpose.

The Brother Sniper trading system has one Pine script (BrotherSniperULTIMATE,
Pine v6, on TradingView) that fires alerts to the v18 brain's webhook; nginx
mirrors a copy of every alert to the v7 bot. Every account in the system is a
DEMO account. The platform observes and manages; it never trades.

# sabuj14eu/Sniper-System — the platform

Sniper-System is the multi-tenant SaaS platform: public site, user dashboard,
admin, Trade Desk, evidence tables, Model Lab and the Pine workspace. It is a
FastAPI application with SQLAlchemy models, Jinja2 templates, a Caddy front
and Docker Compose. It receives a read-only mirror of signals and decisions
from the v18 brain for display, journaling and analytics. No code path in the
platform may send an order, a dispatch or an instruction to an executor. Its
constitution is Sniper-System/CLAUDE.md; its living handoff is
docs/HANDOFF_PLATFORM_SESSION.md; deferred work of both sides is in
docs/OPEN_ITEMS.md. Versions are numbered v5.xx. The pine/ folder holds the
indicator (v18.12.x) and its release notes.

# sabuj14eu/brother-brain-v2 — the v18 brain

brother-brain-v2 is the v18 brain on the Contabo box
(/home/shyam/brain-v2/brain): a six-agent AI council judges every signal and
produces an Ed25519-signed dispatch to the Windows executor on port 8080 (NSSM
service SniperExecutorV18, MT5 account 52901228). The dashboard at
status.signalmesh.dev lives in dashboard/backend. Analytics live in the brain
directory: truth_layer, scorecard, pullback_backtest, council_calibration,
weekly_source_report, session_caller. Nothing bypasses the council; the last
bypass, an MT5 scanner, lost 60R and is retired.

# sabuj14eu/brother_sniper_v7 — the v7 bot

brother_sniper_v7 is the mechanical arm on the bot box
(/home/shyam/brother_sniper_v7): its own filters, news gate, risk engine,
learning and governance, sending to the bridge on port 5001 (NSSM service
SniperExecutorV7, MT5 account 52834417). It receives the nginx mirror of every
Pine alert. It posts outlooks, readiness and incidents to the platform with
the post_*.py tools, which are display data only and can never place, modify
or cancel a trade. Its journal is logs/decisions.jsonl and the journal, not
memory, is how claims are checked.

# sabuj14eu/brother-developer — the engineering agent

brother-developer is the Brother Developer agent: engineering intelligence
for the three trading repositories. It reads everywhere, writes only in a
sandbox worktree, deploys only through the human release gate and never
trades. It diagnoses in a fixed order (SYMPTOM, ROOT CAUSE, AFFECTED, WHY
TESTS MISSED IT, FIX, RISKS, TEST PLAN), keeps a hash-chained ledger and ten
ADRs, and classes every change P0 to P4. Its verdicts are PASS, FAIL, NOT
RUNNABLE, UNKNOWN or NOT TESTED, and UNKNOWN is never PASS. Phase 1 (read-only
intelligence) is built; Phase 2 (sandbox repair) waits on Job 1, the dual-MT5
isolation audit.

# sabuj14eu/Accounting- — the accounting application

Accounting- is the Polish JDG accounting application at account.signalmesh.dev,
built on the Liberu ERP with a standalone, framework-free Poland tax engine
(modules/poland). It never touches trading: no shared database, queue, Redis,
session store or credential. The only permitted link is a hyperlink from
SignalMesh to it, and bin/check-isolation.sh enforces the separation before
every deploy. The same repository holds a second, separate application,
shop-intelligence/, for the shop's money reconciliation, stock and real
profit; the two share nothing.

# sabuj14eu/AIHELPER — this assistant

AIHELPER is AI Helper, the self-hosted local-first AI gateway that Brother
runs in. It answers from deterministic tools, then memory and documents, then
a local Ollama model, then validation, and only then, if allowed, a paid
provider. It imports nothing from the other repositories; it knows them
through this knowledge pack, which is data.

# The boxes

The Contabo box is the Linux server running the v18 brain, the dashboard and
nginx. The bot box is the Linux host of the v7 bot. Two Windows machines run
the MT5 executors as NSSM services (v18 on port 8080, v7 bridge on port 5001).
The platform runs under Docker Compose behind Caddy. The accounting
application runs under nginx and systemd. Where the knowledge pack does not
name a host for a component, the host is UNKNOWN.
