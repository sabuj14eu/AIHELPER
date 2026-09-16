---
title: Sniper-System platform workflows and tools
domain: platform
repo: sabuj14eu/Sniper-System
sources: CLAUDE.md, README.md, docs/HANDOFF_PLATFORM_SESSION.md, docs/DEPLOYMENT.md, docs/OPEN_ITEMS.md, docs/CHANGELOG.md, docs/HANDOVER_V7_DESK.md, docs/SERVICE_AUDIT_2026-08-08.md, pine/V18.9_RELEASE_NOTES.md, agents/mt5_reporter/README.md, scripts/backup.sh, scripts/audit_candle_offsets.py, scripts/bias_coverage.py, scripts/dedupe_trade_twins.py, scripts/page_timing.py, app/version.py, Dockerfile, docker-compose.yml, .github/workflows/ci.yml, requirements.txt
verified_on: 2026-09-16
classification: INTERNAL
---

# Sniper-System platform — how work is done here

## The house method (CLAUDE.md "HOW TO WORK HERE" and HANDOFF §7)

Findings first, then code. Small verified diffs over rewrites. Run `pytest -q` before every commit — the full suite, not a subset, and report the count. All user-visible money/risk numbers come from the database, never hardcoded in templates. The handoff's ordered habits: (1) trace the paste in code and say in one sentence what is wrong; (2) ask which question each number answers and whether the page says so; (3) refuse any inference from absence, silence or a single witness; (4) keep the decision where it is — display fixes touch display, proven by an `ast`-parsing test; (5) anchor-safe edits, one organ per change, a test that RENDERS the branch, `pytest -q`, commit, push, deploy line, expected output; (6) write the CHANGELOG as a story of what was wrong; (7) put every deferred thing in `docs/OPEN_ITEMS.md` with a falsifier ("finding if: ..."); (8) report faithfully, paste failures; (9) close with a recap that stands alone — answer first, then what changed, then the deploy line, then what is open, no "let me know if".

## Test command and test conventions

`pytest -q` (README.md, CLAUDE.md). CI runs `python -m pytest -q` on every push (`.github/workflows/ci.yml`, Python 3.12). Suite size by release: 91 (2026-08-08 audit) → 163 (v3.1) → 225 (v4.0) → 280 (v4.8) → 486 (v4.52) → 618 (v5.00) → 723 (v5.24). House test patterns recorded in the CHANGELOG: guard tests that parse a module with `ast`, blank string literals and fail on verdict vocabulary or forbidden imports (`test_no_new_intelligence_is_computed_here`, v5.00); "one door" guards that ban SDK imports and hostnames outside `services/ai_ledger.py` (v4.10, proven by planting a bypass); structural tests that forbid `int(r["time"]) - BROKER_OFFSET_S` or the "Assuming 0" fallback from returning (reporter v1.4/1.5); regression locks on frozen engine arithmetic (`test_the_original_auto_v1_maths_is_frozen`); column-width tests in Python because SQLite ignores VARCHAR (`tests/test_column_widths.py`, v4.6); tests that render a page for the symbol that enters a conditional block (v5.14); tests that create throwaway users and restore rows exactly as found, never deleting a row they did not create (v4.71, v5.06). Guard tests are verified "red with the bypass present, green without it".

## Versioning and commit style

`app/version.py` holds `VERSION` (5.24 at HEAD), bumped in the same commit as the release it names and printed on every page (v4.33; v4.52's forgotten bump is recorded as its own postscript). Release numbering is `v5.xx` for the platform (earlier `v1.0.0` … `v4.99`), `1.x.0` for the MT5 reporter (`REPORTER_VERSION`), `v18.x` for Pine, and read-model names carry their own version strings (`lane-resolve-v1`, `mgmt-v1`, `feed-diag-v1`, `bar-clock-v1`, `position-state-v1`, `trade-twins-v1`). Commit subjects read as a story: `v5.19 — one SELL position opened both cards: the direction was lost at one line`; docs-only commits are prefixed `docs:`; agent-only changes `agents:`/`scripts:`. Every release gets a CHANGELOG section headed `## 5.xx — <what was wrong>` ending with the test count and either "No migration" or a MIGRATION block. Never open a pull request unless Shyam explicitly asks (HANDOFF §1). Branch: `claude/brother-bot-trading-platform-58o7gr`.

## Migration rule (Iron Rule 6)

Every schema change ships with a migration note in docs/CHANGELOG.md. `create_all` creates NEW tables on startup but never alters an existing one; column additions and index creation are explicit SQL the operator runs BEFORE the new code starts, because "code ahead of its migration is DOWN, not degraded" (v5.00, v5.07). Migration blocks are written as one paste with the expected output, e.g. v5.23: run `scripts.dedupe_trade_twins` dry, read it, then `--apply` and `CREATE UNIQUE INDEX IF NOT EXISTS uq_trade_ticket …`, correct output `0 refused` then `open_rows_for_ticket = 0`. SQLite/dev auto-creates; Postgres does not. A startup schema guard (refuse to start when code is ahead of its migration) is still owed (HANDOFF §5).

## Deploy ceremony

CLAUDE.md: backup → migrate → restart → verify logs. docs/DEPLOYMENT.md §8: `cd /srv/brotherbot && ./scripts/backup.sh && git pull && docker compose up -d --build && docker compose logs --tail 50 app && curl -s https://app.yourdomain.com/readyz` — "verify in logs, not just exit codes". The standing deploy line from the handoff (no migration unless the CHANGELOG says so):

```
cd /srv/brotherbot && git pull && docker compose up -d --build app && sleep 20 && docker compose logs --tail 30 app
```

Correct output: `Uvicorn running` / `Application startup complete`, no traceback, and the version chip on any page reads the new VERSION. Since v4.82 a Dockerfile CMD change needs `--build`, not a plain restart. Nightly backups: `scripts/backup.sh` via cron at 03:00 with 14-day retention, dumps in `./backups` (mounted into the app read-only so the candle-wipe gate can verify a dump exists), and a restore rehearsed with `pg_restore`. Never `git checkout` another branch on the box (services load whatever the checkout says on next restart); take one file with `git checkout origin/<branch> -- path`.

## How commands for Shyam are written (HANDOFF §2)

He pastes into a terminal and will not fill in blanks. One paste per step. No placeholders, ever (not `<your-path>`, not `<symbol>`). Every block starts with `cd /absolute/path && ...`. Name the box on the line above the block (`Linux box: vmi3221804`; the Windows VPS for reporter commands). Say what correct output looks like after every block. When he pastes a screen and says something is wrong, "he is nearly always right, and the bug is nearly always bigger than the sentence he wrote" — trace it in code before answering, never explain a paste away. Answer the question he asked first, in one line, then the detail. He says "sir" out of courtesy; the reply does not need to.

## Handoff practice

`docs/HANDOFF_PLATFORM_SESSION.md` is the living handoff for the platform session: what this side owns, how Shyam works, the state at handoff, the working laws, and the paste-ready opening prompt for a new window (§8). It is updated at every handoff; the new window confirms it has read CLAUDE.md, the handoff, OPEN_ITEMS and CHANGELOG 5.16/5.17 by stating the current version, the test count, the one thing seen and not acted on, and the three laws most likely to be tested next. `docs/OPEN_ITEMS.md` carries the deferred work of BOTH sides — "an item deferred in conversation is an item forgotten"; delete an entry only when done and verified, saying where the proof is; "won't do" is legitimate, silent dropping is not. Bot-box coordination goes through Shyam relaying between sessions; the two repos never take write access to each other ("Ship a payload contract, not a pull request", HANDOVER_V7_DESK.md).

## Tools and services in use

- **FastAPI, SQLAlchemy 2, Jinja2, pydantic-settings, PyJWT, httpx, psycopg** (requirements.txt); Tailwind + Chart.js via CDN, no build step.
- **pytest** (local + GitHub Actions CI).
- **Docker Compose + Caddy** (auto-HTTPS reverse proxy to `app:8000`), **Postgres 16**, **Redis 7** (in the stack, "NOT CONSUMED"), **uvicorn** 4 workers, **Sentry** optional (`BB_SENTRY_DSN`), **Prometheus** `/metrics` (token/admin gated), uptime monitor on `/readyz`.
- **Brevo** (HTTP mail API, free tier ~300/day) or SMTP for verification/recovery codes; **Twilio** optional for SMS OTP; **Telegram** bot notifications.
- **MT5 reporter** (`agents/mt5_reporter/mt5_reporter.py`, Python + `MetaTrader5`, `requests`, `psutil`, `tzdata`) on the Windows VPS as NSSM service `BrotherBotReporter`; one-shot commands `backfill` and `depth`; env `BB_PLATFORM_URL`, `BB_API_KEY`, `BB_CANDLE_SYMBOLS` (append, set at the NSSM registry level or the service ignores it), `BB_CANDLE_TFS`, `BB_BACKFILL_BARS`, `BB_PUSH_CANDLES`, `BB_BROKER_TZ`, `BB_BROKER_UTC_OFFSET` (pin), `BB_GIT_COMMIT` or a `DEPLOYED_COMMIT` sidecar. The platform serves it and a sha256 at `/downloads/`; provenance is settled with `Get-FileHash`, never a paste.
- **Live bridge**: the v7 executor's HTTP `/candles` on port 5001, proxied by `services/bridge.py`.
- **Pine v6 on TradingView**: `pine/BrotherSniperULTIMATE_v18_FINAL_v6.pine` and `BrotherSniper_AssetPulse_v1.pine`; alert ceremony after every save (delete + recreate all "Any alert() function call" alerts, same ingress URL, verify `pine_ver` in the brain log, confirm v7 mirror, hands off — pine/V18.9_RELEASE_NOTES.md).
- **AI narration**: a single metered door `services/ai_ledger.call_messages` (model configured by `BB_AI_MODEL`), weekly cap 10 USD, research-only.
- **n8n / other automation**: UNKNOWN — not mentioned anywhere in this repository.
- **systemd**: a bare-metal alternative unit `brotherbot.service` is documented in DEPLOYMENT.md; the bot box's v7 runs as `sniper-bot.service` with gunicorn `workers=1` (service audit).

## Operational scripts (run inside the app container)

- `python -m scripts.seed` — plans, brokers, server nodes, demo admin + demo user (idempotent).
- `python -m scripts.audit_candle_offsets` — the timestamp-shift audit; purge refused with exit 2 unless `--dst-answered`; `wipe_series` needs `--dump-file` and a fresh depth probe; `--wipe-rebuilt` to wipe a freshly rebuilt series.
- `python -m scripts.bias_coverage` — bias/council/spread/candle ages per symbol and the relay paste for the brain session (read-only).
- `python -m scripts.dedupe_trade_twins [--apply]` — v5.23 twin removal, dry-run by default.
- `python -m scripts.outlook_audit GOLD SILVER …` — stored outlook rows and the exact row each page would use.
- `python -m scripts.page_timing GOLD SILVER ETH` and `python -m scripts.page_split_timing` — best-of-three section timings against production volumes ("measure 'cheap' on the box before believing it").
- `scripts/backup.sh` — nightly pg_dump (stored executable in git since v5.08 era commit `484f070`).

## The working laws from the handoff, applied as workflow

Never infer from silence (the platform states LIVE/STALE/NEVER_POSTED/UNREACHABLE/NOT_EXPECTED/RETIRED as separate facts, the last two by human decision). One word carrying two facts is the fault to hunt (split it into two named fields; keep the old value). A threshold is never moved as a side effect (a display or naming fix must prove, by test, that nothing gates on what changed). Render the branch, do not grep for the words (a template block that executes for one symbol gets a test that uses that symbol). Two right numbers with no anchor are a bug (name the timestamp, reference price, timeframe and scope). Recorded evidence is never redefined midway (add a labelled second number). Add keys, never rename. Secrets never reach chat, logs, templates or commits.

## Adding an asset (OPEN_ITEMS checklist, learned 2026-09-02)

Three places: `SYMBOL_ALIASES` (`app/routers/webhooks.py`) BEFORE the feed turns on; `CORE_UNIVERSE` (`app/routers/scanner_page.py`) for the Daily Market Brief (costs one AI brief per symbol per session block, so it grows one named asset at a time); the reporter's symbol list on the bot side. Also for altcoins: `services/precision.py: SYMBOL_DECIMALS` and `services/market_time.py: CRYPTO_247`. Everything else follows the candles via `tracked_symbols`; `/radar` alone waits on a brain bias push. Any new instrument must be probed end to end on the Windows box (name resolves, spec returns, one order attempted) before it is enabled.
