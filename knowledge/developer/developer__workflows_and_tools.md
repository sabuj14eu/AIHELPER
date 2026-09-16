---
title: Brother Developer Agent — workflows and tools
domain: developer
repo: sabuj14eu/brother-developer
sources: docs/SESSION_PROTOCOL.md, docs/BROTHER_DEVELOPER.md, docs/JOB3_ISOLATION_2026-09-04.md, docs/JOB8_9_TRADING_LOGIC_2026-09-05.md, docs/P0_RELEASE_REPORT_2026-09-05.md, docs/WINDOW2_ISO02_ISO09_2026-09-05.md, docs/HEARTBEAT_WORK_ORDER_2026-09-05.md, README.md, CLAUDE.md, brother_developer/__main__.py, tests/audit/2026-09-04_job3/README.md, tests/test_brother_developer.py
verified_on: 2026-09-16
classification: INTERNAL
---

# The Brother Developer session protocol

`docs/SESSION_PROTOCOL.md` governs every AI window that touches the trading repos. It was written after 2026-09-04, when an audit session produced 661 lines of P0 findings, ran a suite that reproduced a misrouted order and a fabricated balance, then DELETED that suite and could not push — "Nothing was lost, by luck. These rules make luck unnecessary."

Opening (first 5 minutes, before any reading): (1) `git -C <repo> status --porcelain` in every repo — must be empty, paste it; (2) create the designated branch and push it EMPTY at once (`git checkout -b <branch> && git push -u origin <branch>`) so a push denial shows up at minute two; (3) `python3 -m brother_developer manifest "<task>"` — the run is on record.
During: (4) push after every job, one commit per job (`Job 3 — …`), pushed immediately — "work that exists only in a container does not exist"; (5) never delete evidence — reproduction tests live under `tests/audit/<date>_<job>/` in the repo they test, marked `# EVIDENCE — reproduces finding X, keep`; (6) never edit a live checkout (`/srv/brotherbot`, `/home/shyam/brain-v2`, `/home/shyam/brother_sniper_v7`), never `git checkout` another branch on a box; (7) verdicts PASS / FAIL / NOT RUNNABLE / UNKNOWN, UNKNOWN never PASS, every claim names file and line.
If push is denied: (8) do not route around it — print the full file content in chat or offer it as an attachment, say so, the human commits it, then stop.
Closing (last 5 minutes): (9) `git status --porcelain` empty in every repo, `git log origin/<branch> -1` shows the last job's commit on the remote, ledger append `session_end`; (10) handoff in the report: what is UNKNOWN and why, what the next window must not repeat.
Model switching: never switch the model on a job mid-flight; finish, push, close the window, open the next one with this protocol. "Two windows on one box checkout is the fault the coordination file exists for."

# How a Brother Developer report opens: six lines first

Every bot-side report starts with a fixed six-line summary (`docs/JOB3_ISOLATION_2026-09-04.md` §9 opening prompt; `docs/P0_RELEASE_REPORT_2026-09-05.md` head): branch pushed; git status of every repo; jobs done; P0 count; UNKNOWN count; what was not done. The closing handoff names what is UNKNOWN and what the next window must not repeat (for Job 3: do not search for the n45mwm audit; do not run the Job 3 suites on a box checkout, because they write `sniper_executor.log` beside the file and `logs/` under the executor).

# How a Brother Developer job runs

Every job in `docs/BROTHER_DEVELOPER.md` §5 is READ + TEST + REPORT first; a patch is a separate, gated step with its own manifest and ledger rows. The observed sequence in the Job 3 window (ledger rows 1–8): manifest → establish what is NOT RUNNABLE → build fixtures per arm and run them (ledger `test` rows with commit and pass count) → write memory records for every P0 (ledger `memory`) → propose the highest-risk patch, not applied (ledger `patch_proposed`, `applied: false`) → `session_end` with the open P0 list and the UNKNOWN flag list. Box facts the repos cannot see are turned into read-only paste commands for Shyam (JOB3 §3a Contabo bash, §3b Windows PowerShell; JOB8_9 §5, §7), with a "correct output looks like" block so the answer can be graded; each paste is recorded as a `box_witness` ledger row and the report gains a section.

The order of work between windows is written down, not remembered: JOB3 §9 fixed the priority ISO-02, ISO-09, ISO-10, ISO-03, ISO-05, ISO-12, ISO-14, ISO-16, then the six P1s; JOB8_9 §6 moved ISO-19 and ISO-24 ahead of ISO-10 after the box showed ISO-19 was the live path; the P0 report §8 shows the order the fixes actually landed (ISO-19, ISO-24, ISO-02, ISO-09, ISO-10, ISO-03+05, ISO-12, ISO-14, ISO-16).

# How a patch proposal is written and proven

A Brother Developer patch proposal is a document, not a diff, until the gate. Its six parts (`docs/BROTHER_DEVELOPER.md` §3 Phase 2; instances in JOB3 §4 and JOB8_9 §3–§4): BEFORE (the current code, file:line); WHY WRONG (which ADR or law it contradicts and what the fixture shows); AFTER (the new code, or its shape); WHY CORRECT; WHAT COULD BREAK (numbered, including deploy-order hazards such as "deploying without `V7_MT5_LOGIN` darkens the arm until it is set — by design"); HOW TESTED, listing unit, failure injection, regression, replay and the box step with human approval. Each proposal ends "NOT applied" and gets a ledger row (`patch_proposed` or `proposal` with `applied: false`).

Proof is by fixtures on a pre-patch copy. The pre-fix file is copied under `tests/audit/<date>_<job>/fixtures/` (`sniper_executor_prepatch_c1618f5.py`, `mt5_bridge_prepatch.py`) so `test_repro_*` keeps reproducing the gap after the fix; the same scenario inverted becomes `test_golden_*` (expected behaviour: refusal, 503, `orders == []`); `test_holds_*` pins that the accepted path is unchanged (e.g. `test_golden_ISO01_right_account_is_byte_identical_on_the_accepted_path`, `test_holds_measured_balance_path_unchanged`). For ISO-01 the deployable form was a script, `brother_sniper_v7/patch_iso01_identity.py`, that patches a temp copy by anchor and aborts unless each anchor matches exactly once; a golden test asserts the script's output equals the repo file, and the script's own backup stamp (`.bak.<yyyymmdd_HHMMSS>`) became the box witness that step 4a ran. A pin test such as `test_golden_fabrication_lines_are_gone` asserts the removed lines are absent from the source.

Failure injection is written as tests too: account swapped between two requests → second refused; `account_info()` None mid-run → 503; provider raise keeps the block (ISO-24); calculator raise rejects the signal (ISO-19); dead terminal at close → loss parked, terminal back → pending applied and cap trips (ISO-12); unreadable witness file = STOP (ISO-16). Replay, where applicable, re-runs real journal rows and tabulates old vs new (ISO-19: 12 rows, 7 widened). Where replay does not apply (identity gates) the ledger row says so: "n/a (identity gate; accepted path byte-identical)".

# Reviewing another window's work

JOB3 §10 shows the pattern for verifying a sibling window: check the claims against the remotes, not the report; re-run its fixtures in scratch worktrees of its branches; confirm `ledger verify` and the row count; dry-run merges with `git merge-tree` and report conflict counts; and read the proposed diff for defects a test would catch (W2-02 found a `GuardResult(...)` constructor missing four required fields). The convergence recipe when two windows branch from different bases: fast-forward `main` to the audit branch, then merge the other window's single commit; on this repo's ledger, keep the chain from `main` and re-append the diverging rows (commits `1e9e1d1`, `a7cc1a1`).

# Test commands

Brother Developer itself (repo root): `python3 -m pytest -q` (pyproject `testpaths = ["tests"]`); expected 15 passed with the sibling checkouts present (8 unit + 7 cross-arm), otherwise 8 passed 1 skipped as NOT RUNNABLE. The cross-arm suite alone: `python3 -m pytest tests/audit/2026-09-04_job3 -q` (needs pytest, flask, loguru). The CLI: `python3 -m brother_developer manifest "<task>"`, `scan`, `test <repo>`, `ledger verify`, `memory list` (the `README.md` lines `python -m tools.brother_developer …` are the pre-split form).
Trading repos, as run for the release report (`docs/P0_RELEASE_REPORT_2026-09-05.md` §2): `brother_sniper_v7` root `python3 -m pytest -q`; `brother-brain-v2` root `python3 -m pytest tests/audit executor_ic_markets/tests -q`; `brother-brain-v2/brain` `python3 -m pytest tests -q`. Job 3 per-arm suites: `python3 -m pytest tests/audit/2026-09-04_job3 -q` in each repo (needs pytest, flask, requests, cryptography, loguru; the v18 route tests also need fastapi and httpx and skip as NOT RUNNABLE without them). Run them only in a sandbox, never on a box checkout (they write logs beside the files).

# Tools the Brother Developer Agent uses

- **pytest** — every verdict that is PASS comes from a pytest summary line; `-p no:cacheprovider` in the test engine keeps repos clean.
- **git** — `status --porcelain`, `rev-parse`, `branch --show-current`, `fetch`, `log --all`, `grep` over remote refs, `merge-tree` dry runs, fast-forward merges, `worktree` (scratch/clean worktrees for verification and regression), `subtree split` (the original extraction).
- **hashlib sha256** — ledger chaining, manifest patch hash and config fingerprint; on Windows `Get-FileHash` before any deploy of a file that was patched in place on the box (JOB3 §4, referencing `docs/SESSION_COORDINATION.md` in the bot repo).
- **ast** — the SYSTEM MAP parses files instead of importing them, so scanning never executes trading code.
- **FakeMT5 / Flask test client / FastAPI + httpx / throw-away Ed25519 key** — the fixture stack for reproducing execution defects without a broker.
- **NSSM** (`nssm status|get|set|restart`), **PowerShell `Select-String`/`Get-Process`/`Expand-Archive`**, **bash `grep`/`curl -s -m 5 …/health`** — the read-only box paste commands; they print secrets as set/EMPTY only and hide NSSM env values unless the key is one of the audited flags.
- **GitHub code search** — used to prove the missing n45mwm audit was nowhere (JOB3 §0).

# The deploy ceremony and the release gate, as the agent hands it over

The Brother Developer Agent never deploys; it writes the gate document. What Shyam runs (P0 report §9; JOB3 §4 "Box" step): set the service environment BEFORE the restart (e.g. `nssm set SniperExecutorV7 AppEnvironmentExtra … V7_MT5_LOGIN=…`), backup → copy/compile → restart → verify in logs/journal, then read the named witness (`/health` fields, a log line, a state file) and paste it. Deploys are coupled where a contract changed on both ends: brain + v18 executor together (ISO-10; deploying the executor alone rejects every envelope `no_account_id`, deploying the brain alone is harmless), v7 bridge + v7 bot together (ISO-03; the bot without `V7_MT5_LOGIN` gets 400 on every order). `GLOBAL_STOP_FILE` must resolve to the same writable path for both Windows services. Only after the witness is read does a memory record move from `watch` to `resolved` and a ledger row record it (ISO-01: rows 11–14, `box_deploy_step` UNKNOWN → `box_verify` PASS on 3 witnesses → `iso01_resolved`).

# The heartbeat work order (an example of cross-window hand-off)

`docs/HEARTBEAT_WORK_ORDER_2026-09-05.md` is a bot-side work order that came back from the platform window (JOB3 §8; ledger rows 16 `platform_reply`, 19 `work_order`): put `account_login` and `trade_mode` (MT5 `account_info().trade_mode`: 0 demo, 1 contest, 2 real) in BOTH heartbeats, append-only, display-only, no risk number. Six edits named by file:line — v7 `sniper_executor.py:102-108` `/health` gains `trade_mode`; `core/ic_markets.py` gains `get_account()` returning `None` on non-200 (the ISO-02 shape); `core/v7_status.py:177-216` `build_heartbeat(..., account_login=None, trade_mode=None)` with keys dropped when None; `bot.py` passes them at the call site; v18 `executor_ic_markets/src/main.py:236-249` `/health` gains `account_login` and `trade_mode` (from the ISO-09 patch's `asserted_login`/`trade_mode`); `brain/src/platform_mirror.py` forwards both keys verbatim. The platform (v5.25.4) already renders `account_login` as MEASURED and otherwise says CONFIGURED LABEL. Status: recorded, not applied; the ISO-09 fix (`db74e85`) implemented the v18 `/health` half.
