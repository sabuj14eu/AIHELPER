---
title: Brother Sniper v7 — overview of the mechanical arm
domain: v7
repo: sabuj14eu/brother_sniper_v7
sources: CLAUDE.md, INTENT_v5.md, ROADMAP.md, docs/START_HERE.md, docs/SESSION_COORDINATION.md, docs/A2_NGINX_MIRROR_SECRET.md, docs/OPEN_ITEMS.md, docs/V7_AUTONOMY_PLAN.md, docs/AUTONOMY_READINESS_2026-08-30.md, sniper-bot.service, gunicorn.conf.py, bot.py, sniper_executor.py, core/v7_status.py, core/ic_markets.py, learning/platform_mirror.py, requirements.txt, .env.example, .gitignore, auto_live.py, post_readiness.py, post_weekly_outlooks.py, autonomy_scorecard.py, nightly_edge.py
verified_on: 2026-09-16
classification: INTERNAL
---

# What the v7 bot is

The Brother Sniper v7 bot ("the arm", "the mechanical arm", "v7") is the
rule-based trading bot of Shyam's Brother Sniper system. It is one Flask
application, `bot.py` (header: "Brother Sniper Bot v7 — Self-Adjusting
Decision System"), that receives TradingView Pine alerts on `/webhook`, runs
them through its own filter chain (news, equity guard, EV/cluster gate,
six-factor AI filter, institutional SL engine, R:R validator, freshness gate),
sizes the trade, and sends a market order to a Windows bridge that talks to
MetaTrader 5. Every account is DEMO (CLAUDE.md: "Algorithmic trading system,
ALL DEMO accounts"; OPEN_ITEMS 2026-09-15: "Real money stays NO-GO").

The v7 bot is the SCALP arm by decision: it accepts only Pine type
`SMART_SCALP` from BSv17/BSv18 payloads; PULLBACK signals are dropped on
purpose (decision C4, 2026-09-01) because `auto_live.py` is v7's own
pullback engine, running in shadow (bot.py, OPEN_ITEMS.md).

The v7 bot never learns silently: the learning layer (clusters, weights,
governance) is clamped and evidence-gated, and the LLM "eye" votes are shadow
evidence only since ISO-24 (2026-09-05). The destination is the "V7
Self-Dependence" plan: v7 trading without Pine after five phases, none
skippable (docs/V7_AUTONOMY_PLAN.md).

# Where the v7 bot runs (boxes, services, ports)

The v7 bot process runs on the Contabo Linux box at
`/home/shyam/brother_sniper_v7` as the systemd unit `sniper-bot.service`
(User/Group `shyam`, `EnvironmentFile=.env`, `ExecStart=venv/bin/gunicorn -c
gunicorn.conf.py bot:app`, `Restart=always`, `ProtectSystem=strict`,
`ReadWritePaths=/home/shyam/brother_sniper_v7`). Gunicorn binds
`127.0.0.1:5000` with `workers = 1` ("MUST be 1 — shared XTB socket +
state"), `threads = 4`, `worker_class = "gthread"`, `timeout = 30`, and
calls `bot.startup()` in `post_worker_init` (gunicorn.conf.py). The same
Contabo box hosts the v18 brain (`/home/shyam/brain-v2`) and the platform
(`/srv/brotherbot`) (docs/START_HERE.md).

The v7 bridge (`sniper_executor.py`, "Brother Sniper Executor v3 - Windows
VPS") runs on the Windows VPS `164.68.126.105` as the NSSM service
`SniperExecutorV7` on port `:5001`, attached to the IC Markets MT5 terminal
at `C:\Program Files\MetaTrader 5 IC Markets EU\terminal64.exe`, demo account
`52834417` (CLAUDE.md; sniper_executor.py `V7_MT5_PATH`). The deployed file is
a loose copy at `C:\Users\Administrator\sniper_executor.py`; a git clone
`C:\brother_sniper_v7` exists on the VPS since 2026-09-02 (OPEN_ITEMS.md).
Bridge routes: `/health`, `/positions`, `/history`, `/execute`, `/close`,
`/candles`, `/modify`, `/admin/halt`, `/admin/status`.

Neighbours on the same Windows VPS: the v18 executor `SniperExecutorV18` on
`:8080` (MT5 `52901228`, code at `C:\brother_v18\executor_ic_markets`) and
the candle reporter `BrotherBotReporter` (`C:\brotherbot\mt5_reporter.py`,
source `Sniper-System/agents/mt5_reporter/mt5_reporter.py`, v1.6.0+). The
bot's env `V7_MT5_LOGIN=52834417` and the bridge's must agree (ISO-01/03).

# How a Pine signal reaches the v7 bot (the nginx mirror)

One TradingView Pine script (BrotherSniperULTIMATE, Pine v6, v18.12.x/v18.13)
fires alerts to `brain.signalmesh.dev/webhook/v18`. nginx on the brain box
mirrors every request (`mirror /_v7_mirror; mirror_request_body on;`) to
`http://127.0.0.1:5000/webhook`, which is the v7 bot (CLAUDE.md,
docs/A2_NGINX_MIRROR_SECRET.md). A mirrored body cannot be rewritten, so the
copy carries no `secret`; that is why `bot.py handle_signal` auto-injects
`WEBHOOK_SECRET` for `system in (BSv16, BSv17, BSv18, BSv11)`, `version`
starting `v9`, or `bot` starting `BS_`. Since round 3 (2026-09-02) the
`/webhook` route also accepts the secret from the `X-Webhook-Secret` header
(shipped dark; the auto-injection stays until the log proves the mirror
carries the header).

The v7 bot's `/webhook` is protected by `@app.before_request _guard`: an
IPv4 allowlist of TradingView CIDRs plus `TRUSTED_IPS`, with
`X-Forwarded-For` honoured only when the connection comes from loopback (our
own nginx), and a rate limit of 10 requests per IP per 60 s (bot.py).

# The v7 arm versus the v18 brain

The v18 brain (`/home/shyam/brain-v2/brain`) is a 6-agent AI council that
judges every signal and dispatches an Ed25519-signed order to the v18 Windows
executor on `:8080` (MT5 `52901228`). The v7 bot is the second, mechanical
arm on its own MT5 account (`52834417`) with its own filters. Both arms see
the SAME Pine alert (one via the brain webhook, one via the mirror), so the
same signal is judged twice; the agreed join key between the arms is Pine's
`signal_id` (`pine_signal_id`) (docs/SESSION_COORDINATION.md, "Shared
contracts"). The two arms share a Windows box, so the dual-MT5 isolation
audit (ISO-01..ISO-24, September 2026) hardened identity, magic numbers,
dedupe and a global stop on both sides (docs/OPEN_ITEMS.md).

# The v7 bot and the platform (Sniper-System)

The platform (`sabuj14eu/Sniper-System`, `/srv/brotherbot`) is a read-only
observer: it never trades. The v7 bot feeds it through `core/v7_status.py`
(a `v7_decision` for every verdict to `/webhooks/brain/decision`; a
`v7_heartbeat` every monitor cycle to `/webhooks/brain/artifact`, pushed at
most every 240 s), through `learning/platform_mirror.py` (`mirror_v7_close`
to `/webhooks/brain/signal` with `signal_id` prefixed `v7-`), and through the
poster CLIs `post_outlook.py`, `post_weekly_outlooks.py`, `post_readiness.py`,
`post_incident.py` and `autonomy_scorecard.py --post`. All posts carry the
`X-Brain-Secret` header and read either env pair `PLATFORM_URL/PLATFORM_SECRET`
or `PLATFORM_WEBHOOK_URL/PLATFORM_WEBHOOK_SECRET` (core/v7_status.py `_push`).

The platform is also a WITNESS for the v7 bot: the NEWS01 news gate asks
`GET /api/v1/news/state?symbols=<one>` on every signal and combines it with
v7's own ForexFactory reading (filters/news_gate.py). The platform's paper
lanes are a hypothesis generator, never a gate authority for v7 (Sniper-System
constitution, echoed in docs/START_HERE.md: "One population").

# The v7 bot and Pine

Pine is the frozen sensor. The v7 bot reads from the payload: `time` (signal
age), `trend`/`htf_trend`, `atr`, `entry_dist_atr`, `type`, `grade`, `v4_rr`,
`structure` (v18.13), `pine_ver` (since v18.8), plus the append-only base
contract (system, signal, direction, signal_id, symbol, tf, entry, sl, tp,
tp1, tp2, rr, grade) (docs/PINE_UPDATE_NOTE.md). Every Pine save requires the
alert ceremony (delete + recreate all alerts), because alerts freeze the
script version at creation (CLAUDE.md Iron Rule 3).

# The v7 bot and the developer agent

`brother-developer` is the engineering-intelligence agent: it reads every
repo, writes only in a sandbox worktree, and never trades. It produced the
dual-MT5 isolation audit (Job 3, 2026-09-04), the ISO-xx bug records
(`brother_developer/memory/bugs/BUG-2026-09-04-ISO*.json`), the ADRs
(ADR-004 uniqueness is `(account_id, signal_id)`, ADR-008 global stop), the
release-gate artefacts (anchor-safe patch scripts + golden tests), and the
P1 closure document `docs/audits/P1_CLOSURE_2026-09-15.md` (docs/OPEN_ITEMS.md).
Repro tests in this repo under `tests/audit/` follow its naming: `test_repro_*`
green = the gap is still there; `test_golden_*` = the fix holds;
`test_holds_*` = an invariant that holds today.

# Repository layout (main at f7cacfd, 2026-09-16)

- `bot.py` — the live trading file (webhook, filter chain, monitor loop,
  routes). Touching it is a "deliberate session only" act (docs/START_HERE.md).
- `sniper_executor.py` — the repo copy of the Windows bridge.
- `core/` — `ic_markets.py` (HTTP client to the bridge), `signal_memory.py`
  (all signals, RAM + `signal_memory.json`), `sl_engine.py`, `v7_status.py`.
- `filters/` — `ai_filter.py`, `news_gate.py` (NEWS01), `freshness_gate.py`,
  `news_semantic.py`, `deepseek_vote.py`.
- `risk/` — `equity_guard.py`, `analyst_eye.py`.
- `learning/` — trade memory, telemetry, cluster/weight engines, strategy DNA,
  conditional profile, platform mirror, signal bus, vote worker, brain scorer.
- `governance/discipline.py` — weight freeze, delta cap, decay, EV floor.
- `utils/asset_gate.py` — per-symbol bench/size-down dial (off by default).
- `patch_*.py` — anchor-safe box patch scripts, each documenting one fix.
- `post_*.py`, `scorecard.py`, `weekly_report.py`, `nightly_edge.py`,
  `mae_study.py`, `shadow_eye_score.py`, `audit_report.py`, `mgmt_replay.py`,
  `audit_mgmt_state.py`, `autonomy_scorecard.py`, `auto_live.py`,
  `probe_symbols.py`, `deploy_windows.py`.
- `docs/` — START_HERE, OPEN_ITEMS, STRATEGY_INTELLIGENCE, ADAPTIVE_GATES_SPEC,
  V7_AUTONOMY_PLAN, AUTONOMY_READINESS_2026-08-30, V7_AUDIT_2026-08-01,
  SESSION_COORDINATION, UI_WORK_ORDER_2026-09-02, PINE_UPDATE_NOTE,
  A2_NGINX_MIRROR_SECRET.
- `tests/` — 249 tests (`pytest -q`), including `tests/audit/<date>_<job>/`.
- `.gitignore` excludes `.env`, `logs/`, `*.jsonl`, `learning/` data,
  `state.json`, `signal_memory.json`, `governance/discipline_state.json`
  (live mutable state is owned by the running bot, never by git; commit
  f76ba28 2026-09-01). `learning/*.py` code IS committed (H-1 closed).

# Branches and convergence state

Historically three long-lived session branches diverged:
`claude/brain-platform-mirror-fcacwl` (bridge resolver, probes, evidence
reports), `claude/trade-desk-architecture-review-hp9xnb` (heartbeat +
decision contract, reconcile) and the deploy branch
`claude/evidence-integrity-audit-35rlfa` (rounds 1-4), plus
`claude/session-44nji4` (docs/SESSION_COORDINATION.md, docs/OPEN_ITEMS.md).
On 2026-09-15 the Contabo checkout was converged: `git reset --hard 66bc480`,
`git pull --ff-only origin main` -> 54f3acd, restart, `/health` ok. From then
a Contabo deploy is `git pull --ff-only origin main` + `sudo systemctl
restart sniper-bot` + the log/`/health` witness. The Windows bridge is still
a patched loose copy deployed by patch script (docs/OPEN_ITEMS.md).

Scripts named in the docs but ABSENT from `main` at f7cacfd (they live on the
mirror/trade-desk branches): `setup_edge.py`, `v7_evidence_report.py`,
`v7_counterfactual.py`, `mae_recompute.py`, `push_doc.py`,
`platform_gap_sql.py`, `probe_symbol_specs.py`, `core/reconcile`. Whether they
were merged since is UNKNOWN from this checkout.

# Symbol universe

`bot.py SYMBOL_MAP` canonicalises GOLD, SILVER, BITCOIN, ETHEREUM, LITECOIN,
RIPPLE, USDJPY, EURUSD, GBPUSD, AUDUSD, NZDUSD, USDCAD, USDCHF, US30, USTEC
(US100/NAS100/NDX -> USTEC); anything else is `unsupported` (NVDA is pinned
outside the map by `tests/test_shadow_symbols.py`). The decided trading
universe (2026-08-22): GOLD, SILVER, BTC, ETH, USDJPY, US30, US100; EURUSD
toggle exists default OFF; the five majors + SOL are candles-only until a
deliberate Pine v18.13 change; "No batch enablement, ever — one instrument,
probed end to end" (docs/V7_AUTONOMY_PLAN.md). `auto_live.py` trades only the
measured net earners: `AUTO_LIVE_SYMBOLS` default `SILVER,GBPUSD,US30`, with
`NVDA=NVDA.NAS-24` added for shadow collection (docs/OPEN_ITEMS.md).

# Scheduled jobs documented in the repo (cron lines quoted in docstrings)

- `0 2 * * *` nightly_edge.py --json learning/edge_report.json
  (docs/STRATEGY_INTELLIGENCE.md).
- `*/5 * * * *` auto_live.py (dry run unless `AUTO_LIVE_ARM=1`).
- `55 23 * * *` autonomy_scorecard.py --post.
- `30 21 * * 0` post_weekly_outlooks.py; `45 21 * * 0` post_readiness.py.
- Nightly 03:25 analytics (setup_edge, v7_evidence_report, v7_counterfactual,
  mae_recompute) per docs/START_HERE.md — scripts on the mirror branch.
Whether each line is installed on the box is not verifiable from the repo
(OPEN_ITEMS round 3, item 4: "Verify on the box with crontab -l").

# Test suite and history depth

`pytest -q` runs 249 tests (count from `def test_` across `tests/`). The
local clone is SHALLOW: 55 commits, oldest 2026-08-29 (ce25c15). Commits the
docs cite from before that date (88fe2d8 base, fc5bd6f resolver, cb534f6
auto_live, 6063676 platform signal_id adoption, 1baa72a Windows snapshot)
are not inspectable here.

# Contradictions and tensions found in the repo (recorded, not resolved)

- CLAUDE.md Iron Rule 1 says "NOTHING bypasses the council", yet the v7 bot
  is by design a second decision path that never consults the council (nginx
  mirror -> v7 filters -> bridge). The file is shared with brother-brain-v2;
  the rule targets executor bypasses (the retired MT5 scanner), and v7's own
  gate chain is the authority for its arm.
- CLAUDE.md says "grep the journal (logs/decisions.jsonl)": that path is the
  BRAIN's journal; the v7 bot's durable verdict journal is
  `learning/decisions.jsonl` (core/v7_status.py `JOURNAL_FILE`).
- INTENT_v5.md (2026-05-05) states "0.5% risk per trade" and "Max DD 12%";
  the code sizes 0.3%–1.0% effective risk and the DD guard sits at 99%
  (a deliberate, logged demo decision, A6 2026-09-01). The decision card for
  real limits is open (docs/V7_AUTONOMY_PLAN.md).
- The repo copy of `sniper_executor.py` on `main` has no closed-bar default,
  no `?live=1`, no `BRIDGE_KEY` gate and no front-contract resolver; the
  DEPLOYED bridge (measured 2026-09-02, `_macro_front` present) is the
  mirror-branch bridge + A1 + ISO patches. OPEN_ITEMS: "the deploy branch's
  copy is a landmine until converged".
