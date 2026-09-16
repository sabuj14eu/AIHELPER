---
title: Brother Developer Agent — glossary
domain: developer
repo: sabuj14eu/brother-developer
sources: CLAUDE.md, docs/BROTHER_DEVELOPER.md, docs/SESSION_PROTOCOL.md, docs/JOB3_ISOLATION_2026-09-04.md, docs/JOB8_9_TRADING_LOGIC_2026-09-05.md, docs/P0_RELEASE_REPORT_2026-09-05.md, docs/HEARTBEAT_WORK_ORDER_2026-09-05.md, brother_developer/ledger.py, brother_developer/manifest.py, brother_developer/memory.py, brother_developer/replay.py, brother_developer/repo_map.py, brother_developer/test_engine.py
verified_on: 2026-09-16
classification: INTERNAL
---

# Glossary of the Brother Developer Agent

**Brother Developer Agent** — the engineering-intelligence system for Sniper-System, brother-brain-v2 and brother_sniper_v7: it reads, maps, tests, replays, records and proposes, and never trades, routes, deploys or holds credentials. "Developer Agent ≠ Trading Agent" (`docs/BROTHER_DEVELOPER.md` §1).

**Iron rules** — the eight numbered rules in `brother-developer/CLAUDE.md` (least privilege; diagnose before editing; verdict vocabulary; manifest/ledger/memory/fixtures; risk classes; BEHAVIOR CHANGED; secrets as references; boxes read-only).

**ADR (Architecture Decision Record)** — one of the ten seven-line files in `brother_developer/memory/adr/`, each "accepted 2026-09-04 (Shyam, Master Engineering Specification v1.0)"; a patch contradicting any ADR is a P0 finding whatever its tests say.

**Manifest** — the governance record of one run (`brother_developer/manifest.py`): run id `BD-<date>-<time>-<hex>`, per-repo commit/branch/dirty state, python and package versions, config fingerprint, patch hash and research sources; written to `brother_developer/evidence/` and referenced by a ledger row.

**Ledger** — `brother_developer/ledger/ledger.jsonl`, an append-only JSONL file in which every row carries `seq`, `kind`, `ts`, `payload`, `prev` and `hash = sha256(prev + event)`; `ledger verify` finds the first broken row. Every engineering event (test run, finding, proposal, box witness, deploy step, session end) is a row.

**Memory record** — a bug/fix record in `brother_developer/memory/bugs/<id>.json` with the fixed schema id, date, repo, commit, problem, root_cause, solution, tests, risk (P0–P4), status (open/resolved/watch/rejected), files, do_not_reintroduce; `Memory.touching(path)` answers "what does memory say before I touch this file".

**Golden fixture** — a test that pins the correct behaviour after a fix (`test_golden_*`), usually the inverted form of a reproduction; its inputs are fakes (FakeMT5, throw-away keys), never a broker or a live checkout.

**Evidence test / repro test** — a test under `tests/audit/<date>_<job>/` marked `# EVIDENCE — reproduces finding X, keep`; `test_repro_*` PASSES while the finding is reproducible (green means the gap is still there) and keeps running against a pre-patch fixture copy after the fix.

**Holds test** — `test_holds_*`, an invariant that holds today (for example "two equity guards do not share state") or that the accepted path is unchanged by a fix.

**Pre-patch fixture** — a verbatim copy of the pre-fix source kept under `tests/audit/<job>/fixtures/` (e.g. `sniper_executor_prepatch_c1618f5.py`, `mt5_bridge_prepatch.py`) so the reproduction stays re-runnable after the repo file is patched.

**ISO-xx** — a numbered finding from the dual-MT5 isolation audit and the trading-logic review (ISO-01 … ISO-25). ISO-01/02/03/05/09/10/12/14/16/19/24 are P0; ISO-06/07/08/11/13/15/20/21 are P1; ISO-17/18/22/23/25 are P2 (ISO-17 and ISO-25 closed); ISO-04 is folded into ISO-03.

**W2-xx** — findings made by the Job 3 window while verifying Window 2's work (W2-01 branch coordination, W2-02 a defect in a proposed diff).

**Risk class P0–P4** — the change-risk floor assigned to every change (`CLAUDE.md` rule 5; keyword floors in `repo_map.risk_class`). P0 = execution, routing, MT5, orders, stops, lots, SL/TP, identity, dedupe and needs unit + integration + failure injection + replay + regression + human approval; P4 is everything without a keyword match.

**Verdict vocabulary** — PASS / FAIL / NOT RUNNABLE / UNKNOWN / NOT TESTED. UNKNOWN is never PASS; a missing dependency, fixture, contract or identity is NOT RUNNABLE, never a default.

**Failure semantics** — PASS · BLOCK · FAIL CLOSED · FAIL SOFT · UNKNOWN · NOT RUNNABLE, the states a system under audit may answer with; live execution fails CLOSED, UI and research may fail soft (`docs/BROTHER_DEVELOPER.md` §4).

**Replay** — running the same inputs through OLD and NEW code and comparing the fields that decide execution (decision, reason, score, entry, sl, tp, risk, size, block, execution_intent, freshness, account_routing) — `brother_developer/replay.py`; in the P0 queue, pytest fixtures over real journal rows.

**BEHAVIOR CHANGED** — the replay verdict when any compared field differs, reported even when every test passes; IMPROVEMENT vs REGRESSION is a human/evidence verdict never inferred by code (iron rule 6). ISO-19: 7 of 12 real rows widened.

**Failure injection** — tests that break a dependency mid-run (account swap between requests, `account_info()` None, provider raise, calculator raise, dead terminal at close, unreadable witness file) and assert the system refuses rather than defaults.

**Diagnosis format** — SYMPTOM · ROOT CAUSE · AFFECTED · WHY TESTS MISSED IT · FIX · RISKS · TEST PLAN (iron rule 2); a bug report never becomes a diff without it.

**Patch proposal / six-line explanation** — BEFORE / WHY WRONG / AFTER / WHY CORRECT / WHAT COULD BREAK / HOW TESTED, the Phase 2 diff explanation; every proposal ends "NOT applied" until the release gate.

**Release gate** — the human step (Shyam) between `PASS (repo)` and a box verdict: set env, backup → compile → restart → verify in logs/journal, then read the named witness. ADR-010: Brother Developer cannot modify production.

**Coupled deploy** — two services that must be deployed together because a contract changed on both ends (brain + v18 executor for ISO-10; v7 bridge + v7 bot for ISO-03); "a half deploy is worse than none".

**Witness** — an observable artefact that only the intended state can produce: a `/health` field, a log line, a backup file stamp, a marker line in the running file, a state-file key. A fix moves from `watch` to `resolved` only when its named witness is read. "A clock needs two witnesses" is the sibling law behind it.

**Box** — a production machine: Contabo (brain + v7 bot, `/home/shyam/brain-v2`, `/home/shyam/brother_sniper_v7`), the Windows VPS (both executors, both MT5 terminals, NSSM services `SniperExecutorV18` and `SniperExecutorV7`), and the platform host vmi3221804 (`/srv/brotherbot`). All read-only to every AI window.

**Box flags** — the nine isolation-deciding configuration values invisible from the repos (`DRY_RUN`, `MT5_LOGIN`, `MT5_PATH`, `MAGIC_NUMBER`, `GUARDS_DISABLED`, `ADMIN_HALT_TOKEN`, `BRAIN_DISPATCH_MODE`, `EXECUTOR_IC_MARKETS_URL`, `EXECUTOR_URL`), measured by read-only paste commands (`docs/JOB3_ISOLATION_2026-09-04.md` §3, §6, §12).

**Sandbox worktree** — a git worktree per task in which patches are written and tested (Phase 2); scratch/clean worktrees are also used to verify another window's branch and to run regression at a branch head. Never a box checkout.

**Designated branch** — the branch a window creates and pushes empty at minute two (`claude/sniper-isolation-audit-completion-xdj6z4`, `claude/gold-ny-breakout-correctness-ek8562`), then pushes after every job.

**Session protocol** — `docs/SESSION_PROTOCOL.md`: opening, during, push-denied, closing and model-switching rules for every AI window that touches the trading repos.

**Window** — one AI session under the protocol; the bot-side window (v7, brain, brother-developer) and the platform window (Sniper-System) hand work orders to each other through the reports and the ledger.

**Dual-MT5 isolation** — the property that the v18 arm (MT5 login 52901228, executor :8080) and the v7 arm (MT5 login 52834417, bridge :5001) can never execute, close, modify or count losses on each other's account, and that one stop halts both; Jobs 1 and 3 and the ten invariants.

**The ten invariants** — Job 3's isolation tests: A cannot execute on B; B cannot execute on A; same signal + same account = one execution; same signal on two accounts = two executions; global kill blocks both; A daily loss blocks A only; B stays operational; unknown account = NO EXECUTION; missing margin = NO EXECUTION; invalid signature = NO EXECUTION.

**Global stop / GLOBAL_STOP_FILE** — the shared witness file introduced by ISO-16 (default `C:\brotherbot\GLOBAL_STOP`): present = STOP, unreadable = STOP, read by both executors before every new order; engaged by either arm's admin halt; never blocks a close.

**Asserted login / identity_ok** — the pattern from ISO-01 and ISO-09: the expected MT5 login is an environment input, compared against `account_info().login` on attach and on every request/probe; mismatch or missing value refuses (503 / shutdown), never a default.

**Execution identity** — `(account_id, signal_id)`, never `signal_id` alone (ADR-004); the still-open ISO-06/08/13 are dedupe keys that omit the account.

**Fail closed / fail open** — a gate that refuses when its input is missing (closed) versus one that proceeds on a default (open); `or 0`, `default=`, `except: pass` and `fallback` sites are audited for this (Job 8).

**Heartbeat work order** — the platform's request that both arms' heartbeats carry `account_login` and MT5 `trade_mode` (0 demo, 1 contest, 2 real) so the desk can show MEASURED instead of CONFIGURED LABEL (`docs/HEARTBEAT_WORK_ORDER_2026-09-05.md`).

**Accepted risk** — a risk-widening behaviour kept by explicit human decision and recorded as such (the brain's fail-soft path, `FAILSOFT_MAX_PER_DAY`), never silently passed and never re-litigated by the agent.

**GO / NO-GO lanes** — DUAL-SHADOW (both arms, no orders), DUAL-DEMO (both demo accounts), REAL MONEY (tiny test); as of 2026-09-05: GO, GO after coupled deploys, NO-GO.

**SYSTEM MAP** — the static per-file scan (`repo_map.py`): functions, classes, imports, network and database use, risk-class floor; `callers_of` for dependency awareness.

**Evidence Law** — n<20 is luck, ~100 to judge (from the trading constitutions); applied to the ISO-19 soak requirement (n≥20 shadow rows minimum).

**Convergence** — bringing two windows' branches onto `main` with zero conflicts (fast-forward main to the audit branch, merge the other window's commit) while keeping the ledger chain from main and re-appending diverging rows.
