---
title: Brother Developer Agent — iron rules, ADRs, verdicts and risk classes
domain: developer
repo: sabuj14eu/brother-developer
sources: CLAUDE.md, docs/BROTHER_DEVELOPER.md, docs/SESSION_PROTOCOL.md, brother_developer/memory/adr/ADR-001.md … ADR-010.md, brother_developer/test_engine.py, brother_developer/repo_map.py, brother_developer/replay.py, brother_developer/memory.py, docs/P0_RELEASE_REPORT_2026-09-05.md, docs/JOB3_ISOLATION_2026-09-04.md, docs/JOB8_9_TRADING_LOGIC_2026-09-05.md
verified_on: 2026-09-16
classification: INTERNAL
---

# The eight iron rules of the Brother Developer Agent

The eight iron rules live in `CLAUDE.md` of `brother-developer`. They are the constitution every AI window under the agent reads first.

1. **Least privilege.** READ everywhere, WRITE only in a sandbox worktree, DEPLOY only through the human release gate, TRADE never. No code here may reach an executor, a broker, MT5, or a live checkout on any box.
2. **Diagnose before editing.** SYMPTOM · ROOT CAUSE · AFFECTED · WHY TESTS MISSED IT · FIX · RISKS · TEST PLAN. A bug report never becomes a diff.
3. **Verdict vocabulary.** Verdicts are PASS / FAIL / NOT RUNNABLE / UNKNOWN / NOT TESTED. UNKNOWN is never PASS. Missing dependency, fixture, contract or identity = NOT RUNNABLE, never a default.
4. **Governance artefacts.** Every run writes a manifest; every event appends to the hash-chained ledger; every bug becomes a structured memory record and, where serious, a golden fixture. `brother_developer/memory/adr/` holds the ten ADRs; a patch contradicting one is a P0 finding whatever its tests say.
5. **Risk classes.** P0–P4 per change. P0 (execution, routing, MT5, orders, stops, lots, SL/TP, identity, dedupe) needs unit + integration + failure injection + replay + regression + human approval.
6. **BEHAVIOR CHANGED.** It is reported from replay even when all tests pass; IMPROVEMENT vs REGRESSION is a human/evidence verdict, never inferred.
7. **Secrets are references, never values.** Never in memory, ledger, logs.
8. **Boxes are read-only.** Never `git checkout` another branch on a box; never edit files under `/srv/brotherbot`, `/home/shyam/brain-v2`, `/home/shyam/brother_sniper_v7`.

`CLAUDE.md` closes with: run `pytest -q` before every commit.

# The ten ADRs of the Brother Developer Agent

All ten ADRs in `brother_developer/memory/adr/ADR-001.md` … `ADR-010.md` share one status line — "accepted 2026-09-04 (Shyam, Master Engineering Specification v1.0)" — and one consequence: "Any patch that contradicts this is a review finding of class P0, whatever its tests say." The ADR files carry only Status, Decision and Consequence; they contain no separate rationale section. Where a rationale exists in the repo it comes from the finding that exercised the ADR, cited below.

**ADR-001 — SignalMesh is the observer and read-model authority; it never dispatches.** Exercised by the platform-side constitution (Sniper-System `CLAUDE.md` iron rule 1) and by the sealed-off test in `tests/test_brother_developer.py`. Rationale in this repo: UNKNOWN beyond the decision text.

**ADR-002 — Brother Brain v2 is the decision authority, not the broker execution authority.** Rationale in this repo: UNKNOWN beyond the decision text; the identity chain in `docs/P0_RELEASE_REPORT_2026-09-05.md` §5 shows the brain producing an opportunity and the dispatcher, not the brain, binding the account.

**ADR-003 — Executors are the execution authority; nothing bypasses the council.** `docs/JOB8_9_TRADING_LOGIC_2026-09-05.md` §2 records a tension: the brain's fail-soft path (`brain/src/main.py:433-465`, A/A+ approved from Pine on agent failure, `FAILSOFT_MAX_PER_DAY`=2) bypasses the council by an explicit `.env` decision, recorded as accepted risk with "tension with ADR-003 for the real-money gate".

**ADR-004 — Account identity is immutable on every execution object; uniqueness is (account_id, signal_id).** The most-exercised ADR: ISO-01 (v7 bridge attaches by path), ISO-03 (`/execute` has no account field, no magic), ISO-05 (close/modify any ticket), ISO-09 (v18 bridge never asserts login), ISO-10 (signed envelope has no account) all cite it (`docs/P0_RELEASE_REPORT_2026-09-05.md` §1). The still-open P1s ISO-06/07/08/13 are dedupe keys and state objects that omit the account (`tests/audit/2026-09-04_job3/test_cross_arm_isolation.py::test_repro_ISO08_ISO13_dedupe_keys_on_both_arms_omit_the_account`).

**ADR-005 — An LLM never calculates lot size, risk %, SL/TP, margin, tick normalisation or exposure.** Exercised by ISO-19 (the council's AI-on path dispatched the ExecutorPrep LLM's own entry/SL/TP/risk_pct/order_type) and ISO-24 (a DeepSeek/Gemini vote could flip a v7 rule block). The spec's phrasing (`docs/BROTHER_DEVELOPER.md` §4): LLMs classify, rank, explain, research, suggest; deterministic code computes lot, risk %, SL, TP, normalisation, margin, exposure. The ISO-19 memory record adds the rule "models choose bounded parameters, code computes prices and sizes"; ISO-24 adds "models may only remove risk (veto), never add it".

**ADR-006 — A pending LIMIT invalidated is rejected or cancelled; it never converts to MARKET automatically.** Exercised by ISO-14: `mt5_bridge.py:377-386` had a `[PEND->MKT]` branch converting at drift ≤ 30% of risk; the memory record says the finding "contradicts ADR-006 whatever its tests say" and the do-not-reintroduce line is "any automatic pending->market conversion, at any drift tolerance". The spec §4 states: accidental conversion is P0.

**ADR-007 — Closed candles only enter research, state and evidence; a forming bar may display, never count.** Exercised in this repo only by the seeded platform memory records (RETEST persistence, `BUG-2026-09-03-retest-persistence.json`, which re-evaluates state on the newest CLOSED bar). Rationale beyond that: UNKNOWN in this repo (the Sniper-System constitution's Quant Lab and Freshness laws carry it).

**ADR-008 — A global emergency stop stops every account.** Exercised by ISO-16: before the fix no object stopped both accounts (v18 `/admin/halt` was a per-process state file; v7 had no halt route); the memory record states "ADR-008 has no implementation". Fixed by one shared witness file, `GLOBAL_STOP_FILE`.

**ADR-009 — Account-local daily loss isolates one account; another account stays independently operational.** Exercised by ISO-12 (a loss seen while the v18 balance was unreadable was dropped, so the daily cap could not trip — "UNKNOWN became 'no loss'") and ISO-02 (v7 fabricated a balance and let it reach the equity guard). Both records cite ADR-009 together with the platform's Freshness Law.

**ADR-010 — Brother Developer cannot modify production; every change passes the release gate.** Exercised on every P0 row of `docs/P0_RELEASE_REPORT_2026-09-05.md`: the verdict column is `PASS (repo) · UNKNOWN (box)` and the "Not done" line reads "nothing deployed by this window (rule 1, deploy only through the human gate)".

# The verdict vocabulary and why UNKNOWN is never PASS

The Brother Developer Agent's verdicts are PASS / FAIL / NOT RUNNABLE / UNKNOWN / NOT TESTED (`CLAUDE.md` rule 3; `brother_developer/test_engine.py` `VERDICTS`). `docs/SESSION_PROTOCOL.md` step 7 lists four (it omits NOT TESTED) — a small inconsistency between the two documents; the code and `CLAUDE.md` carry five.

The implementation in `brother_developer/test_engine.py::classify(returncode, output)`: no exit code (timeout or killed) → UNKNOWN; output containing `No module named`, `ModuleNotFoundError`, `no tests ran`, `ERROR: file or directory not found` or `ImportError` → NOT RUNNABLE ("missing dependency, fixture or path"); exit 0 with an `N passed` summary → PASS with the count; a `failed`/`error` count or non-zero exit → FAIL with counts; exit 0 but no pytest summary → UNKNOWN. `run(repo)` returns NOT TESTED when the repo has no `tests/` directory. `tests/test_brother_developer.py::test_verdicts_never_invent_pass` pins that `classify(0, "")` is UNKNOWN, not PASS.

Why UNKNOWN is never PASS, in the repo's own words: "Missing dependency, fixture, contract or identity = NOT RUNNABLE, never a default" (`CLAUDE.md`). The cross-arm suite skips with the message "NOT RUNNABLE: sibling checkouts ... not found" rather than passing vacuously; `docs/JOB3_ISOLATION_2026-09-04.md` §13 records "brother-developer 13 passed with sibling checkouts (8 passed 1 skipped without them: NOT RUNNABLE, never PASS)". The same principle governs box facts: every one of the nine isolation flags was UNKNOWN until Shyam pasted it (§3, §6, §12), and a fix is `UNKNOWN (box)` until deployed and witnessed.

The spec (`docs/BROTHER_DEVELOPER.md` §4) adds explicit failure semantics for the systems under audit: PASS · BLOCK · FAIL CLOSED · FAIL SOFT · UNKNOWN · NOT RUNNABLE. Live execution fails CLOSED; UI and research may fail soft. The Job 8 fallback audit (`docs/JOB8_9_TRADING_LOGIC_2026-09-05.md` §2) grades every `or 0`, `except: pass`, `fallback` and `default=` site as FAIL CLOSED (PASS) or a finding.

# Risk classes P0–P4

`CLAUDE.md` rule 5 assigns a risk class to every change. P0 covers execution, routing, MT5, orders, stops, lots, SL/TP, identity and dedupe, and requires unit + integration + failure injection + replay + regression + human approval. `docs/BROTHER_DEVELOPER.md` §4 adds that coverage is risk-based: 100% of critical contracts — account isolation, duplicate execution, emergency stop, daily-loss isolation, candle integrity, signature/nonce/expiry.

`brother_developer/repo_map.py::risk_class(path)` gives a static floor by path keyword (the docstring: "a class here is a floor for review, never a verdict — P0 paths are named by keyword, the reviewer confirms"):
- P0 keywords: execut, order, mt5, position, emergency, daily_loss, margin, lot, sl_engine, sltp, dispatch, sign, nonce, ticket, account.
- P1 keywords: signal, regime, score, evidence, entry, news, fresh, structure, session_state, planner, autonomous, desk, council, risk.
- P2 keywords: candle, reporter, ingest, webhook, timestamp, dedupe, candle_audit.
- P3 keywords: template, chart, dashboard, radar, router, ui.
- P4: everything else.

`brother_developer/memory.py` enforces `RISK = ("P0", "P1", "P2", "P3", "P4")` on every memory record. How the reports used the classes: P0 findings each got a memory record and (mostly) a golden fixture; P1 findings (ISO-06/07/08/11/13/15/20/21) got test docstrings but no memory record and were left open "by decision (queue order)"; P2 findings (ISO-18 doc drift, ISO-22 orphan adoption, ISO-23 magic in payload, ISO-25 threshold default, the `USE_DEMO` label) are recorded in the reports only; the one P3 in this repo (the `__main__.py` ROOT bug) was fixed with a pinning test. The ISO-01 patch proposal shows what a P0 test plan looks like in practice: unit, failure injection and regression are covered by fixtures; integration on the box and human approval are the release gate (`docs/JOB3_ISOLATION_2026-09-04.md` §4 "HOW TESTED", §7).

# The BEHAVIOR CHANGED rule

`brother_developer/replay.py` fixes the comparison contract now so fixtures can be written against it (the runners are Phase 3). `FIELDS = ("decision", "reason", "score", "entry", "sl", "tp", "risk", "size", "block", "execution_intent", "freshness", "account_routing")`. `compare(old, new)` returns UNKNOWN when either side produced no output, UNCHANGED when no field differs, and otherwise CHANGED with the note "BEHAVIOR CHANGED — even if every test passes; classify IMPROVEMENT/REGRESSION from replay evidence, not from here". `tests/test_brother_developer.py::test_replay_compare_reports_behavior_change_not_improvement` pins those three outcomes.

The rule was applied for real on ISO-19: `test_replay_ISO19_twelve_real_rows_behavior_changed_report` re-ran 12 real journal rows shipped with `compute_sltp` through the new `build_execution_payload`; 7 of 12 stops widened to the symbol noise floor. `docs/P0_RELEASE_REPORT_2026-09-05.md` §3 records the verdict as BEHAVIOR CHANGED (rule 6) and says IMPROVEMENT vs REGRESSION "needs dual-shadow soak, n≥20 minimum" — one of the five reasons real money is NO-GO (§10). For ISO-24 the BEHAVIOR CHANGED size was measured on the box: 0 `AI OVERRIDE` lines in the retained v7 logs (ledger row 30).

# Laws the spec compresses into the agent

`docs/BROTHER_DEVELOPER.md` §4 (from spec §8–§19 and §41–§48) carries the working laws that the iron rules summarise: diagnose before editing; every change has a risk class; coverage is risk-based; `(account_id, signal_id)` is the execution identity, never `signal_id` alone; LLMs suggest and deterministic code computes; LIMIT invalidated → reject/cancel, never MARKET; explicit failure semantics; evidence beats a confidence number ("list what reproduced, what the trace says, what removing the patch does"); secrets are references; least privilege.

`docs/SESSION_PROTOCOL.md` adds the procedural laws learned on 2026-09-04: push the designated branch empty at minute two, push after every job, never delete evidence, never edit a live checkout, every claim names file and line, never switch the model mid-job, and if push is denied print the file in chat and stop rather than route around it.

The bot-side reports also adopt laws from the sibling constitutions when they decide a finding: the Evidence Law (n<20 is luck, ~100 to judge; `docs/P0_RELEASE_REPORT_2026-09-05.md` §10), the Freshness Law (STALE/UNKNOWN never becomes a valid positive; ISO-12 and ISO-02), "never widen risk silently" (every fix reports `risk_number_changed: false` in the ledger), and "one word carrying two facts is the fault to hunt" (`EYE_MODEL=shadow` names the second model's role, not the first's — `docs/JOB8_9_TRADING_LOGIC_2026-09-05.md` §6).
