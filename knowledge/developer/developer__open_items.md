---
title: Brother Developer Agent — open items
domain: developer
repo: sabuj14eu/brother-developer
sources: CLAUDE.md, README.md, docs/BROTHER_DEVELOPER.md, docs/JOB3_ISOLATION_2026-09-04.md, docs/JOB8_9_TRADING_LOGIC_2026-09-05.md, docs/P0_RELEASE_REPORT_2026-09-05.md, docs/WINDOW2_ISO02_ISO09_2026-09-05.md, docs/HEARTBEAT_WORK_ORDER_2026-09-05.md, docs/SESSION_PROTOCOL.md, brother_developer/memory/bugs/, brother_developer/ledger/ledger.jsonl
verified_on: 2026-09-16
classification: INTERNAL
---

# Open items of the Brother Developer Agent (state at commit 55aba5b, 2026-09-05)

This repo has no `docs/OPEN_ITEMS.md` of its own (the sibling constitutions require one; the bot repo's OPEN_ITEMS was mentioned as part of the Job 3 audit branch). The list below is assembled from the closing sections of the reports and the ledger. Status words: OPEN (no fix), WATCH (fixed in repo, awaiting release gate), OWED (a box fact Shyam must paste), DEFERRED (by decision).

## Release gate — ten P0 fixes awaiting deploy (WATCH)

The Brother Developer release gate holds ten P0 fixes that are green in the repos and UNKNOWN on the boxes: ISO-19, ISO-24, ISO-02, ISO-09, ISO-10, ISO-03, ISO-05, ISO-12, ISO-14, ISO-16 (`docs/P0_RELEASE_REPORT_2026-09-05.md` §1, §8; memory status `watch`). Nothing was deployed by the window. Deploy requirements (§9): brain + v18 executor together with `EXECUTOR_IC_MARKETS_ACCOUNT=52901228` in the brain .env (not yet set) and MT5_LOGIN/PASSWORD/SERVER present in the executor .env; v7 bridge with `V7_MAGIC_NUMBER=70007` and `ADMIN_HALT_TOKEN` set, v7 bot with `V7_MT5_LOGIN` in its .env; a shared writable `GLOBAL_STOP_FILE` path for both Windows services; after each deploy read the named `/health` witness. Each memory record names its own "resolved when" condition (see developer__evidence.md).

## Real-money conditions (OPEN)

REAL MONEY is NO-GO (`docs/P0_RELEASE_REPORT_2026-09-05.md` §10). It is reconsidered only when: every P0 box column reads a measured witness; the ISO-19 change (7/12 stops widened) has a dual-shadow soak of n≥20 rows with the widened stops reviewed by a human; ISO-06, ISO-11 and ISO-15 are fixed and deployed; and the two UNKNOWN box facts below are measured.

## P1 findings, no memory record yet (OPEN, deferred by queue order)

- ISO-06 — v7 bridge has no idempotency: the same `signal_id` twice = two fills (`sniper_executor.py`). Money-touching; blocks real money.
- ISO-07 — `EquityState` has no account field, default `peak_balance` 1000.0 (`risk/equity_guard.py:18-22`).
- ISO-08 — bot dedupe key is `symbol:signal_id`, no account (`bot.py:284-288`; ADR-004 says `(account_id, signal_id)`).
- ISO-11 — v18 margin floor is fail-open (`mt5_bridge.py:318-334`). Money-touching; blocks real money.
- ISO-13 — `ExecutorState` has no account field (`state.py:14-25`).
- ISO-15 — the `GUARDS_DISABLED` file bypasses both daily caps (`main.py:65-68, 421-430`); the ISO-16 global stop is not bypassable by it, the caps still are. Money-touching; blocks real money.
- ISO-20 — executor `s.get("risk_pct", 0.5)` sizes a missing risk at the cap (`main.py:433`); proposal: missing = reject.
- ISO-21 — `pine_trust.py:73-78` falls back to raw Pine SL/TP when the calculator raises; proposal: fail closed (the ISO-19 rule "calculator error rejects" applied to the pine_trust path would close it).
Source: `docs/JOB3_ISOLATION_2026-09-04.md` §2, §5; `docs/JOB8_9_TRADING_LOGIC_2026-09-05.md` §2; P0 report line 6 "P1s ISO-06/07/08/11/13/15/20/21 untouched by decision (queue order)".

## P2 findings (OPEN)

- ISO-18 — box `MAGIC_NUMBER=20260530` undocumented; code default, `.env.example:20` and `docs/PROTOCOL.md:97` say 180000. Fix proposed: record the live value or the reason it differs (JOB3 §12).
- ISO-22 — orphan adoption with `sl or 0` then managed on 0 (`bot.py:411-415`); proposal: adopt only with sl>0, else alert and leave (JOB8_9 §2).
- ISO-23 — `magic_number: 180000` hard-coded in the brain payload (`pine_trust.py:99`, `executor_prep.py:43`) while the executor uses its own `MAGIC_NUMBER`; pairs with ISO-18 (JOB8_9 §2).
- `USE_DEMO=false` label in the v7 .env vs the all-demo constitution; settled by measurement once `trade_mode` is in the heartbeat (JOB3 §6, §8).
- v18 manage path: TP magnitude unbounded on LLM MODIFY requests (P3 note, JOB8_9 §1).
- `core/ic_markets.py:44` `except: pass` in `ensure_connected` (P3, JOB8_9 §2).

## Box facts still owed (OWED)

- The v18 executor's own "MT5 connected: account=" log line. It lives in the zipped 2026-09-01 day; the corrected `Expand-Archive` + `Select-String` command is in `docs/JOB8_9_TRADING_LOGIC_2026-09-05.md` §7. Until seen, the v18 login is inferred (MT5_LOGIN set, `mt5_connected true`), not measured.
- The `trade_mode` of 52834417 (demo/contest/real). Its terminal runs in session 0 with no window title and the v7 `/health` has no `trade_mode` until the heartbeat work order lands.
- The `council_live` row count in `logs/decisions.jsonl` (first grep missed the compact format; corrected histogram command in JOB8_9 §7).
- `C:\Users\Administrator\flags-2026-09-04.txt` was the original owed file (WINDOW2 report); its content arrived as JOB3 §12, so only the two witnesses above remain from it.

## Heartbeat work order (OPEN, recorded not applied)

`docs/HEARTBEAT_WORK_ORDER_2026-09-05.md`: `account_login` + `trade_mode` in both heartbeats, six append-only edits (v7 bridge `/health`, `core/ic_markets.get_account()`, `core/v7_status.build_heartbeat`, `bot.py` call site, v18 executor `/health`, `brain/src/platform_mirror.py`). The ISO-09 fix (`db74e85`) already adds `account_login`/`trade_mode` to the v18 `/health`; the v7 side and the mirror forwarding are UNKNOWN in this repo (no ledger row records them done).

## Phase 2 gate and the unattempted jobs (OPEN)

`CLAUDE.md`: Phase 2 (sandbox repair) starts only after Job 1 (the dual-MT5 isolation audit with its `object · file · has account_id · immutable · test` table) exists. `docs/JOB3_ISOLATION_2026-09-04.md` §5 records that Jobs 1, 2, 4–10 "were not attempted beyond what the Job 3 fixture reached"; the P0 report §5 gives an account identity chain "as it will stand after the coupled deploys" but not the Job 1 table as specified. Jobs done: 3 (closed), 8 and 9. Still open per the spec: Job 1 (table), Job 2 (one correlation set per hop: `trace_id, signal_id, decision_id, account_id, executor_id, broker_ticket, position_ticket`, naming every hop that drops one), Job 5 (emergency-stop propagation proof beyond the ISO-16 fixtures, including the fail-soft branch), Job 6 (EquityGuard per account — ISO-07 says it is per process), Job 7 (dedupe on `(account_id, signal_id)` — ISO-06/08/13 say it is not), Job 10 (golden fixtures from the memory records: GOLD stale candle, forming candle, twin ticket, scalar offset, expired signal, invalid signature, wrong account, missing margin, LIMIT invalidation, daily loss, global stop — the last six exist inside the ISO fixtures, the first five do not). Whether the ten P0 fixes count as Phase 2 having started is not stated in the repo: UNKNOWN.

## Phase 3–6 (OPEN by design)

Replay runners (Phase 3; `replay.py` holds only the comparison contract), research agent (Phase 4), release reports and approval workflow beyond the hand-written P0 report (Phase 5), and the controlled release assistant with post-deploy verification and rollback recommendation (Phase 6) are not built (`docs/BROTHER_DEVELOPER.md` §3).

## Repo hygiene (OPEN)

- `README.md` still documents the pre-split invocation (`python -m tools.brother_developer …`, `git subtree split` from `/srv/brotherbot`) and says the package "lives here only until `sabuj14eu/brother-developer` exists"; the split happened on 2026-09-04 (commit `af42bf3`). The spec's §7 "First commands" has the same stale form.
- `docs/SESSION_PROTOCOL.md` step 7 lists four verdicts; `CLAUDE.md` and the code list five (adds NOT TESTED).
- The committed manifest `brother_developer/evidence/BD-20260904-212928-9191f2.json` records every repo as `NOT_A_CHECKOUT` because of the since-fixed ROOT bug; Window 2's manifest `BD-20260904-224305-190e6f` is not committed (directory gitignored).
- The ADR files contain Decision and Consequence only; the rationale text of the Master Engineering Specification v1.0 is not in the repo.
- The ISO-16 memory record's `repo` field is `brother-developer` although the fix lives in brother-brain-v2 and brother_sniper_v7 (its `files` list carries both repo prefixes).
- Two seeded platform commits (`5260ce9`, `297554c`) are not reachable in the local Sniper-System checkout as of 2026-09-16; whether history was rewritten is UNKNOWN.
- The previous window's 661-line audit (`claude/sniper-account-isolation-audit-n45mwm`) is gone; if Shyam has it locally, committing it under `brother-developer/docs/` lets a window diff its P0 list against JOB3 §2 (JOB3 §0). Next windows must not search for it again.

## Accepted risk on record (DEFERRED by explicit decision)

The brain's fail-soft path approves A/A+ Pine signals on agent failure up to `FAILSOFT_MAX_PER_DAY=2` by explicit .env decision, recorded as accepted risk with a tension against ADR-003 that must be revisited at the real-money gate (`docs/JOB8_9_TRADING_LOGIC_2026-09-05.md` §2; ledger row 27).
