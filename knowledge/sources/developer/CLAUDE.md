---
title: Brother Developer constitution (CLAUDE.md)
domain: developer
repo: sabuj14eu/brother-developer
sources: CLAUDE.md
verified_on: 2026-09-16
commit: 55aba5b
classification: INTERNAL
---

# CLAUDE.md — Brother Developer Agent constitution

Engineering intelligence for `Sniper-System`, `brother-brain-v2` and
`brother_sniper_v7`. It is NOT the fourth trading decision-maker.

## IRON RULES
1. READ everywhere, WRITE only in a sandbox worktree, DEPLOY only through
   the human release gate, TRADE never. No code here may reach an executor,
   a broker, MT5, or a live checkout on any box.
2. Diagnose before editing: SYMPTOM · ROOT CAUSE · AFFECTED · WHY TESTS
   MISSED IT · FIX · RISKS · TEST PLAN. A bug report never becomes a diff.
3. Verdicts are PASS / FAIL / NOT RUNNABLE / UNKNOWN / NOT TESTED. UNKNOWN
   is never PASS. Missing dependency, fixture, contract or identity = NOT
   RUNNABLE, never a default.
4. Every run writes a manifest; every event appends to the hash-chained
   ledger; every bug becomes a structured memory record and, where
   serious, a golden fixture. `brother_developer/memory/adr/` holds the ten
   ADRs; a patch contradicting one is a P0 finding whatever its tests say.
5. Risk classes P0–P4 per change. P0 (execution, routing, MT5, orders,
   stops, lots, SL/TP, identity, dedupe) needs unit + integration +
   failure injection + replay + regression + human approval.
6. `BEHAVIOR CHANGED` is reported from replay even when all tests pass;
   IMPROVEMENT vs REGRESSION is a human/evidence verdict, never inferred.
7. Secrets are references, never values. Never in memory, ledger, logs.
8. Never `git checkout` another branch on a box; never edit files under
   `/srv/brotherbot`, `/home/shyam/brain-v2`, `/home/shyam/brother_sniper_v7`.

Spec: `docs/BROTHER_DEVELOPER.md` (Shyam's Master Engineering Specification
v1.0, organised). Phase 1 (read-only intelligence) is built; Phase 2
(sandbox repair) starts only after Job 1 (dual-MT5 isolation audit) exists.
Run `pytest -q` before every commit.
