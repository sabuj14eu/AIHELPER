---
title: Brother Sniper v7 — workflows, ceremonies and tools
domain: v7
repo: sabuj14eu/brother_sniper_v7
sources: CLAUDE.md, docs/START_HERE.md, docs/OPEN_ITEMS.md, docs/SESSION_COORDINATION.md, docs/A2_NGINX_MIRROR_SECRET.md, docs/STRATEGY_INTELLIGENCE.md, docs/V7_AUDIT_2026-08-01.md, docs/V7_AUTONOMY_PLAN.md, docs/ADAPTIVE_GATES_SPEC.md, docs/PINE_UPDATE_NOTE.md, docs/UI_WORK_ORDER_2026-09-02.md, patch_entry_dist_atr.py, patch_iso01_identity.py, patch_iso02_balance_unknown.py, patch_v7_bridge_iso03_05_16.py, patch_v7_bridge_iso06_box.py, patch_v7_bot_iso07_08.py, patch_mirror_close.py, deploy_windows.py, sniper-bot.service, gunicorn.conf.py, requirements.txt, .env.example, find_news.sh, show_newsgate.sh, scorecard.py, nightly_edge.py, weekly_report.py, mae_study.py, shadow_eye_score.py, audit_report.py, mgmt_replay.py, audit_mgmt_state.py, autonomy_scorecard.py, auto_live.py, probe_symbols.py, post_outlook.py, post_readiness.py, post_incident.py, post_weekly_outlooks.py, tests/audit/2026-09-04_job3/README.md
verified_on: 2026-09-16
classification: INTERNAL
---

# How work is done on the v7 repo: findings first, then code

CLAUDE.md "HOW TO WORK HERE": findings first, then code; small verified
diffs over rewrites; when a claim matters, grep the journal — "this system's
history is measured, not remembered"; if something looks broken, check what
the TICKETS say before believing any green light. `pytest -q` before every
commit (249 tests as of f7cacfd). The audit format used for every serious
finding (from brother-developer, applied here in `tests/audit/*/PROPOSAL*.md`):
BEFORE / WHY WRONG / AFTER / WHY CORRECT / WHAT COULD BREAK / HOW TESTED,
with a proposed diff and golden fixtures BEFORE anything is applied.

# The anchor-safe patch script pattern (patch_*.py)

Why a patch script and not a file copy: the box's `bot.py` may belong to
another session's branch, so "copying a whole bot.py over it would silently
drop that session's work" (patch_entry_dist_atr.py). Every `patch_*.py`
follows the same ceremony (Iron Rule 4): (1) module docstring states the
finding, the exact change, the run command and the verify step; (2) back up
`<file>.bak.<stamp>` (`*.bak*` is gitignored); (3) each hunk anchors on a
unique string — it must match EXACTLY ONCE or NOTHING is written ("abort on
ambiguous anchors"); (4) `py_compile` the result and restore the backup on
failure; (5) idempotent — a second run prints ALREADY PATCHED; (6) print the
next step (restart) and the acceptance witness. Multi-file scripts (ISO-02:
15 hunks over 3 files; ISO-03/24: 7 hunks over 4 files) check every anchor
of every file before writing any.

Release-gate artefacts pair a patch script with GOLDEN TESTS under
`tests/audit/<date>_deploy_*`: the script's output on a pre-state fixture
must be byte-identical to the repo fix at a named commit (e.g. 4937532,
0d1a2a5, 28b4c9d), plus a test that the script is idempotent and writes
nothing anywhere on an unknown anchor. When the box file differs from the
repo shape (the A1-patched bridge), a BOX VARIANT script anchors on the box's
lines (`patch_v7_bridge_iso06_box.py`); the generic script correctly aborted
there and wrote nothing.

# Deploy ceremony — Contabo v7 bot (current, since 2026-09-15)

The Contabo checkout is converged on `main`, so a v7 bot deploy is:
`cd /home/shyam/brother_sniper_v7 && git pull --ff-only origin main`,
`sudo systemctl restart sniper-bot`, then the witness: `curl
127.0.0.1:5000/health` (expect `status ok`, `balance_state MEASURED`,
`git_commit` = the pulled short SHA) and the log (`tail logs/bot.log`,
`journalctl -u sniper-bot`), e.g. "HARD STOP 0; `no_account_id` 0". The
earlier rule "Box deploy stays via the idempotent patch scripts" is RETIRED
for Contabo (docs/OPEN_ITEMS.md 2026-09-15). Before that, the ceremony was
single-file checkouts (`git checkout origin/<branch> -- bot.py
patch_x.py`), run the patch script, restart, verify. Syntax check used on the
box: `python3 -c "import ast,sys; ast.parse(open('bot.py').read())"`.

# Deploy ceremony — Windows bridge (still a patched loose copy)

Run PowerShell as Administrator on the VPS. Pattern from the ISO scripts:
`python patch_x.py C:\Users\Administrator` (directory) or the explicit file
path; the script backs up `.bak.<stamp>`, patches, `py_compile`s; then set the
service env — NSSM `AppEnvironmentExtra` REPLACES the whole set, so list every
variable: `V7_MT5_LOGIN=52834417 V7_MAGIC_NUMBER=70007 ADMIN_HALT_TOKEN=<secret>`
(plus `WEBHOOK_SECRET`); create `C:\brotherbot` before restart; `nssm restart
SniperExecutorV7`; verify `curl http://127.0.0.1:5001/health` shows the
asserted account, `magic`, `trade_mode`, `global_stop CLEAR`. Order matters:
deploy the BOT's ISO-03 patch and `V7_MT5_LOGIN` in the bot .env FIRST,
because after the bridge patch it refuses orders without `account_id`.
`deploy_windows.py` carries fixes for a VPS with no git (A1 v7 `/positions`
503; B5 v18 two-witness `/candles`), idempotent, `--dry-run` supported.
Manual compile check: `& "C:\Program Files\Python311\python.exe" -m py_compile
C:\Users\Administrator\sniper_executor.py`.

# Alert ceremony (every Pine save; docs/PINE_UPDATE_NOTE.md, CLAUDE.md Rule 3)

1. Fix the Pine error first; keep the filename. 2. Save. 3. Delete and
recreate ALL TradingView alerts using "Any alert() function call" — an alert
created earlier keeps running the OLD frozen script. 4. Afterwards verify
what runs from its own mouth: `pine_ver` in the journal / mirror payloads
(only pre-v18.8 signals are genuinely unstamped). 5. If `WEBHOOK_SECRET`
rotates, update all three places: v7 `.env`, the TradingView alert JSON, and
the bridge service env.

# Session coordination protocol (multiple Claude sessions, one checkout per box)

Read `docs/SESSION_COORDINATION.md` before touching a checkout. Rules: never
`git checkout <branch>` on a box; take single files with `git fetch origin
<branch> && git checkout origin/<branch> -- path`; push deploy-ready work to
`main` as well; "Already up to date" while the remote moved means you are on
the wrong branch (`git branch --show-current`); deployed != committed. Work
orders between the bot session and the platform session are written into
`docs/OPEN_ITEMS.md` as numbered ROUND entries with item codes (A1, A2, B5,
C1...), each with a proof that closes it; "An item deferred in conversation is
an item forgotten — if it is not in that file, it does not exist."

# One organ per week, decision cards, and the shadow-then-enforce path

Only one live organ changes per week (Evidence Law). A new gate ships in
SHADOW (logs `[X SHADOW]`, telemetry-tagged, blocks nothing); after n >= 20
the numbers are read; enforcement is an explicit human flip via `.env`
(`V7_FRESHNESS_GATE=enforce`, `ASSET_GATE_ENABLED=true`, `F8_CT_50=true`,
`AUTO_LIVE_ARM=1`, `V7_NEWS_GATE=...`) plus restart, logged with its reason.
Anything that widens risk or enables a signal class is a DECISION CARD for
Shyam, never a silent change (PULLBACK on v7; DD guard numbers).

# Journal-grep habits (commands quoted in the repo)

- `grep -c "\[BE\]" logs/bot.log*` — did breakeven ever fire.
- `grep -c '"mae"' learning/trades.jsonl` — MAE null-check.
- `tail -1 learning/telemetry.jsonl | python3 -c "import json,sys;
  print(json.load(sys.stdin).get('entry_dist_atr'))"` — verify a capture.
- `grep -c "\[A2\] secret from header" logs/bot.log` — mirror carries the
  header (>= 1 after the next real Pine alert).
- `journalctl -u sniper-bot | grep MIRROR` — only appears if a close post fails.
- `grep "\[V7-STATUS\] ... skipped"` absent in bot.log = heartbeat healthy.
- `crontab -l | grep post_readiness` — verify the Sunday cron line exists.
- `Select-String C:\Users\Administrator\sniper_executor.py -Pattern
  "_macro_front"` — a hit = the mirror-branch bridge with the resolver.
- `Get-FileHash` both copies before trusting either reporter file.
- `SELECT signal_id, system, status FROM signals WHERE signal_id LIKE
  '%<id>%';` — search BOTH v7 id namespaces on the platform.
- `find_news.sh` / `show_newsgate.sh` — where news minutes are computed and
  what news_minutes the near-news losers had.

# Read-only analysis tools (nothing written to live state, nothing traded)

- `python3 scorecard.py` — six sections: entry quality, trade management
  (BE/partial/MAE), filter/AI score, shadow eyes, analyst eye, protection;
  n < 20 flagged PROVISIONAL.
- `python3 nightly_edge.py [--json out.json] [--unified]` — shrunk, lower-
  bound expectancy per dimension and combination; advisory weights only.
- `python3 audit_report.py` then `python3 weekly_report.py [--days 7]` —
  joined per-signal records, Wilson intervals; "collecting" instead of inventing.
- `python3 mae_study.py` — stop-distance replay at 1.0/1.2/1.5/2.0 x ATR.
- `python3 shadow_eye_score.py`, `python3 eye_scoreboard.py` — eye votes vs
  outcomes per model.
- `python3 -m learning.conditional_profile GOLD` — hierarchical-backoff cells.
- `python3 mgmt_replay.py` — ENTRY-ONLY vs BREAKEVEN+1R with BEST/WORST bounds.
- `python3 audit_mgmt_state.py` — required zeros; writes
  `logs/mgmt_audit_last.json`; exit 1 on violation.
- `python3 autonomy_scorecard.py [date] [--post]` — the day's autonomous record.
- `python3 probe_symbols.py [SYMBOLS]` — can the bridge serve candles for a
  name (never prints URL/token/account).
- `python3 auto_live.py` — dry-run hunt; `python3 analyst_eye.py --once --dry`.
- `python3 -m pytest tests/audit/2026-09-04_job3 -q` — isolation repros.
- Mirror-branch only (not on main): `v7_counterfactual.py` (per-gate
  killed-losers vs killed-winners), `setup_edge.py`, `v7_evidence_report.py`,
  `probe_symbol_specs.py` (needs `BRIDGE_KEY`), `push_doc.py`.

# Posting workflows to the platform

Outlook: `python3 post_outlook.py --symbol GOLD --horizon weekly --source
"Shyam" --thesis "..." --scenario "above:4600:reading" --scenario
"below:4460:reading"` (levels and readings, no confidence words; a changed
mind is a new post). Weekly auto-outlooks: `post_weekly_outlooks.py` on the
Sunday cron. Readiness: write `docs/AUTONOMY_READINESS_<date>.md`, commit,
then `post_readiness.py` (cron 45 21 * * 0). Incident: `python3
post_incident.py INC-0001 --root-cause "..." --fix-ref "brother_sniper_v7@
<commit> patch_truth_guards.py" --tests "tests/test_round2_guards.py 2 passed"
--status patch_proposed`; RESOLVE is Shyam's button. Daily scorecard:
`autonomy_scorecard.py --post`.

# Test conventions

`pytest -q` from the repo root (needs flask, requests, pytest). Unit tests
under `tests/test_*.py`; audit evidence under `tests/audit/<date>_<job>/`
with fixtures (pre-patch copies of live files) and naming `test_repro_*`
(green = gap still present), `test_golden_*` (fix holds), `test_holds_*`
(invariant), `test_evidence_*` / `test_contract_*` (ISO-02 proposal pins).
Several tests exec the repo `bot.py` or a patch script against a temp copy
to prove idempotency and anchor safety (e.g. `test_entry_dist_atr.py::
test_box_patch_script_is_idempotent_and_anchor_safe`, `test_v7_status_hooks.py::
test_patch_is_idempotent_on_the_repo_copy`). Proposal hunk modules carry
unique names (`proposal_hunks_isoNN`) so two proposal dirs collect in one run.

# Tools and runtime dependencies

`requirements.txt`: flask==3.0.3, requests==2.32.3, python-dotenv==1.0.1,
gunicorn[gthread]==22.0.0, pandas==2.2.3. Windows bridge: Python 3.11 +
`MetaTrader5` package + Flask, run under NSSM. Infra: systemd
(`sniper-bot.service`), nginx mirror on the brain box, NSSM services on the
VPS, cron on Contabo. External feeds: ForexFactory calendar
`https://nfs.faireconomy.media/ff_calendar_thisweek.json` (HIGH impact only,
600 s refetch TTL); Telegram Bot API for every notice (messages tagged
`[V7-DEMO]`); LLM "eyes" via `EYE_MODEL=gemini|deepseek|shadow`
(filters/deepseek_vote.py) and `risk/analyst_eye.py`; TradingView Pine v6
BrotherSniperULTIMATE; the platform's webhooks (X-Brain-Secret).

# Environment variables (names only; values live in .env, never in git)

Required by bot.py: XTB_USER, XTB_PASS (legacy contract, kept required),
WEBHOOK_SECRET, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID. Optional: USE_DEMO,
TRUSTED_IPS, TV_HMAC_SECRET, EXECUTOR_URL (bridge `/execute`; other routes
derived), V7_MT5_LOGIN, V7_MAGIC_NUMBER, F8_CT_50, ASSET_GATE_ENABLED /
ASSET_GATE_DISABLE / ASSET_GATE_SIZE, V7_FRESHNESS_GATE (off|shadow|enforce),
V7_FRESH_MAX_SIGNAL_AGE_S, V7_FRESH_MAX_MOVE_ATR, V7_NEWS_GATE
(enforce|shadow|observe), V7_NEWS_OWN_MAX_AGE_S, PLATFORM_URL /
PLATFORM_SECRET or PLATFORM_WEBHOOK_URL / PLATFORM_WEBHOOK_SECRET,
PLATFORM_MIRROR_ENABLED, INCIDENT_INGEST_PATH, AUTO_LIVE_SYMBOLS,
AUTO_LIVE_MAX_DIST, AUTO_LIVE_ARM, EYE_MODEL, EYE_SHADOW_PRIMARY, BRIDGE_KEY
(mirror-branch bridge). Bridge env: WEBHOOK_SECRET, V7_MT5_LOGIN,
V7_MAGIC_NUMBER, V7_SEEN_FILE, GLOBAL_STOP_FILE, ADMIN_HALT_TOKEN.
`ACCOUNT_BALANCE` is dead config since ISO-02.

# Workflow for a signal-class or symbol addition ("three doors")

Pine detects -> v7 accepts (`SYMBOL_MAP`/`ALLOWED_SYMBOLS`, price ranges,
specs) -> broker probed (`symbol_info` on the v7 terminal: digits,
volume_min/step, contract size, trade_mode, spread in-session AND overnight).
"A name that resolves is not a name that fills." Then COLLECT (config only,
shadow), ANALYZE (>= 100 shadow signals or 4 weeks), and only then a NEW
versioned engine behind a dark flag (NVDA queue, docs/OPEN_ITEMS.md).
