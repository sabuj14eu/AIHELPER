---
title: Brother Developer README
domain: developer
repo: sabuj14eu/brother-developer
sources: README.md
verified_on: 2026-09-16
commit: 55aba5b
classification: INTERNAL
---

# Brother Developer Agent — Phase 1 scaffold (v0.1.0)

Engineering intelligence for the three live repositories. NOT a trading
agent: read-only, sandbox-only, gated. Spec: `docs/BROTHER_DEVELOPER.md`.

```
python -m tools.brother_developer manifest            # governance manifest (commits, dirty, versions, hashes)
python -m tools.brother_developer scan                # SYSTEM MAP of the repos + risk class per file
python -m tools.brother_developer test Sniper-System  # PASS / FAIL / NOT RUNNABLE / UNKNOWN, never a fake PASS
python -m tools.brother_developer ledger verify       # hash chain intact?
python -m tools.brother_developer memory list         # bugs / fixes / ADRs, structured
```

Extract to its own repo (Shyam creates `sabuj14eu/brother-developer` first):
```
cd /srv/brotherbot && git subtree split --prefix=tools/brother_developer -b brother-developer-split
```
Protocol for every AI window: `docs/SESSION_PROTOCOL.md`.
Rules: no import of `app`, no network client, no write outside `evidence/`
and `ledger/`, no credentials. A test enforces the first three.
