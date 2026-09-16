---
title: Brother v18 Brain — Open Items
domain: brain
repo: sabuj14eu/brother-brain-v2
sources: docs/OPEN_ITEMS.md, docs/AUDIT_2026-07-31.md, docs/decisions.md, docs/SESSION_PENDING_SPEC.md, docs/SESSION_COORDINATION.md, CLAUDE.md, brain/backfill_journal_outcomes.py, brain/src/utils/decision_journal.py, tests/test_signal_id_canonical.py, tests/audit/2026-09-04_job3/README.md, executor_ic_markets/patch_v18_executor_iso11_13_15_20.py, git log
verified_on: 2026-09-16
classification: INTERNAL
---

# How open items are kept for the v18 brain

`docs/OPEN_ITEMS.md` in this repo is a chronological evidence file (2026-08-31 to 2026-09-05) rather than a checklist; the platform repo's constitution states the rule that governs both sides: "An item deferred in conversation is an item forgotten — if it is not in that file, it does not exist. Delete an entry only when it is done and verified, and say where the proof is." The items below are carried as the file carries them, with status as of the repo state on 2026-09-16 (HEAD 0f8f49d). Anything not provable from the repo is marked UNKNOWN.

# The two bot-box P0s named by the platform

**P0 — journal outcomes never filled (BOT-P0-1).** Symptom: `write_decision` wrote `outcome/pnl_net/exit_reason/closed_at` as None and nothing filled them, so no council decision was judgeable. Status: the fix tool `brain/backfill_journal_outcomes.py` exists (atomic rewrite, abort if any decision field moves, shared fcntl lock since 2026-09-02) and the executor's close-tracker plus `/outcomes` supply the truth; `mirror_outcomes.py` now posts each close to the platform. Whether the backfill runs on a schedule on the brain box is UNKNOWN from the repo (no cron line is documented for it, unlike push_bias/push_news/mirror_outcomes). Proof of closure would be journal rows with non-null `outcome` and the platform's `/funnel` showing outcomes.

**P0 — the brain minted its own signal_id instead of adopting Pine's (BOT-P0-2).** Symptom: `FALLBACK_ID` still appeared on the platform's `/funnel` because the executor's dedupe could never match a genuine Pine duplicate. Status: fixed in code on 2026-08-21 (`canonical_signal_id`, source journaled as `pine` or `minted_fallback`; tests/test_signal_id_canonical.py; git 0f8f49d 2026-09-15 pins that `pine_signal_id` is the opportunity's own id). The acceptance test named in the code is platform-side: "the FALLBACK_ID share on /funnel falling toward zero." Whether that share has fallen is UNKNOWN from this repo.

# Open from docs/OPEN_ITEMS.md (bot-side)

- **BOT-BIAS-1 / US10Y stale:** the bridge cannot serve a 10-year yield under any alias (measured 2026-08-31); US10Y is Pine-only and stays honestly UNKNOWN when Pine is silent. Decision: no feed built; a Pine-independent yield source is a NEW ORGAN needing a spec and offline harness first, one organ per week. Reassess after the v18.13 alert ceremony. Status: open by design.
- **US30/USTEC execution probe:** the feed half passes (both serve live candles); order acceptance is "a SEPARATE, human-approved probe and is still open; a served candle proves data, never fill." Status: open.
- **Alert census 2026-08-31:** the ceremony was PARTIAL — BITSTAMP:BTCUSD, FOREXCOM:US30 and OANDA:XAUUSD alerts still ran v18.12; PURPLETRADING:US100 had no genuine Pine alert for 32 days (last real 18.8), FX:EURUSD 19 days; ACTIVTRADES:USA500 is retired and should be deleted. Whether the remaining alerts were recreated is UNKNOWN here (owned by TradingView/Sniper-System).
- **Incident ingest blocked (2026-09-02):** the platform's incident route 404'd authenticated POSTs for INC-0001/INC-0002 after the v5.01 rebuild; the corrected findings were preserved in OPEN_ITEMS pending the platform's answer. INC-0001 was later "RESOLVED on the board 2026-09-02 ('posted INC-0001 -> 200')". INC-0002 (OIL vs USOIL, XRP vs XRPUSD alias mismatch) status: the OIL/USOIL twin is now deduped canonically on the bot side; the proposal "ONE canonical set = the platform UI's 14 display names, owned by the platform canonicalizer" awaits the platform's written agreement.
- **DXY_U6 watch (mid-September):** `BB_CANDLE_SYMBOLS` on the reporter carries the September dollar-index contract; it rolls mid-September and DXY_Z6 was not yet listed, so nothing could be pre-configured. Trigger: the first "PUSH DXY_U6 ... symbol not known" line in the reporter log, then list `*DXY*` again and swap the name. Status: open, date-sensitive, and now overdue for a check (today is 2026-09-16).
- **UST10Y_U6 removal from BB_CANDLE_SYMBOLS:** logs five WARNINGs per cycle for a name that can never serve; "Shyam's call, noise only". Status: UNKNOWN.
- **Two terminal64 processes from C:\MT5_v18 (ISO-17 observation):** "Worth one look ... before anyone reads a v18 ticket count." Status: UNKNOWN.
- **NVDA phase 1 proofs owed (2026-09-02):** (1) reporter log "PUSH NVDA.NAS-24 15m ... bars pushed" > 0 — the 18:48 log showed NVDA.NAS-24 voting as a clock witness, and the reporter logs candles only on failure, so "the platform's row count is the proof"; (2) first `decisions.jsonl` row with `dispatch_mode blocked_shadow`; (3) platform NVDA candles under the canonical name. Status: (1) inferred, (2) and (3) UNKNOWN from the repo.
- **NVDA context owed to the platform card:** MAJOR_EARNINGS rows in the calendar push (platform ask #3, open since 08-28, "harness-first"); single-stock session tiers (REGULAR 09:30–16:00 America/New_York, PRE/AFTER, OVERNIGHT) as platform read-model work; a BREAKOUT state must name its SIDE and never say BUY/SELL; cross-asset order US100 → DXY → yields via Pine only. Status: open.
- **Pine-independent NVDA analysis:** add `NVDA.NAS-24` to `AUTO_LIVE_SYMBOLS` in the v7 `.env` (shadow, `AUTO_LIVE_ARM=0`); proof is a scenario row in `logs/auto_scenarios.jsonl`. Status: UNKNOWN (v7 repo).
- **FAIL-SOFT policy decision (Iron Rule 1 exception):** the 2/day budget was spent on 2026-09-02; the mirror now shows it. "DECISION OWED BY SHYAM: keep fail-soft at 2/day, lower it, or fail-closed always." Evidence to decide with: outcomes of every journal row with `trace.agent_error_fallback`; also read the provider error codes (429/500/529). Status: open, human decision.
- **GOLD twin trade rows (ticket 1900277473):** bot side closed (one reporter); platform side must dedupe the duplicate ticket rows and add a unique index on trades(user_id, account_id, ticket). Status: platform-owned, UNKNOWN.
- **USOIL/OIL cosmetic twin on the macro fallback path:** "a later tidy, not a fault" (the platform has USOIL RETIRED so it is inert). Status: open, low.
- **Job 3 dual-MT5 isolation evidence (2026-09-04):** "Delete this entry only when each P0 record is `resolved` with its golden fixture named." Status per finding, from git: ISO-09 fixed db74e85, ISO-10 4b8352b, ISO-12 3b0d4a0, ISO-14 cfe18b1, ISO-16 f93a3fd (all 2026-09-05); ISO-11, ISO-13, ISO-15, ISO-20, ISO-21 fixed 2b9460c (2026-09-15); ISO-19 fixed 21f6f31. Whether each memory record in `brother-developer/brother_developer/memory/bugs/` is marked resolved is UNKNOWN here. The nine box flags (DRY_RUN, MT5_LOGIN, MT5_PATH, MAGIC_NUMBER, GUARDS_DISABLED, ADMIN_HALT_TOKEN, BRAIN_DISPATCH_MODE, EXECUTOR_IC_MARKETS_URL, v7 EXECUTOR_URL) remain UNKNOWN from the repo by construction; the P1 patch docstring states the GUARDS_DISABLED file "is absent on the box."
- **Deployment of the 2026-09-15 P1 executor batch to Windows:** the release-gate artefact `patch_v18_executor_iso11_13_15_20.py` exists with golden tests; proof of deployment is `/health` showing `guards_flag_present: false` and the new refusal reasons in the executor log. Status: UNKNOWN.
- **Platform work order for `/health` (2026-09-05):** `account_login` and `trade_mode` on the v18 executor `/health` — done in code (ISO-09, db74e85). Order was "ISO-02 (v7) first, then ISO-09 and ISO-10 here"; ISO-02 lives in the v7 repo. Status: code done; box deployment UNKNOWN.

# Open from the 2026-07-31 audit (still open per its addendum)

- **P2-1** global exposure / correlation caps are prompt text only; a hard cap in the executor (`len(ours) >= N → reject`) was suggested and not built.
- **P2-2** `macro_calendar` is always empty; nothing blocks a trade on news.
- **P2-3** sessions/DST delegated to Pine, no broker-server-time check beyond NTP.
- **P2-4** reconciler docstring promises position-count and net-exposure checks it does not perform.
- **P2-5** substituted Devil output is now tagged `failed: true` (done); downstream consumers should exclude it (platform/calibration side, UNKNOWN).
- **P2-8** housekeeping: stray `dashboard/backend/PYEOF`, stale `patch_*.py` one-shots to move to `archive/` — still present in the tree.
- The audit's own condition: after the P0/P1 fixes "this audit should be re-run against the true executor — and then handed to the independent cross-check auditor." No re-run is recorded in this repo.

# Queued, deliberately not built

- **Session-caller pending orders** (docs/SESSION_PENDING_SPEC.md, 2026-08-05): build only after the paper record is scored (n>=20), the executor can place and cancel pendings, and the cancel-then-market step is atomic; "Ship the MT5 auto-reconnect fix and let it settle FIRST."
- **MiroFish** (decisions.md 2026-05-13): revisit with 3+ months of live PnL or a separate GPU box; `MIROFISH_*` env vars are dead config.
- **CLAUDE.md queued work:** CMS Phase 1 per CMS_MASTERPLAN.md (login, account registry, per-account health + ON/OFF; "CMS manages accounts/routing, NEVER signals"); `usd_lag_backtest.py` (DXY_U6 vs gold lag rule, harness first); v18.9 dark flags awaiting harness validation: SB_PENDING, BIAS_INFO, ASSET_PULSE, BREAKOUT.
- **Researcher two-pass split** (search pass, then format pass) to end the recurring first-attempt parse failure (decisions.md 2026-05-21) — not implemented; the retry-with-reminder remains.

# Historical open items from May 2026 (decisions.md) — status

- nginx + Let's Encrypt for the brain: done 2026-05-20. TradingView IP allowlist: done 2026-05-21. Decision journal format: done 2026-05-21. Re-route v18 alerts to the brain: done (CLAUDE.md states alerts go to brain.signalmesh.dev). Positive-edge fixture to exercise DevilsAdvocate → RiskManager → Executor: not present as a named test; the ISO-19 fixtures fake all five stages instead.
- Polymarket items (wallet allowances, pUSD balance check, Poland geoblock, status site, ADMIN_HALT_TOKEN rotation "before live funding"): superseded by the executor's decommissioning; whether the token was rotated is UNKNOWN.

# Session-coordination endgame (docs/SESSION_COORDINATION.md)

The branch-ownership table is meant to shrink to one row: "every session merges to `main`, every box checks out `main`, ... and the single-file trick becomes history." The repo currently has `main` and `claude/exciting-hopper-uyy9gb`; which branch each box runs is UNKNOWN from here.
