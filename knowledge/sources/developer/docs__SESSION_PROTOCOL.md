---
title: Brother Developer session protocol
domain: developer
repo: sabuj14eu/brother-developer
sources: docs/SESSION_PROTOCOL.md
verified_on: 2026-09-16
commit: 55aba5b
classification: INTERNAL
---

# Session protocol — every AI window that touches the trading repos

Written after 2026-09-04: an audit session produced 661 lines of P0
findings, ran a test suite that reproduced a misrouted order and a
fabricated balance, then DELETED that suite and could not push. The
findings existed in one ephemeral container. Nothing was lost, by luck.
These rules make luck unnecessary.

## Opening (first 5 minutes, before any reading)
1. `git -C <repo> status --porcelain` in every repo — must be empty. Paste it.
2. Create the designated branch and push it EMPTY at once:
   `git checkout -b <branch> && git push -u origin <branch>`.
   A push denial shows up here, at minute two, not after the work.
3. `python3 -m brother_developer manifest "<task>"` — the run is on record.

## During
4. **Push after every job.** One commit per job (`Job 3 — …`), pushed
   immediately. Work that exists only in a container does not exist.
5. **Never delete evidence.** Tests written to reproduce a finding live
   under `tests/audit/<date>_<job>/` in the repo they test, marked
   `# EVIDENCE — reproduces finding X, keep`. A reproduction nobody can
   re-run is a story.
6. **Never edit a live checkout.** `/srv/brotherbot`, `/home/shyam/brain-v2`,
   `/home/shyam/brother_sniper_v7` are read-only to every AI window.
   Never `git checkout` another branch on a box.
7. **Verdicts:** PASS / FAIL / NOT RUNNABLE / UNKNOWN. UNKNOWN is never PASS.
   Every claim names file and line.

## If push is denied
8. Do not route around it. Print the full file content in chat, or offer
   it as an attachment, and say so. The human commits it. Then stop.

## Closing (last 5 minutes)
9. `git status --porcelain` in every repo (empty), `git log origin/<branch> -1`
   (the last job's commit is on the remote), ledger append `session_end`.
10. Handoff in the report: what is UNKNOWN and why, what the next window
    must not repeat.

## Model switching
Never switch the model on a job mid-flight. Finish, push, close the
window, open the next one with this protocol. Two windows on one box
checkout is the fault the coordination file exists for.
