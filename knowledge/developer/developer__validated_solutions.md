---
title: Brother Developer Agent — validated solutions
domain: developer
repo: sabuj14eu/brother-developer
sources: brother_developer/memory/bugs/, brother_developer/memory/adr/, brother_developer/ledger/ledger.jsonl, docs/JOB3_ISOLATION_2026-09-04.md, docs/JOB8_9_TRADING_LOGIC_2026-09-05.md, docs/P0_RELEASE_REPORT_2026-09-05.md, docs/WINDOW2_ISO02_ISO09_2026-09-05.md, docs/SESSION_PROTOCOL.md, docs/BROTHER_DEVELOPER.md, brother_developer/__main__.py, brother_developer/test_engine.py, brother_developer/ledger.py, brother_developer/replay.py, tests/test_brother_developer.py, tests/audit/2026-09-04_job3/test_cross_arm_isolation.py
verified_on: 2026-09-16
classification: INTERNAL
---

# Validated solutions from the Brother Developer Agent

Each entry below is a problem the Brother Developer windows actually diagnosed and, where a fix shipped, the fix and the rule it produced. "Fixed in repo" means the fix is committed in the trading repository on branch `claude/sniper-isolation-audit-completion-xdj6z4` with golden tests green, memory status `watch`, and NOT yet deployed to a box as of 2026-09-05. "Resolved" means verified on the box.

### ISO-01 v7 bridge attaches to a terminal path, not an account
question: Why could the v7 Windows bridge place orders on v18's MT5 account, and how was that closed?
answer: `sniper_executor.py` chose its terminal by a hard-coded path (`V7_MT5_PATH`, line 21) and called `mt5.initialize(path=...)` without a login, then treated `account_info() is not None` as "connected"; whoever was logged into that terminal was the account v7 traded, and `core/ic_markets.py:20-32` called any HTTP 200 "logged in". The fixture reproduced a POST `/execute` landing on the foreign account with `status ok`. The fix adds an asserted identity: `V7_MT5_LOGIN` from the service environment and `_identity_ok(acc)` checked on every request and after every reconnect, answering 503 and placing nothing on mismatch or missing env. Shyam deployed it on 2026-09-05 00:08 box time via `patch_iso01_identity.py`, verified by `/health` 200 on 52834417, secret still accepted, wrong secret rejected, and marker lines 259-286 in the running file. Rule produced (ADR-004): never infer an account from a path, a port or a service name; assert it against an expected login.
evidence: brother_developer/memory/bugs/BUG-2026-09-04-ISO01-v7-bridge-attaches-by-path.json (status resolved); docs/JOB3_ISOLATION_2026-09-04.md §4, §7a-7c; ledger rows 7, 10-14; brother_sniper_v7 tests/audit/2026-09-04_job3/test_v7_iso01_patch_golden.py; 2026-09-05

### ISO-02 the v7 bot fabricated a balance when the bridge could not answer
question: What happened when the v7 bridge was down and why is a default balance a P0?
answer: `core/ic_markets.py:62` read `balance` with a default of 1000.0 without checking the status code, so the bridge's own 503 became a balance of 1000.0, and lines 63-66 returned the env `ACCOUNT_BALANCE` (6000.0, explicitly set in the box .env) on any exception, labelled "conservative"; `bot.py:839-840` and `:1384-1385` did the same. The invented number passed the fail-closed margin gate and reached the equity guard and lot sizing, reproduced end-to-end through `bot.handle_signal`. Fixed in repo (v7 4937532): `get_balance()` returns None on non-200, missing field or exception; `EquityGuard.check(None)` blocks before any state update; `/health` reports `balance_state` UNKNOWN with 503; `/recalibrate` refuses; startup Telegram says UNKNOWN. Rule produced: no default numeric balance, price, margin or lot anywhere on the execution path; the sentinel for "unreadable" is None and it fails closed (Freshness Law, ADR-009).
evidence: brother_developer/memory/bugs/BUG-2026-09-04-ISO02-fabricated-balance.json (watch); docs/P0_RELEASE_REPORT_2026-09-05.md §1; ledger row 31; brother_sniper_v7 tests/audit/2026-09-05_iso02/; 2026-09-05

### ISO-03 v7 /execute had no account field and orders carried no magic number
question: How did the v7 bridge accept an order for an unknown account, and how are v7 positions told apart now?
answer: `sniper_executor.py:178-199` read only secret, symbol, direction, lot, sl, tp and signal_id, and the MT5 request at lines 234-245 had no `magic`, so an order tagged for any account executed on whatever the terminal held and the resulting position was anonymous except for a `BS_` comment prefix; the bot (`core/ic_markets.py:142-150`) never sent an account either. Fixed in repo (v7 f400347): `/execute` requires `account_id == V7_MT5_LOGIN` (400 `no_account_id`, 403 `account_mismatch`), every order carries `magic V7_MAGIC` (env `V7_MAGIC_NUMBER`, default 70007), `/positions` rows carry `magic` and `ours`, and the bot sends `account_id` from `V7_MT5_LOGIN`. ISO-04 (no magic) was folded into this record. Rule produced: an execution request without an account identity, or an MT5 order without a magic number, is never accepted.
evidence: brother_developer/memory/bugs/BUG-2026-09-04-ISO03-v7-execute-ignores-account.json (watch); ledger row 34; docs/P0_RELEASE_REPORT_2026-09-05.md §1, §5; 2026-09-05

### ISO-05 v7 /close and /modify acted on any ticket including v18 positions
question: Could the v7 bot close or re-stop a v18 trade on a shared terminal?
answer: Yes: `sniper_executor.py:299-323` (`/close`) and `:372-386` (`/modify`) resolved the ticket with `positions_get(ticket=...)` and sent the order with no magic, comment or account check, and the bot's SLOT-RECON (`bot.py:400-424`) adopted any `BS_`-commented position and then managed it through those routes; the fixture reproduced it against a fake terminal holding a magic-180000 position. Fixed in repo (v7 f400347): `_is_ours` requires magic 70007 or the legacy `BS_` comment, otherwise 403 `not_ours` and nothing is sent. Rule produced: a close/modify path must prove ownership of the ticket before sending.
evidence: brother_developer/memory/bugs/BUG-2026-09-04-ISO05-v7-close-modify-any-ticket.json (watch); ledger row 35; brother_sniper_v7 tests/audit/2026-09-04_job3/test_v7_bridge_identity.py::test_repro_ISO05_*; 2026-09-05

### ISO-09 the v18 executor bridge never asserted its MT5 login
question: Why was "MT5_LOGIN is set on the box" not enough to prove the v18 arm was on its own account?
answer: `executor_ic_markets/src/ic_markets/mt5_bridge.py:42-53` attached without login whenever any of MT5_LOGIN, PASSWORD or SERVER was empty (a mode `.env.example:9-10` documented), and even with all three set, lines 64-71 logged `info.login` and set `connected=True` without comparing it; a terminal logged into 52834417 would be adopted as "the v18 account". The box measurement (`MT5_LOGIN=52901228`, JOB3 §12) mitigated by configuration but not by code. Fixed in repo (brain db74e85): all three values required (missing means refuse, CRITICAL); the attached login is asserted after `initialize()` and on every probe; mismatch triggers `mt5.shutdown()` and `connected False`; `/health` reports `account_login`, `trade_mode`, `trade_mode_name`. Rule produced: no "attach to whatever is logged in" mode on any executor, and no `connected=True` without a login assertion.
evidence: brother_developer/memory/bugs/BUG-2026-09-04-ISO09-v18-bridge-no-login-assertion.json (watch); ledger row 32; tests/audit/2026-09-04_job3/test_cross_arm_isolation.py::test_golden_ISO09_patched_v18_bridge_refuses_without_or_against_its_login; 2026-09-05

### ISO-10 the Ed25519-signed envelope named an executor kind, not an account
question: Why was one brain signature valid for every IC Markets executor, and what does the envelope carry now?
answer: `shared/src/protocol/envelope.py:40-49` signed version, issued_at, nonce, target and signal, where `target` was a Literal of executor kinds; `executor_ic_markets/src/main.py:371-373` accepted on `target == 'ic_markets'` alone and never read an account field, and the dispatcher (`brain/src/signals/dispatcher.py:19-28`) routed by kind with one URL per kind. An unknown `account_id` inside the signal body was executed anyway, reproduced through the real `/signal` route. Fixed in repo (brain 4b8352b): `SignalEnvelope.account_id` sits inside the signed bytes; the dispatcher fills it from `EXECUTOR_IC_MARKETS_ACCOUNT` and refuses live dispatch without it; the executor rejects missing (`no_account_id`) or mismatched (`account_mismatch` against the ISO-09 asserted login) envelopes after signature verification. Deploy note: brain and executor together, with `EXECUTOR_IC_MARKETS_ACCOUNT=52901228` in the brain .env. Rule produced: a signed execution message must carry an immutable account identity inside the signed bytes.
evidence: brother_developer/memory/bugs/BUG-2026-09-04-ISO10-envelope-has-no-account.json (watch); ledger row 33; brain/tests/audit/2026-09-05_iso10/test_iso10_dispatcher_account.py; 2026-09-05

### ISO-12 a realised loss seen while the balance was unreadable was dropped from the daily counter
question: How could the v18 daily-loss cap fail to trip on a real loss?
answer: `executor_ic_markets/src/main.py:168` computed `bal = ... or 0.0` and line 171 set `bal = 0.0` on exception, and `src/utils/state.py:67` guarded the accumulation with `if balance and balance > 0`, so a close observed while MT5 could not report the balance was silently not added and MAX_DAILY_LOSS_PCT could not trip on it: UNKNOWN had become "no loss". Fixed in repo (brain 3b0d4a0): `state.add_realized_pnl` parks the loss in a persisted `pending_pnl_money` when the balance is None or 0 and applies it on the next measured balance; `_on_trade_closed` passes None and journals `pnl_unknown_pending`; the OPEN gate applies pending first and refuses new opens while a pending loss is unreadable, tripping the cap when the applied loss crosses it. Failure injection proved the pending loss survives a restart and still blocks. Rule produced: never `or 0.0` / `if balance` on a loss, margin or exposure counter; missing data blocks, it never zeroes.
evidence: brother_developer/memory/bugs/BUG-2026-09-04-ISO12-daily-loss-drops-loss-on-unreadable-balance.json (watch); ledger row 36; docs/P0_RELEASE_REPORT_2026-09-05.md §6; 2026-09-05

### ISO-14 an invalidated pending LIMIT was converted in place to a MARKET order
question: Did any code path turn a stale LIMIT into a MARKET order, and what replaced it?
answer: `executor_ic_markets/src/ic_markets/mt5_bridge.py:377-386` had a `[PEND->MKT]` branch that, when the entry had already moved through the market by at most 30% of the risk distance, set `action=TRADE_ACTION_DEAL` and the live price, contradicting ADR-006 regardless of its tests. Fixed in repo (brain cfe18b1): the branch is deleted; an invalid pending price is skipped with `pending_price_stale` and the measured `drift` at any tolerance; valid pendings and MARKET orders are unchanged, as the holds tests pin. This was a Job 4 finding met during Job 3. Rule produced: no automatic pending-to-market conversion at any drift tolerance.
evidence: brother_developer/memory/bugs/BUG-2026-09-04-ISO14-limit-converts-to-market.json (watch); ledger row 37; docs/P0_RELEASE_REPORT_2026-09-05.md §7; 2026-09-05

### ISO-16 no object stopped both accounts
question: What is the global emergency stop for the two arms and why did it not exist before?
answer: Before 2026-09-05 v18's kill switch was a per-process state file tripped by `/admin/halt` (`state.py:19`, `main.py:109-116`), v7 had only `state['paused']` in the bot and no halt route on the bridge, and the only cross-cutting file was `GUARDS_DISABLED`, a bypass; the cross-arm fixture showed v18 halted while the v7 bridge still filled, so ADR-008 had no implementation. Fixed in repo (brain f93a3fd + v7 f8aaf5f): one witness file, `GLOBAL_STOP_FILE` (default `C:\brotherbot\GLOBAL_STOP`, `/var/lib/brotherbot/GLOBAL_STOP` on Linux), present means STOP and unreadable means STOP; the v18 executor refuses every OPEN unless CLEAR, outside the GUARDS_DISABLED bypass, and its admin halt engages the witness; the v7 bridge reads the same file before every `/execute` and gains `/admin/halt` and `/admin/status` behind an admin token; closes are never blocked. Rule produced: an emergency stop that any executor can fail to observe is a P0.
evidence: brother_developer/memory/bugs/BUG-2026-09-04-ISO16-no-global-kill.json (watch); ledger row 38; tests/audit/2026-09-04_job3/test_cross_arm_isolation.py::test_golden_ISO16_v18_halt_engages_the_shared_witness_and_the_v7_bridge_refuses; 2026-09-05

### ISO-19 the council dispatched entry, SL, TP and risk written by an LLM
question: On the v18 AI-on path, who computed the numbers that reached MT5, and what does the council do now?
answer: The OPEN payload signed and sent on the AI-on path was the ExecutorPrep model's own JSON (entry_price, stop_loss, take_profit, risk_pct, order_type; prompts at `executor_prep.py:38-44` and `risk_manager.py:31-33`, dispatch at `council.py:244-262`), guarded only by a range check, and `compute_sltp` was never called on that path even though its contract says the LLM never outputs raw prices; a fixture showed a 0.5-dollar GOLD stop accepted where the floor is 4.32, and the box confirmed `brain/AI_ENABLED` PRESENT, so this was the live path. Fixed in repo (brain 21f6f31): `council.build_execution_payload()` computes entry from the signal and SL/TP through `compute_sltp` with the model's parameters clamped to `_SLTP_BOUNDS`; `risk_pct` starts at the 0.5 base and the model may only lower it; MARKET only; a calculator error rejects; ExecutorPrep is retired. Replay of 12 real journal rows widened 7 stops, reported as BEHAVIOR CHANGED and left for a human soak verdict. Rule produced (ADR-005): models choose bounded parameters, code computes prices and sizes; no model-produced number goes on the wire.
evidence: brother_developer/memory/bugs/BUG-2026-09-05-ISO19-llm-computed-execution-values.json (watch); docs/JOB8_9_TRADING_LOGIC_2026-09-05.md §1, §3, §6; ledger rows 26, 28, 29; brain/tests/audit/2026-09-05_iso19/test_iso19_execution_payload.py; 2026-09-05

### ISO-24 a DeepSeek/Gemini vote could reverse a v7 rule block
question: Could a model call in v7's filter turn a blocked signal into a trade?
answer: Yes: `filters/ai_filter.py:106-119` asked `deepseek_tiebreak()` when the rules blocked a non-news signal and, on `take=True` with confidence at least 60, set `passed=True` with the reason "AI OVERRIDE", a live HTTP call inside `handle_signal`; the override could only add risk, never remove it. Box measurement showed both provider keys set, `EYE_MODEL=shadow` (which asks two providers and returns the primary's vote, so not shadow-only), and a filter threshold of 38, meaning the branch was armed; 0 overrides were found in retained logs. Fixed in repo (v7 1443ec8): the override branch is removed, the vote is recorded as `shadow_only: True` in `breakdown['deepseek']`, and the block always stands; a provider error keeps the block. Rule produced: a model vote may veto but never unblock; no LLM in the decision path.
evidence: brother_developer/memory/bugs/BUG-2026-09-05-ISO24-llm-overrides-rule-block-v7.json (watch); docs/JOB8_9_TRADING_LOGIC_2026-09-05.md §4, §6; ledger row 30; brother_sniper_v7 tests/audit/2026-09-05_job9/test_job9_llm_override.py; 2026-09-05

### ISO-17 two MT5 terminals running from C:\MT5_v18
question: Why were there two terminal64.exe processes from the v18 install, and is it a fault?
answer: Not a fault. The Windows flags paste showed PID 2452 in session 1 (Shyam's RDP session, window title naming 52901228 as a demo account) and PID 7620 in session 0, started 7 seconds after the 2026-09-01 22:49:30 deploy; a session-0 service cannot attach to a session-1 window, and `mt5_bridge.py:47-53` falls back to launching the terminal by path, so the executor runs its own instance. Non-portable MT5 keeps its data folder per Windows user, so the two do not share state. Consequences recorded: manual orders on 52901228 would come from the interactive terminal (no magic, invisible to the reconciler by design), and the executor's login is provable only from its own log because its terminal has no window title.
evidence: docs/JOB3_ISOLATION_2026-09-04.md §6 (hypothesis), §12 (resolved); ledger row 24; 2026-09-05

### ISO-18 the box magic number is 20260530 while every document says 180000
question: What magic number does the v18 executor actually use, and why does the mismatch matter?
answer: The measured `MAGIC_NUMBER` in the Windows .env is 20260530, while the code default (`mt5_bridge.py:21`), `.env.example:20` and `docs/PROTOCOL.md:97` all say 180000 and 20260530 appears in no repo. A redeploy from `.env.example` would tag new positions 180000 and make every open 20260530 position an orphan to the reconciler. Classified P2 documentation drift; the proposed fix is to record 20260530 as the live value in `.env.example` and PROTOCOL.md or document why it differs, with no change to the box. The report also corrected its own earlier table, which had listed "180000 expected" as if measured. Not fixed as of the last commit.
evidence: docs/JOB3_ISOLATION_2026-09-04.md §12; ledger row 24; docs/JOB8_9_TRADING_LOGIC_2026-09-05.md §2 (ISO-23 pairs with it); 2026-09-05

### ISO-25 filter threshold default 5 closed by measurement
question: Was the v7 AI filter running with its pilot default threshold of 5?
answer: No. Code defaults (`ai_filter.py:10,23`, `learning/weight_engine.py:6`) set the threshold to 5 when no weights file exists, which would make the filter a data collector that blocks almost nothing; the box's `learning/weights.json` (gitignored) showed threshold 38 with 207 samples updated 2026-09-04T22:03Z. The observation was closed as measured; its consequence was that blocks do happen, so the ISO-24 override branch was reachable.
evidence: docs/JOB8_9_TRADING_LOGIC_2026-09-05.md §2, §6; ledger row 28; 2026-09-05

### W2-01 Window 2 branched from a main that never contained the audit branch
question: Why did Window 2's v7 tree have the pre-ISO-01 bridge again, and how was it converged?
answer: The Job 3 audit branch (evidence suite, `patch_iso01_identity.py`, the ISO-01 repo patch, the pre-patch fixture) was never merged to v7 or brain `main`, so Window 2, branching from `main`, took its ISO-02 pre-patch copy from a pre-ISO-01 tree; the brain branch likewise missed four `push_bias` commits and the audit branch's three. `git merge-tree` dry runs showed zero conflicts, and the convergence was two fast-forwards of `main` to the audit branch followed by a clean merge of each window's single commit, run by Shyam in the `/home/shyam/audit-2026-09-04` clones, never a live checkout. Rule produced: every window from here branches from `main`, and `main` must carry the audit branch first.
evidence: docs/JOB3_ISOLATION_2026-09-04.md §10 (finding), §11 (converged); ledger rows 21, 23; commit b7c6813; 2026-09-05

### W2-02 the ISO-02 proposal's GuardResult hunk would have raised TypeError
question: What defect did the review of the ISO-02 diff catch before the release gate?
answer: The proposed `EquityGuard.check` hunk constructed `GuardResult(allowed=False, block_reason=..., tier_hit="UNKNOWN")`, but `risk/equity_guard.py:24-27` declares seven fields without defaults, four of which were missing, so the first None balance would have raised `TypeError`. The fix used the existing `self._block("UNKNOWN", 0, 0, 0, "balance UNKNOWN — bridge unreadable")` placed before `self.update_balance(bal)`, pinned by `test_iso02_equity_guard_none.py`, closed on v7 5369fa3. Rule produced: a proposal's own HOW TESTED (here, `check(None)` pinned) must be written as a test on the patch commit, not as a requirement in prose.
evidence: docs/JOB3_ISOLATION_2026-09-04.md §10; ledger row 22 (finding_closed); brother_sniper_v7 5369fa3; 2026-09-05

### The agent CLI resolved the workspace as /home and recorded every repo as NOT_A_CHECKOUT
question: Why does the committed manifest show all three repos as NOT_A_CHECKOUT?
answer: `brother_developer/__main__.py` originally computed `ROOT = HERE.parents[1].parent`, one level too high, so the Job 3 manifest `BD-<date>-<time>-9191f2` recorded paths under `/home/` and state `NOT_A_CHECKOUT` for every repo. Window 2 fixed it to `HERE.parents[1]` and pinned it with `test_the_cli_resolves_the_workspace_one_level_up`; the Job 3 window verified the fix against the remote. The committed manifest was left as it was recorded.
evidence: docs/JOB3_ISOLATION_2026-09-04.md §2 (P3), §10; docs/WINDOW2_ISO02_ISO09_2026-09-05.md; ledger row 20 (fix); tests/test_brother_developer.py; 2026-09-04

### The previous audit existed only in an ephemeral container
question: What happened to the 661-line n45mwm isolation audit, and what rule came out of it?
answer: A 2026-09-04 session produced 661 lines of P0 findings and a reproducing test suite, then deleted the suite and could not push; the branch `claude/sniper-account-isolation-audit-n45mwm` and the file `docs/AUDIT_ACCOUNT_ISOLATION_2026-09-04.md` were searched in every remote ref of four repos, `git log --all`, GitHub code search and local disk, and do not exist. The verdict on "read the audit" was NOT RUNNABLE and Job 3 was rebuilt from the branch heads. The session protocol was written from it: push the designated branch empty at minute two, push after every job, never delete evidence, and if push is denied print the file in chat and stop.
evidence: docs/SESSION_PROTOCOL.md; docs/JOB3_ISOLATION_2026-09-04.md §0; ledger row 2 (audit_missing); commit 3432cb1; 2026-09-04

### The ledger chain survived two branch merges
question: How is the hash chain kept intact when two windows append to the ledger on different branches?
answer: When Window 2's branch and the Job 3 branch both appended rows, the merge kept the chain from `main` and re-appended the diverging rows at the head so every `prev` still matches; row 23 carries the note "re-appended after merging main (chain kept from main)". `ledger verify` reported ok with 20 rows after the first merge and 24 after the closure; the committed file has 39 rows ending at `p0_queue_complete`.
evidence: commits 1e9e1d1 and a7cc1a1; brother_developer/ledger/ledger.jsonl rows 21-25; docs/JOB3_ISOLATION_2026-09-04.md §10, §13; 2026-09-05

### A grep for council_live rows returned 0 because the journal is written compact
question: Why did the first count of council-dispatched journal rows come back as zero?
answer: The Job 8/9 paste command grepped for `"dispatch_mode": "council_live"` with a space after the colon, but `decision_journal.py:198` writes the journal with compact separators, so the pattern never matched and 0 was a formatting miss, not a measurement. The count was re-labelled UNKNOWN and a corrected histogram command (`grep -o '"dispatch_mode":"[a-z_]*"' logs/decisions.jsonl | sort | uniq -c`) was issued. Rule reinforced: a zero from a grep is a claim about the pattern until the format is checked.
evidence: docs/JOB8_9_TRADING_LOGIC_2026-09-05.md §6, §7; ledger row 28; 2026-09-05

### The v18 executor's connect line was not in the newest log
question: Where is the v18 executor's "MT5 connected: account=" line when the current log does not contain it?
answer: The service last initialised on 2026-09-01 and loguru zips rotated days, so the newest `executor_ic_*.log` had no connect line; the report first pointed at NSSM's `service_stderr.log`, but the flags paste showed no such file exists, only daily zips 08-06 to 09-04 plus the 09-05 plain log. The corrected read-only command expands `executor_ic_2026-09-01.log.zip` to a temp folder and runs `Select-String` for the pattern there. As of the last commit this witness is still owed; until it is seen, the v18 login is inferred from config, not measured.
evidence: docs/JOB3_ISOLATION_2026-09-04.md §12; docs/JOB8_9_TRADING_LOGIC_2026-09-05.md §7; ledger row 28; 2026-09-05

### EYE_MODEL=shadow did not mean shadow-only
question: Why was the v7 AI vote armed even though EYE_MODEL was set to "shadow"?
answer: `deepseek_vote.py:231-243` in shadow mode asks two providers and RETURNS the primary's vote, and `ai_filter.py:112-115` then acted on it; "shadow" named the second model's role, not the first's. With both keys set and a threshold of 38 the override was reachable. The report applied the rule "one word carrying two facts is the fault to hunt" and marked ISO-24 ARMED. Removing the override branch (ISO-24 fix) made the vote genuinely shadow-only.
evidence: docs/JOB8_9_TRADING_LOGIC_2026-09-05.md §6; ledger row 28; brother_developer/memory/bugs/BUG-2026-09-05-ISO24-llm-overrides-rule-block-v7.json; 2026-09-05

### The ISO-19 replay reported BEHAVIOR CHANGED instead of "better"
question: How was the ISO-19 fix graded when the new stops differed from the old ones?
answer: Twelve real journal rows shipped with `compute_sltp` were rebuilt through `build_execution_payload`; all twelve produced a payload with entry equal to the signal entry and MARKET only, and 7 of 12 stops widened to the symbol noise floor compared with Pine's raw stop. Per iron rule 6 this is reported as BEHAVIOR CHANGED and the report refuses to call it an improvement: the verdict needs a dual-shadow soak of at least 20 rows reviewed by a human, and it is one of the five reasons real money is NO-GO.
evidence: docs/P0_RELEASE_REPORT_2026-09-05.md §3, §10; ledger rows 29, 39; brain/tests/audit/2026-09-05_iso19/ test_replay_ISO19_twelve_real_rows_behavior_changed_report; 2026-09-05

### The USE_DEMO=false label contradicted the all-demo constitution
question: Is the v7 account real or demo, and how should the platform find out?
answer: The v7 `.env` on Contabo says `USE_DEMO=false` and the startup Telegram says "REAL", while both trading constitutions say all accounts are demo; the report found the flag is a label only (`bot.py:34`, a dead XTB port). 52901228 was later measured as DEMO from its terminal window title, but 52834417 runs in session 0 with no title and its `/health` had no `trade_mode`, so its mode is UNKNOWN. The solution is the heartbeat work order: carry `account_login` and MT5 `trade_mode` (0 demo, 1 contest, 2 real) in both heartbeats so demo/real is measured, not configured; the platform v5.25.4 already renders MEASURED vs CONFIGURED LABEL.
evidence: docs/JOB3_ISOLATION_2026-09-04.md §6, §8, §12; docs/HEARTBEAT_WORK_ORDER_2026-09-05.md; ledger rows 9, 16, 19, 24; 2026-09-05

### Platform v5.25.4 stopped grading v7 on fabricated money
question: What did the platform change in response to the ISO-02 finding?
answer: The platform window's reply (v5.25.4 on vmi3221804) made the v7 desk render equity, peak balance, day PnL and week PnL as UNKNOWN with the reason when `bridge_ok` is false, so nothing grades v7 on invented numbers; the account reads MEASURED only when the heartbeat carries `account_login`, otherwise CONFIGURED LABEL; and the bridge's own `msg` prints beside the red light. Verified by Shyam: fast-forward, "Application startup complete", version chip 5.25.4, account state chip on /v7.
evidence: docs/JOB3_ISOLATION_2026-09-04.md §8; ledger row 16 (platform_reply); 2026-09-05

### Test verdicts never invent PASS
question: How does the Brother Developer test engine avoid reporting PASS for a run that did not really pass?
answer: `test_engine.classify` returns UNKNOWN when there is no exit code, NOT RUNNABLE when the output mentions a missing module, import error, missing path or "no tests ran", PASS only for exit 0 with an "N passed" summary, FAIL on any failure or error count or non-zero exit, and UNKNOWN for exit 0 with no summary; `run` returns NOT TESTED for a repo with no tests/ directory. The unit test pins all five branches, including that `classify(0, "")` is UNKNOWN.
evidence: brother_developer/test_engine.py; tests/test_brother_developer.py::test_verdicts_never_invent_pass; 2026-09-04

### The cross-arm suite skips as NOT RUNNABLE instead of passing vacuously
question: What does the Brother Developer suite report when the sibling trading repos are absent?
answer: `tests/audit/2026-09-04_job3/test_cross_arm_isolation.py` resolves `../brother_sniper_v7` and `../brother-brain-v2` by path and calls `pytest.skip("NOT RUNNABLE: ...", allow_module_level=True)` when either is missing, and `importorskip` for flask and loguru; the closure report records "8 passed 1 skipped without them: NOT RUNNABLE, never PASS" against 13 (later 15) with siblings. Rule: a missing fixture, dependency or identity is NOT RUNNABLE, never a default PASS.
evidence: tests/audit/2026-09-04_job3/test_cross_arm_isolation.py lines 17-24; tests/audit/2026-09-04_job3/README.md; docs/JOB3_ISOLATION_2026-09-04.md §13; 2026-09-05

### The developer package is sealed off from the trading code
question: How is it enforced that the Brother Developer Agent cannot reach the platform, a broker or the network?
answer: `test_the_agent_is_sealed_off_from_trading_code` reads every `.py` in `brother_developer/` and asserts none contains `from app`, `import app`, or an import of httpx, requests, MetaTrader5 or socket; the SYSTEM MAP uses `ast` so scanning never executes repo code, and the manifest shells out to git only. The README states the same rules: no import of `app`, no network client, no write outside evidence/ and ledger/, no credentials.
evidence: tests/test_brother_developer.py::test_the_agent_is_sealed_off_from_trading_code; brother_developer/repo_map.py; README.md; 2026-09-04

### ISO-01 deploy verified in stages, not from one 200
question: Why was the ISO-01 deploy graded UNKNOWN after /health returned 200 on the right account?
answer: Because an unpatched bridge answers the same 200 when the terminal happens to hold the right account; the first paste showed only step 4b (NSSM env set, restart, /health ok), so the patch state was UNKNOWN until the distinguishing witnesses appeared: the backup file `sniper_executor.py.bak.20260905_000815` (written only after both anchors matched), the bot secret still accepted from Contabo, a wrong secret rejected, and finally the marker lines in the running file. Rule reinforced (iron rule 6 of the trading constitutions, "health endpoints lie"): a deploy is verified by the artefact that only the new code could produce.
evidence: docs/JOB3_ISOLATION_2026-09-04.md §7a-7c; ledger rows 11 (verdict UNKNOWN), 12 (PASS on 3 witnesses), 14 (resolved); 2026-09-05

### A box paste is graded against a "correct output looks like" block
question: How does the agent turn a box fact it cannot see into a measurable answer?
answer: Each read-only paste command in the reports is followed by a "correct output looks like" block that states the values isolation requires (not what is assumed to be there), plus a line explaining what each deviation means (for example `:5001` in EXECUTOR_IC_MARKETS_URL is a cross-wiring that stops the day). Commands print secrets as set/EMPTY only and hide NSSM env values unless the key is one of the audited flags. Results are recorded as `box_witness` ledger rows with a `still_unknown` list.
evidence: docs/JOB3_ISOLATION_2026-09-04.md §3a-3b; docs/JOB8_9_TRADING_LOGIC_2026-09-05.md §5; ledger rows 9, 24, 28; 2026-09-04

### The fail-soft council bypass was recorded as accepted risk, not silently passed
question: Does anything bypass the v18 council today, and how is it recorded?
answer: `brain/src/main.py:433-465` approves A/A+ Pine signals on agent failure up to `FAILSOFT_MAX_PER_DAY` (measured 2), an explicit .env decision; Job 8 recorded it as accepted risk with a noted tension with ADR-003 for the real-money gate rather than a finding, so the decision stays visible in the ledger and the report. Rule: an explicit human decision that widens risk is logged with its rationale, never hidden and never re-litigated by the agent.
evidence: docs/JOB8_9_TRADING_LOGIC_2026-09-05.md §2; ledger row 27 (job8 accepted_risk); 2026-09-05

### Fallback audit: which `or 0` sites fail closed and which are findings
question: Which fallback sites in the brain and bot were graded PASS and which became findings?
answer: `brain/src/main.py:386-387` `margin_free or 0` / `balance or 0` makes the floor `max(0, 100)` and `0 < 100` skips the trade, so it fails closed (PASS); `bot.py:525-536` journals UNVERIFIED after ten missing history lookups (PASS, a truth guard); `core/signal_memory.py` and `mt5_bridge.py:144,148` `or 0` are analytics only (PASS). Findings: executor `main.py:168,171` (ISO-12), the seven `bot.py`/`ic_markets.py` balance sites (ISO-02), `bot.py:411-415` orphan adoption with sl 0 (ISO-22, P2), `pine_trust.py:73-78` raw Pine SL/TP on calculator error (ISO-21, P1), executor `main.py:433` missing risk_pct sized at the cap (ISO-20, P1), `core/ic_markets.py:44` `except: pass` (P3).
evidence: docs/JOB8_9_TRADING_LOGIC_2026-09-05.md §2; ledger row 27; 2026-09-05

### Scalar broker offset from a single tick (seeded platform record)
question: What went wrong when the reporter inferred the broker clock from one gold tick?
answer: On 2026-08-20 the MT5 reporter read one tick, gold's during the metals rollover break, and inferred the broker offset from it; a single tick cannot separate a clock offset from a stale quote, and a scalar offset cannot convert a series that contains DST, so about 30,209 rows were mis-stamped. The solution: two fresh independent witnesses (one trading 24/7) or refuse; per-bar DST conversion; both ends report stored counts. Do not reintroduce any timestamp inferred from one witness or any scalar offset applied to a multi-season series.
evidence: brother_developer/memory/bugs/BUG-2026-08-20-scalar-offset.json (Sniper-System, commit 5260ce9, P2, resolved); tests named tests/test_reporter_offset.py, tests/test_candle_audit.py; 2026-08-20

### Trade twins: one broker ticket stored as two rows (seeded platform record)
question: How did the platform end up managing a ghost trade for two days?
answer: Five reporter processes raced a read-then-insert heartbeat with no uniqueness on (user, account, ticket), so one broker ticket became two open rows (155/156) and the desk managed the ghost. The fix added the partial unique index `uq_trade_ticket`, made the heartbeat adopt the winner's row on collision, and moved the twins into the audit log. Do not reintroduce any read-then-insert on a broker identity without a unique constraint.
evidence: brother_developer/memory/bugs/BUG-2026-09-01-trade-twins.json (Sniper-System, commit 7fa7330, P0, resolved); tests/test_trade_twins_523.py; 2026-09-01

### RETEST state persisted after its predicate stopped holding (seeded platform record)
question: Why did the GOLD desk show RETEST while price was 3 ATR from the edge, and what replaced it?
answer: ny-v1 set state=RETEST on one bar and had no branch for a later bar that contradicted it, and the explanation was rebuilt from the stale word; the latest closed 15m close was 3.06 ATR from the broken edge. ny-v2 (`services/session_state`) is a pure function over an immutable per-bar fact pack that re-evaluates RETEST every bar, adds BACK_IN_RANGE and EXPIRED phases, and generates the explanation from the same observation. Do not reintroduce a state that persists without its predicate holding on the newest closed bar (ADR-007).
evidence: brother_developer/memory/bugs/BUG-2026-09-03-retest-persistence.json (Sniper-System, commit 297554c, P1, resolved); tests/test_gold_ny_breakout_525.py; 2026-09-03

### Memory records carry the observation commit, not the fix commit
question: Why does an ISO memory record's `commit` field point at c1618f5 or cfc52e9 rather than the fix?
answer: The schema's `commit` records the branch head at which the bug was observed and reproduced (v7 c1618f5, brain cfc52e9, or the later heads for ISO-19/24); the fix commit and its deploy condition are written into the `solution` text ("FIXED IN REPO 2026-09-05, brother_sniper_v7 4937532 ... watch = awaiting release gate ... resolved when ..."). This keeps the pre-fix reproduction addressable and makes the status transition (`watch` to `resolved`) depend on a named box witness.
evidence: brother_developer/memory.py REQUIRED schema; brother_developer/memory/bugs/BUG-2026-09-04-ISO02-fabricated-balance.json; 2026-09-05
