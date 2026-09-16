---
title: Brother v18 Brain — Workflows and Tools
domain: brain
repo: sabuj14eu/brother-brain-v2
sources: CLAUDE.md, docs/DEPLOY_RUNBOOK.md, docs/HANDS_OFF_DEPLOY.md, docs/EXECUTOR_DEPLOY_2026-07-31.md, docs/SESSION_COORDINATION.md, docs/decisions.md, docs/OPEN_ITEMS.md, docs/PINE_VS_BOT_MAP.md, brain/src/agents/PINE_SOURCE.md, brain/tools/check_pine_ver.py, brain/requirements.txt, executor_ic_markets/requirements.txt, watchdog/requirements.txt, dashboard/backend/requirements.txt, brain/.env.example, executor_ic_markets/.env.example, watchdog/.env.example, brain/src/agents/base.py, brain/ai_spend_report.py, brain/patch_*.py, executor_ic_markets/patch_*.py, tests/test_protocol_roundtrip.py, tests/audit/2026-09-04_job3/README.md, tests/audit/2026-09-05_iso09/PATCH_PROPOSAL_ISO09.md, tests/audit/2026-09-05_deploy_v18_executor/test_deploy_v18_executor_golden.py, brain/mirror_outcomes.py, brain/remirror_decisions.py, brain/reconstruct_decisions.py, brain/push_bias.py, brain/push_news.py, brain/backfill_journal_outcomes.py, brain/test_modify.py, deploy/install_windows_service.txt, deploy/brother-brain.service, shared/src/crypto/keygen.py
verified_on: 2026-09-16
classification: INTERNAL
---

# How work is done in the v18 brain repo

CLAUDE.md: "Findings first, then code. Small verified diffs over rewrites. When a claim matters, grep the journal (logs/decisions.jsonl) — this system's history is measured, not remembered." Every change to a running service follows Iron Rule 4's deploy ceremony — backup → compile → restart → verify in logs/journal — and every edit to a file on a box is anchor-safe: the patch aborts untouched if an anchor matches anything other than exactly once. `pytest -q` runs before every commit (the platform and developer-agent constitutions say so explicitly; this repo's test layout assumes it).

# The deploy ceremony on the Contabo brain box

From docs/EXECUTOR_DEPLOY_2026-07-31.md ("Brain deploy") and decisions.md operator commands:

```
cd /home/shyam/brain-v2
git checkout main && git pull        # only safe when live == main was verified (it was, 07-31)
# edit brain/.env (names only, e.g. PLATFORM_MIRROR_ENABLED, FAILSOFT_MAX_PER_DAY)
sudo systemctl restart brother-brain
sudo journalctl -u brother-brain -f          # or -n 50
tail -f brain/logs/brain_*.log | grep -E "platform mirror|PrepValidation|fail-soft"
```

Verify from the journal, not from a 200: `tail -5 /home/shyam/brain-v2/brain/logs/decisions.jsonl | jq -c .`; approval rate `jq -s 'group_by(.approved) | map({k:.[0].approved,n:length})' logs/decisions.jsonl`; costs to date `jq -s 'map(.anthropic_cost_est_usd) | add' logs/decisions.jsonl`. Dashboard changes: `sudo systemctl restart brother-dashboard` after backend or panels.json edits; frontend edits need only a browser refresh (nginx serves static files). Deploy order when brain and executor change together (07-31): executor first, then brain — "the brain's signal_id field is harmless to the old executor; the new executor is harmless without it." The ISO-10 coupling is the exception: an old brain with the new executor means every signal is refused `no_account_id` until the brain follows (patch_v18_executor_iso10_12_14_16.py docstring).

# The deploy ceremony on the Windows executor box

The Windows box is not a git clone, so a deploy is a file copy or an anchor-safe patch script (docs/EXECUTOR_DEPLOY_2026-07-31.md). PowerShell as Administrator:

```
$d = Get-Date -Format "yyyyMMdd_HHmmss"
Copy-Item C:\brother_v18\executor_ic_markets\src\main.py C:\brother_v18\executor_ic_markets\src\main.py.bak.$d
# copy the new files over (scp from the Contabo clone, or paste)
& "C:\Program Files\Python311\python.exe" -m py_compile C:\brother_v18\executor_ic_markets\src\main.py ...
nssm restart SniperExecutorV18
curl http://127.0.0.1:8080/health
```

Verify after the first reconciler cycle (≤5 min): no errors, then after the next real close a `[OUTCOME] ... WIN/LOSS ...` line and `state.json` with `pnl_pct_today` and `cap_day`. Rollback = restore the `.bak.$d` files and `nssm restart SniperExecutorV18`. The release-gate artefacts for the September ISO fixes run the same way: `python patch_iso09_login_assertion.py C:\brother_v18\executor_ic_markets`, then `python patch_v18_executor_iso10_12_14_16.py C:\brother_v18`, then `python patch_v18_executor_iso11_13_15_20.py C:\brother_v18`; each backs up `<file>.bak.<stamp>`, `py_compile`s, is idempotent ("Already patched"), and writes nothing anywhere on an ambiguous anchor. Golden tests in `tests/audit/2026-09-05_deploy_v18_executor` and `tests/audit/2026-09-15_p1_executor` prove each script's output is byte-identical to the repo commit it ships.

# The anchor-safe patch-script pattern

Every `brain/patch_*.py`, `dashboard/backend/patch_*.py` and `executor_ic_markets/patch_*.py` follows one shape: a docstring stating the target file, the finding and the fix; exact `OLD`/`NEW` anchor strings; "backs up, aborts untouched on anchor mismatch, py_compile, auto-restores on failure, re-runnable/idempotent"; then the operator command (`python3 patch_x.py` from the target directory, then restart the service). Examples: `patch_brain_passthrough.py` (07-20 append-tolerant listener), `patch_journal_dispatch_truth.py` (07-19), `patch_routing.py` (AI-ON wiring), `patch_dashboard_botguards.py` (07-19), `patch_iso09_login_assertion.py` (9 hunks, ISO-09). The historical brain patches are one-shot and now stale (audit P2-8 suggested moving them to `archive/`; one of them, `patch_dispatch_modes.py`, caused a journal-loss NameError that the mirror PR fixed).

# Hands-off first-time deploy (docs/HANDS_OFF_DEPLOY.md, docs/DEPLOY_RUNBOOK.md)

Phase 0 offline on a laptop: `python -m shared.src.crypto.keygen --out ./keys` produces `brain_signing_private.key` (brain only, chmod 600, one offline USB backup) and `brain_signing_public.key` (executors + watchdog); `python -m tests.test_protocol_roundtrip` must print all 6 tests passed; generate admin halt tokens with `secrets.token_urlsafe(32)`. Phases 1–4 install the Polymarket executor, the brain (`/home/bots/brain-v2` alongside the untouched `v18-prod`, `WEBHOOK_PORT=8443`, `BRAIN_DISPATCH_MODE=print` for 48h), the Windows executor via NSSM (`deploy/install_windows_service.txt`: service `BrotherV18Executor` in the template; the live name is `SniperExecutorV18`), and the watchdog. Phase 5 cutover: days 1–2 print mode + DRY_RUN; days 3–13 live dispatch + DRY_RUN (watch for `bad_signature`/`replay_attack` events, signal age < 5s); day 14+ Polymarket live at $25; after another 14 clean days IC Markets at half risk (0.25%), then 0.5%. "When NOT to deploy": roundtrip not 6/6 green, no offline key backup, `halt_all` untested, "You're rushing because you saw something in markets", "It's Friday afternoon."

Kill-switch operations: stop the service, set `"kill_switch": true` in `logs/state.json`, start; reset only after diagnosis by editing the file back and restarting (`nssm restart` on Windows). Emergency halt from the watchdog host: `python -m src.halt_all [polymarket|ic_markets] --reason "..."`.

# Test commands

- Whole repo: `pytest -q` from the repo root (tests in `tests/` and `brain/tests/`). Note `tests/test_executor_state.py` runs the executor assertions in a subprocess because brain and executor both use the top-level package name `src`.
- Crypto/protocol: `python -m tests.test_protocol_roundtrip` (6 checks: keygen, signer/verifier interop, canonical JSON stability, tamper, stale, replay).
- Audit evidence directories: `python3 -m pytest tests/audit/2026-09-04_job3 -q` (needs pytest + cryptography; route tests need fastapi + httpx, otherwise NOT RUNNABLE), `python3 -m pytest tests/audit/2026-09-05_iso09 -q`, `.../2026-09-05_iso11`, `.../2026-09-05_iso15`, `.../2026-09-05_deploy_v18_executor`, `.../2026-09-15_p1_executor`; from `brain/`: `python3 -m pytest tests/audit/2026-09-05_iso10 -q`, `.../2026-09-05_iso19`, `.../2026-09-05_job9`, `.../2026-09-06_inc0004`.
- Naming convention in audit tests: `test_repro_*` PASSES while a finding is still reproducible (green = the gap is still there), `test_golden_*` runs against the fixed code, `test_holds_*` is an invariant that holds today; verdicts are PASS / FAIL / NOT RUNNABLE / UNKNOWN, never invented.
- Deterministic calculator self-test: `python3 src/compute_sltp.py` from `brain/` replays 12 real journal rows.
- Live MODIFY drill (DEMO only, from the brain venv): `.venv/bin/python test_modify.py probe|reject|tighten <NEW_SL>` — `reject` must be refused by the favorable-only invariant.

# The journal-grep habit

- Which Pine version is actually firing: `grep -o '"pine_ver":"[^"]*"' logs/decisions.jsonl | sort | uniq -c`; anything other than the current version (or `session_caller`) means alerts are frozen on old code and the alert ceremony is due (PINE_SOURCE.md, PINE_VS_BOT_MAP addendum).
- Fuller census: `python3 brain/tools/check_pine_ver.py [n_rows] [--all-sources]` — lists versions arriving, real Pine alerts per ticker (session_caller paper excluded) and silent tickers (>24h).
- Fail-soft evidence: grep decisions.jsonl for `trace.agent_error_fallback`; provider errors: `grep -c AgentError brain/logs/*.log` and the 429/500/529 codes ("a wallet/limit problem looks like an outage").
- Kill-switch history on an executor: `grep -h kill_switch logs/events/*.jsonl* | jq .`
- AI spend: `python3 ai_spend_report.py [--all]` reads `logs/ai_spend.jsonl` (calls/day by agent, caching verdict, parse-retry rate, spend vs `BRAIN_AI_WEEKLY_BUDGET_USD`).
- Weekly scoreboard: `python3 weekly_source_report.py [--days 7]`; truth layer: `python3 truth_layer.py`; calibration: `python3 council_calibration.py [--days 14]`; backtests: `python3 pullback_backtest.py`, `python3 fib_pullback_backtest.py` — all read-only, $0 API.

# Platform mirror operations (brain -> app.signalmesh.dev)

- Decisions mirror in-process (`PLATFORM_MIRROR_ENABLED=true`, `PLATFORM_WEBHOOK_URL`, `PLATFORM_WEBHOOK_SECRET` in brain/.env).
- Outcomes: cron every 10 minutes `cd /home/shyam/brain-v2/brain && <venv python> mirror_outcomes.py [--dry-run] [--n 500] [--exec-update]`; state `logs/outcomes_mirrored.json`; exit 1 on failure or COUNT MISMATCH.
- Re-mirror refusals with today's payload: `remirror_decisions.py --since 2026-09-10 --until 2026-09-12 --rejected-only [--dry-run]` (only useful inside the platform's 48h idempotency window).
- Reconstruct lost decisions (INC-0004 window 2026-09-01 17:30Z – 2026-09-06 01:40Z): `reconstruct_decisions.py --journalctl FILE --v7-journal FILE --events DIR --out FILE [--received FILE] [--box-utc-offset 2] [--match-minutes 10] [--post] [--already-posted PREV ...] [--post-unknown-symbol]`.
- Journal outcome backfill: `python3 backfill_journal_outcomes.py --dry-run` then without; timestamped backup, atomic replace, aborts if any decision field would move.
- Bias every 30 min `*/30 * * * * cd /home/shyam/brain-v2/brain && /usr/bin/python3 push_bias.py >> logs/bias_push.log 2>&1`; news hourly `17 * * * * ... push_news.py >> logs/news_push.log 2>&1`. Config names: `BIAS_CORE_SYMBOLS` (accepts `CANON=BROKER`), `BIAS_DXY_SYMBOLS`, `BIAS_US10Y_SYMBOLS`, `BIAS_MAX_AGE_H`, `V7_BRIDGE_URL`.

# Session coordination protocol (docs/SESSION_COORDINATION.md)

Several Claude sessions work these repos at once but each box has one checkout with one HEAD. Rules: never `git checkout` a branch on a box whose services run from the current checkout; take single files with `git fetch origin <branch>` + `git checkout origin/<branch> -- path`; push deploy-ready work to `main` too; "Already up to date" while the remote branch moves is the fingerprint of a wrong branch (`git branch --show-current` first); "Deployed ≠ committed" — verify what runs from journal `pine_ver` and service endpoints. The branch-ownership table named `claude/brain-platform-mirror-fcacwl` (bot-side session) and `claude/trade-desk-architecture-review-hp9xnb` (trade-desk session, live on the v7 box); the local repo currently shows `main` and `claude/exciting-hopper-uyy9gb`. The endgame: every session merges to `main`, every box checks out `main`.

Working with the platform session: asks arrive numbered and versioned ("platform v5.44 ask 5"), the answer is a commit whose message names the ask, and proof is a quoted log line or receipt, never a claim (OPEN_ITEMS: "a verdict is posted only with its query output embedded").

# Tools and libraries (names only, never values)

- Python 3.11+ (Windows: `C:\Program Files\Python311\python.exe`), FastAPI + uvicorn for the brain, both executors and the dashboard backend; httpx for outbound calls; pydantic; python-dotenv; loguru (daily rotating logs, 30-day retention, zip); numpy/scipy (Monte Carlo sandbox).
- `cryptography` for Ed25519 (`shared/src/crypto/signer.py`, `verifier.py`, `keygen.py`) — PyNaCl is not used.
- `MetaTrader5` Python package on the Windows executor; NSSM for the Windows services; `w32tm /resync` for clock sync; Caddy or nginx for TLS on Windows (deploy notes).
- nginx + certbot (Let's Encrypt, `certbot.timer`) on Contabo for `brain.signalmesh.dev` and the dashboard; Cloudflare Registrar/DNS for `signalmesh.dev` (gray cloud, no proxy); UFW + fail2ban + chrony on the droplets (`deploy/firewall_executor.sh`).
- systemd units: `brother-brain.service`, `brother-dashboard.service`, `brother-executor-pm.service`, `brother-pm-scanner.service`, `brother-scanner-mt5.service`, `session-caller.timer`.
- LLM provider: Anthropic Claude via the `anthropic` SDK, default model `claude-opus-4-7` (`ANTHROPIC_MODEL`, per-agent `ANTHROPIC_MODEL_<AGENT>`), Researcher uses the `web_search_20250305` tool (`BRAIN_WEB_SEARCH`), prompt caching via `cache_control: ephemeral` (`BRAIN_PROMPT_CACHE`, `BRAIN_PROMPT_CACHE_<AGENT>`), weekly hard cap `BRAIN_AI_WEEKLY_BUDGET_USD` with the ledger `logs/ai_spend.jsonl` and price knobs `BRAIN_PRICE_IN_PER_MTOK` / `BRAIN_PRICE_OUT_PER_MTOK` / `BRAIN_PRICE_CACHE_READ_PER_MTOK`.
- Telegram bot API for notifications (brain, executor, watchdog); py-clob-client-v2 and web3 for the retired Polymarket executor; ForexFactory weekly JSON for the calendar (`push_news.py`).
- Environment variable names in use (values never recorded): brain — `BRAIN_PRIVATE_KEY_PATH`, `BRAIN_DISPATCH_MODE`, `EXECUTOR_IC_MARKETS_URL`, `EXECUTOR_IC_MARKETS_TOKEN`, `EXECUTOR_IC_MARKETS_ACCOUNT`, `ANTHROPIC_API_KEY`, `TRADINGVIEW_WEBHOOK_SECRET`, `BRAIN_REQUIRE_SECRET`, `PM_WEBHOOK_SECRET`, `WEBHOOK_HOST/PORT`, `PLATFORM_MIRROR_ENABLED`, `PLATFORM_WEBHOOK_URL`, `PLATFORM_WEBHOOK_SECRET`, `FAILSOFT_MAX_PER_DAY`, `SHADOW_SYMBOLS`, `PINETRUST_MIN_RR`, `MAX_AI_CALLS_PER_TRADE`, `MODIFY_COOLDOWN_MINUTES`, `BRAIN_LOGS_DIR`, `DECISION_JOURNAL_ENABLED`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`; executor — `BRAIN_PUBLIC_KEY`, `EXECUTOR_BEARER_TOKEN`, `ADMIN_HALT_TOKEN`, `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`, `MT5_PATH`, `DRY_RUN`, `MAX_TRADES_PER_DAY`, `MAX_RISK_PCT_PER_TRADE`, `MAX_DAILY_LOSS_PCT`, `MAGIC_NUMBER`, `USABLE_MARGIN_PCT`, `MIN_MARGIN_LEVEL_PCT`, `RECON_INTERVAL_SECONDS`, `CLOCK_WITNESSES`, `GLOBAL_STOP_FILE`, `MT5_RECONNECT_COOLDOWN`; watchdog — `BRAIN_URL`, `EXECUTOR_*_URL`, `EXECUTOR_*_ADMIN_TOKEN`, `PING_INTERVAL_SECONDS`, `MISS_THRESHOLD`, `ALERT_PNL_THRESHOLD_USDC/PCT`, `ALERT_COOLDOWN_MINUTES`; dashboard — `DASHBOARD_TOKEN`.
