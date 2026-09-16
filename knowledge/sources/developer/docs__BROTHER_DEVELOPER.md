---
title: Brother Developer master specification
domain: developer
repo: sabuj14eu/brother-developer
sources: docs/BROTHER_DEVELOPER.md
verified_on: 2026-09-16
commit: 55aba5b
classification: INTERNAL
---

# Brother Developer Agent — the engineering system, organised (v1.0 → Phase 1 built)

Shyam's Master Engineering Specification v1.0 (2026-09-04) is the source.
This file organises it into what exists, what is next, and the bot-session
work, so both windows read one page.

## 1. What it is, in one line
Engineering intelligence for the three live repositories. It observes,
diagnoses, researches, patches a SANDBOX, tests, replays, audits, and
stops at the release gate. It never trades, never routes, never restarts
production, never holds credentials. `Developer Agent ≠ Trading Agent`.

## 2. What exists today (Phase 1, read-only intelligence)
Package `tools/brother_developer/` in this repo, sealed off from `app/`
(a test enforces: no `app` import, no network client). Extract to
`sabuj14eu/brother-developer` with `git subtree split` once the repo exists.

| module | spec § | does |
|---|---|---|
| `manifest.py` | 2.2 | run ID, commit/branch/dirty per repo, python + packages, config fingerprint, patch hash, sources |
| `ledger.py` | 2.3 | append-only JSONL, each row hashes the previous; `verify` finds the first broken row |
| `memory.py` + `memory/` | 20, 21 | structured bug records (schema enforced) and ADR-001…010; `touching(file)` answers "what does memory say before I edit this" |
| `repo_map.py` | 6, 7, 36 | SYSTEM MAP per file (functions, imports, network, database) with a P0–P4 floor by path; `callers_of` for dependency awareness |
| `test_engine.py` | 2.1 | PASS / FAIL / NOT RUNNABLE / UNKNOWN / NOT TESTED; UNKNOWN is never PASS |
| `replay.py` | 24 | the comparison contract: UNCHANGED / CHANGED / UNKNOWN over decision, entry, SL, TP, risk, size, block, execution_intent, freshness, account_routing. IMPROVEMENT vs REGRESSION is never inferred here |

Seeded memory: RETEST persistence (P1), trade twins (P0), scalar offset
(P2). Seeded ADRs: the ten from the spec.

## 3. Phases (spec §44) and their exit gates
1. **Read-only intelligence** — built. Exit: map + tests + ledger + memory run against all three repos.
2. **Sandbox repair** — worktree per task, patch, targeted + regression tests, diff explanation (BEFORE / WHY WRONG / AFTER / WHY CORRECT / WHAT COULD BREAK / HOW TESTED). Never touches a box checkout.
3. **Replay + failure injection** — golden fixtures (spec §25), injected failures (§26), old-vs-new behaviour diff; `BEHAVIOR CHANGED` reported even when tests pass.
4. **Research agent** — external ideas as REFERENCE, each answering the five questions (§22).
5. **Governance** — manifests on every run, ledger on every event, release reports (§28), approval workflow.
6. **Controlled release assistant** — candidate, checklist, post-deploy verification (§27), rollback recommendation; deployment stays gated.

## 4. Laws the agent carries (compressed from §8–§19, §41–§48)
- Diagnose before editing: SYMPTOM · ROOT CAUSE · AFFECTED · WHY TESTS MISSED IT · FIX · RISKS · TEST PLAN.
- Every change gets a risk class; P0 needs unit + integration + failure injection + replay + regression + human approval.
- Coverage is risk-based: 100 % of critical contracts (account isolation, duplicate execution, emergency stop, daily-loss isolation, candle integrity, signature/nonce/expiry).
- `(account_id, signal_id)` is the execution identity; never `signal_id` alone.
- LLMs classify, rank, explain, research, suggest. Deterministic code computes lot, risk %, SL, TP, normalisation, margin, exposure.
- LIMIT invalidated → reject/cancel, never MARKET. Accidental conversion is P0.
- Failure semantics are explicit: PASS · BLOCK · FAIL CLOSED · FAIL SOFT · UNKNOWN · NOT RUNNABLE. Live execution fails CLOSED; UI/research may fail soft.
- Evidence beats a confidence number: list what reproduced, what the trace says, what removing the patch does.
- Secrets are references, never values. Least privilege: READ everywhere, WRITE sandbox, DEPLOY separate, TRADE never.

## 5. Bot-session work (spec §45, Jobs 1–10), with the files it touches
Written for the bot window. Every job is READ + TEST + REPORT first; a
patch is a separate, gated step with its own manifest and ledger rows.

**Job 1 — Dual-MT5 account isolation audit (P0).**
Trace `account_id` from `brain/src/main.py` (dispatch) → `brain/src/signals`
(envelope) → `sniper_executor.py` on Windows → `core/ic_markets.py`
(MT5 login) → `core/v7_status.py` (what reaches the platform). Report every
object that can carry an order without an immutable account identity.
Deliverable: a table `object · file · has account_id · immutable · test`.

**Job 2 — Trace the whole path.** Pine → `/webhook/v18` → council → Ed25519
signed envelope → dispatcher → account routing → executor `:8080`/`:5001` →
MT5 → broker ticket → `/positions` → reporter → platform `trades`. One
correlation set per hop: `trace_id, signal_id, decision_id, account_id,
executor_id, broker_ticket, position_ticket` (§39). Name every hop where one
of them is dropped.

**Job 3 — The ten isolation tests** (write them under `tests/` in the bot
repo, fixtures not live accounts): A cannot execute on B; B cannot execute
on A; same signal + same account = one execution; same signal on two
accounts = two independent executions; global kill blocks both; A daily
loss blocks A only; B stays operational; unknown account = NO EXECUTION;
missing margin = NO EXECUTION; invalid signature = NO EXECUTION.

**Job 4 — Pending-order lifecycle.** In `bot.py` and `core/sl_engine.py`:
create → invalidation rule → cancel. Prove no path turns an invalidated
LIMIT into a MARKET order (ADR-006). grep for market fallbacks.

**Job 5 — Emergency-stop propagation.** Find the kill switch; prove it
reaches both executors and both MT5 logins; prove it cannot be bypassed by
a fail-soft branch (`fail_soft` in `brain/src/main.py`, FAILSOFT_MAX_PER_DAY).

**Job 6 — Daily-loss isolation.** `EquityGuard`: prove the counter is per
account, not per process.

**Job 7 — Duplicate prevention on `(account_id, signal_id)`.** `core/signal_memory.py`
and the platform's `uq_trade_ticket`. Report if any dedupe key is `signal_id` alone.

**Job 8 — Fallback audit.** grep the bot and brain for `or 0`, `default=`,
`except: pass`, `fallback`: balance, price, margin, symbol spec, account,
stale data. Each one is FAIL CLOSED or a finding.

**Job 9 — LLM-computed execution values.** `learning/consult_brain.py`,
`brain/src/compute_sltp.py`, `brain/src/agents`: any lot, SL, TP, size or
price produced by a model call is a P0 finding (ADR-005).

**Job 10 — Golden fixtures** from the memory records: GOLD stale candle,
forming candle, twin ticket, scalar offset, expired signal, invalid
signature, wrong account, missing margin, LIMIT invalidation, daily loss,
global stop. Each fixture states its expected verdict.

## 6. What not to build now (spec §46)
No new indicators, predictors, parameter optimisation on live data, risk
or SL/TP automation, and no replacement of SignalMesh, Brain or Sniper.

## 7. First commands
```
cd /srv/brotherbot && python3 -m tools.brother_developer manifest
cd /srv/brotherbot && python3 -m tools.brother_developer scan
cd /srv/brotherbot && python3 -m tools.brother_developer memory
```
