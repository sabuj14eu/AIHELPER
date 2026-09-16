---
title: The toolchain Shyam's projects use
domain: brother
repo: sabuj14eu/AIHELPER
sources: Sniper-System/requirements.txt, Sniper-System/docker-compose.yml, Sniper-System/Caddyfile, brother_sniper_v7/sniper-bot.service, brother_sniper_v7/gunicorn.conf.py, brother-brain-v2/deploy, brother-developer/pyproject.toml, Accounting-/composer.json, Accounting-/deploy, AIHELPER/docker-compose.yml
verified_on: 2026-09-16
classification: INTERNAL
---

# Languages and frameworks

The trading side is Python. The platform (Sniper-System) is FastAPI with
SQLAlchemy models, Jinja2 templates and Alembic-style migration notes; the v7
bot serves its webhook with gunicorn under a systemd unit (sniper-bot.service);
the v18 brain is Python with an Ed25519 signing step between the council and
the executor. The Brother Developer agent is a Python package with a
pyproject.toml. The accounting side is PHP: the Liberu ERP on Laravel, with
the Poland tax engine as a standalone Composer package that must not import
Laravel. AI Helper is Python on FastAPI, SQLAlchemy, pydantic-settings and
structlog.

# Trading instruments

TradingView runs the Pine v6 indicator BrotherSniperULTIMATE and fires alerts
by webhook. MetaTrader 5 (MT5) is the broker terminal on two Windows machines,
driven through the MT5 Python API by the executors; NSSM runs the executors as
Windows services (SniperExecutorV18 on port 8080, SniperExecutorV7 bridge on
port 5001). nginx on the Contabo box receives Pine's alerts for the brain and
mirrors a copy to the v7 bot. The MT5 reporter pushes candles to the platform
and must obey the two-witness clock rule.

# Serving and deployment

The platform runs under Docker Compose behind Caddy (Caddyfile in the
repository). The brain and its dashboard deploy per docs/DEPLOY_RUNBOOK.md and
docs/HANDS_OFF_DEPLOY.md with backup, compile, restart and verification steps.
The v7 bot deploys with patch_*.py scripts that back up, check their anchors
and abort on ambiguity, plus deploy_windows.py for the bridge side. The
accounting application deploys with nginx and systemd units in deploy/, a
verified backup script, and bin/check-isolation.sh which runs before every
deploy. AI Helper ships a Docker Compose stack: the gateway, PostgreSQL,
Qdrant, Ollama, Open WebUI and n8n, ports bound to localhost.

# Testing

pytest -q before every commit in every Python repository; the platform's tests
are smoke tests over the whole route surface, the developer agent's suite was
at 296 green tests at its P0 release report. The accounting repository runs
modules/poland/vendor/bin/phpunit and bin/check-isolation.sh before every
commit, and shop-intelligence runs its own phpunit and
bin/check-shop-isolation.sh. The trading repositories keep audit fixtures
under tests/audit/<date>_<job>/ with prepatch and expected copies of the files
a patch touches, so a fix is proven by diff, not by description.

# Evidence tooling

The backtest harness with a train/validate split (the VALIDATE column
decides). The journal logs/decisions.jsonl on the bot box, grepped before any
claim is believed. Analytics in the brain directory: truth_layer, scorecard,
pullback_backtest, council_calibration, weekly_source_report, session_caller.
On the platform: the Trade Desk, lanes, evidence tables, the outlook board,
candle audit (services/candle_audit.season_check), the Model Lab with a
hard-capped variant family and a single-use holdout.

# Automation and notification

n8n workflows ship with AI Helper (budget watch, document ingestion, fallback
review, nightly maintenance). The v7 bot posts outlooks, readiness and
incidents to the platform with post_outlook.py, post_readiness.py,
post_incident.py and post_weekly_outlooks.py; these send display data only and
refuse to build a confidence or probability figure. The platform has a notify
service; which channels it reaches is UNKNOWN to this pack unless the platform
digest says otherwise.

# Version control and sessions

GitHub under sabuj14eu, one working branch per session, commits with clear
messages, and a handoff document updated at every session end
(docs/HANDOFF_PLATFORM_SESSION.md on the platform, SESSION_COORDINATION.md on
the bot and brain, SESSION_PROTOCOL.md for the developer agent). AI Helper's
own history is in docs/CHANGELOG.md and its audit in audit/AUDIT_REPORT.md.

# Local AI

AI Helper runs Ollama for local inference (default llama3.2:3b, small
llama3.2:1b, strong qwen2.5:7b) and nomic-embed-text for embeddings. Paid
providers (Anthropic, OpenAI) are off by default and need both a flag and a
key; budgets are hard stops with no override path. Without nomic-embed-text
the embedder is a lexical fallback and paraphrases will not be matched; the
dashboard says so.
