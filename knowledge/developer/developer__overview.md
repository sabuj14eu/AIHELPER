---
title: Brother Developer Agent — overview
domain: developer
repo: sabuj14eu/brother-developer
sources: CLAUDE.md, README.md, docs/BROTHER_DEVELOPER.md, docs/SESSION_PROTOCOL.md, docs/JOB3_ISOLATION_2026-09-04.md, docs/P0_RELEASE_REPORT_2026-09-05.md, brother_developer/__init__.py, brother_developer/__main__.py, tests/audit/2026-09-04_job3/README.md, pyproject.toml, .gitignore
verified_on: 2026-09-16
classification: INTERNAL
---

# Brother Developer Agent — what it is

The Brother Developer Agent (repo `sabuj14eu/brother-developer`, package `brother_developer`, version 0.1.0 per `brother_developer/__init__.py`) is the engineering-intelligence layer for Shyam's three live trading repositories: `Sniper-System` (the SignalMesh platform), `brother-brain-v2` (the v18 brain and the v18 Windows executor) and `brother_sniper_v7` (the v7 bot and its Windows bridge). Its one-line definition, from `docs/BROTHER_DEVELOPER.md` §1: it observes, diagnoses, researches, patches a SANDBOX, tests, replays, audits, and stops at the release gate. It never trades, never routes, never restarts production, never holds credentials. The spec states the identity rule as `Developer Agent ≠ Trading Agent`.

The Brother Developer Agent is explicitly NOT the fourth trading decision-maker (`CLAUDE.md`, first paragraph). The three trading authorities are fixed by ADR-001 to ADR-003 in `brother_developer/memory/adr/`: SignalMesh is the observer and read-model authority and never dispatches; Brother Brain v2 is the decision authority, not the broker execution authority; executors are the execution authority and nothing bypasses the council. The Developer Agent sits outside that chain and only reads, tests, records and proposes.

# Where the Brother Developer Agent came from

The Brother Developer Agent began as `tools/brother_developer/` inside the Sniper-System repository and was split out with history on 2026-09-04 (commit `af42bf3`, "Brother Developer Agent v0.1.0 — Phase 1 (read-only intelligence), split from Sniper-System with history"; the scaffold commit is `469d0ee`). The `README.md` still carries the pre-split instructions (`python -m tools.brother_developer ...` and a `git subtree split --prefix=tools/brother_developer` command run from `/srv/brotherbot`); after the split the package is invoked as `python3 -m brother_developer` from this repo's root (`docs/SESSION_PROTOCOL.md` step 3). The spec `docs/BROTHER_DEVELOPER.md` is Shyam's Master Engineering Specification v1.0 (2026-09-04), organised into what exists, what is next, and the bot-session jobs.

# Brother Developer phases and gates

`docs/BROTHER_DEVELOPER.md` §3 lists six phases (spec §44), each with an exit gate:

1. Read-only intelligence — BUILT. Exit gate: map + tests + ledger + memory run against all three repos.
2. Sandbox repair — a git worktree per task, patch, targeted plus regression tests, and a diff explanation in six parts (BEFORE / WHY WRONG / AFTER / WHY CORRECT / WHAT COULD BREAK / HOW TESTED). Never touches a box checkout.
3. Replay + failure injection — golden fixtures (spec §25), injected failures (§26), old-vs-new behaviour diff; `BEHAVIOR CHANGED` reported even when tests pass.
4. Research agent — external ideas as REFERENCE, each answering the spec's five questions (§22).
5. Governance — manifests on every run, ledger on every event, release reports (§28), approval workflow.
6. Controlled release assistant — candidate, checklist, post-deploy verification (§27), rollback recommendation; deployment stays gated.

`CLAUDE.md` states the gate between phases: "Phase 1 (read-only intelligence) is built; Phase 2 (sandbox repair) starts only after Job 1 (dual-MT5 isolation audit) exists." Job 1 in the spec (§5) is the `account_id` trace from `brain/src/main.py` through the envelope, the Windows executor and `core/ic_markets.py` to `core/v7_status.py`, with the deliverable table `object · file · has account_id · immutable · test`. `docs/JOB3_ISOLATION_2026-09-04.md` §5 records that Jobs 1, 2 and 4–10 "were not attempted beyond what the Job 3 fixture reached". The later `docs/P0_RELEASE_REPORT_2026-09-05.md` §5 does publish an account identity chain across both arms, and ten P0 fixes were committed to the trading repos on 2026-09-05, so the repo's phase language and its actual work are not perfectly aligned; see developer__open_items.md.

# What the Brother Developer Agent may read, write and deploy

Least privilege is the first iron rule in `CLAUDE.md`: READ everywhere, WRITE only in a sandbox worktree, DEPLOY only through the human release gate, TRADE never. No code in the repo may reach an executor, a broker, MT5, or a live checkout on any box. The live checkouts named as read-only to every AI window are `/srv/brotherbot` (the platform), `/home/shyam/brain-v2` (the brain) and `/home/shyam/brother_sniper_v7` (the v7 bot), per `CLAUDE.md` rule 8 and `docs/SESSION_PROTOCOL.md` step 6. Never `git checkout` another branch on a box.

What the Brother Developer Agent writes, in practice (from `README.md`, `docs/SESSION_PROTOCOL.md` and the reports): its own `brother_developer/evidence/` (run manifests; the directory is gitignored except for the one committed manifest `BD-20260904-212928-9191f2.json`), `brother_developer/ledger/ledger.jsonl` (hash-chained), `brother_developer/memory/bugs/*.json` and `memory/adr/*.md`, the report docs under `docs/`, and — in the trading repos — evidence tests under `tests/audit/<date>_<job>/` plus proposed fixes on a designated branch that is pushed early and never applied to a box by the window. `README.md` says a test enforces that the package never imports `app`, never uses a network client, and (as a rule) never writes outside `evidence/` and `ledger/`; `tests/test_brother_developer.py::test_the_agent_is_sealed_off_from_trading_code` checks the import and network-client halves by scanning every `.py` in the package for `from app`, `import app`, `import httpx`, `import requests`, `import MetaTrader5` and `import socket`.

Deployment is always a human act. ADR-010: "Brother Developer cannot modify production; every change passes the release gate." In the P0 queue, every fix is `PASS (repo) · UNKNOWN (box)` until Shyam deploys it and a named witness (a `/health` field, a log line, a state file) is read (`docs/P0_RELEASE_REPORT_2026-09-05.md` §1, §9).

# How the Brother Developer Agent relates to the three trading repos

The workspace layout is one directory holding the four repos side by side. `brother_developer/__main__.py` resolves `ROOT = HERE.parents[1]` (the directory containing `brother-developer/`), and `manifest.REPOS` is the tuple `("Sniper-System", "brother-brain-v2", "brother_sniper_v7")`. The cross-arm evidence tests in `tests/audit/2026-09-04_job3/test_cross_arm_isolation.py` load `../brother_sniper_v7` and `../brother-brain-v2` by path and skip as NOT RUNNABLE when either is absent (`tests/audit/2026-09-04_job3/README.md`).

The two execution arms the Brother Developer Agent audits, as measured in `docs/JOB3_ISOLATION_2026-09-04.md` §3, §6 and §12: the v18 arm is `brother-brain-v2` — the council on the Contabo box dispatches Ed25519-signed envelopes to the Windows executor `executor_ic_markets` on port 8080 (NSSM service `SniperExecutorV18`, MT5 login 52901228, its own terminal at `C:\MT5_v18\terminal64.exe`); the v7 arm is `brother_sniper_v7` — `bot.py` on Contabo posts to the Windows bridge `sniper_executor.py` on port 5001 (NSSM service `SniperExecutorV7`, MT5 login 52834417, terminal `C:\Program Files\MetaTrader 5 IC Markets EU\terminal64.exe`). `Sniper-System` is the platform on the box `vmi3221804` (`/srv/brotherbot`), which renders both arms' heartbeats; it received no pushes from the bot-side windows (JOB3 §5, commit `a8c2fed`).

Two AI windows work under the agent: the bot-side window (v7, brain, brother-developer, Sniper-System read-only) and the platform window. `docs/JOB3_ISOLATION_2026-09-04.md` §8 records the platform's reply (v5.25.4) and the work order it handed back to the bot side (`account_login` + `trade_mode` in both heartbeats, `docs/HEARTBEAT_WORK_ORDER_2026-09-05.md`). §9 of the same report carries the paste-ready opening prompt for a bot-side window.

# What the Brother Developer Agent does not build

`docs/BROTHER_DEVELOPER.md` §6 (spec §46): no new indicators, no predictors, no parameter optimisation on live data, no risk or SL/TP automation, and no replacement of SignalMesh, Brain or Sniper. `docs/JOB3_ISOLATION_2026-09-04.md` §9 adds the working priority: "no new trading intelligence while any of these [P0s] is open".

# State of the Brother Developer Agent at the last commit (2026-09-05)

`docs/P0_RELEASE_REPORT_2026-09-05.md` (commit `55aba5b`, ledger row 39 `p0_queue_complete`): 11 P0 findings in total; ISO-01 resolved on the box; ten fixed in the trading repos (ISO-19, ISO-24, ISO-02, ISO-09, ISO-10, ISO-03, ISO-05, ISO-12, ISO-14, ISO-16) with memory status `watch` until the release gate deploys them; 0 open P0. Regression across the four suites: 296 passed, 0 failed. Lane verdicts: DUAL-SHADOW GO; DUAL-DEMO GO after the coupled deploys in §9 and after each `/health` witness is read; REAL MONEY (tiny test) NO-GO. Branch everywhere: `claude/sniper-isolation-audit-completion-xdj6z4`, fast-forward onto `main`.

The four memory-record statuses are `open`, `resolved`, `watch`, `rejected` (`brother_developer/memory.py`). As of the last commit: 4 records `resolved` (three seeded platform bugs plus ISO-01) and 10 `watch`.
