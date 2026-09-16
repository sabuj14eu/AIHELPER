---
title: The working laws shared by every project
domain: brother
repo: sabuj14eu/AIHELPER
sources: Sniper-System/CLAUDE.md, Sniper-System/docs/HANDOFF_PLATFORM_SESSION.md, brother_sniper_v7/CLAUDE.md, brother-brain-v2/CLAUDE.md, brother-developer/CLAUDE.md, Accounting-/CLAUDE.md
verified_on: 2026-09-16
classification: INTERNAL
---

# Laws that every repository shares

These rules appear, in one wording or another, in every constitution Shyam
has written. They were paid for in real losses and real bugs, and Brother
applies them everywhere, including to its own answers.

# Findings first, then code

Every repository says it the same way: findings first, then code; small
verified diffs over rewrites. A change starts with what was found (the
symptom, the root cause, the affected code, why the tests missed it) and only
then becomes a diff. A bug report never becomes a diff directly. In the
trading repositories the journal (logs/decisions.jsonl) is grepped before a
claim is believed, because the system's history is measured, not remembered.

# The evidence law

No live logic changes without data. A new rule passes the backtest harness
(train/validate split; the VALIDATE column decides) or accumulates journal
evidence. n under 20 is luck. Judge nothing before about 100 trades. One organ
changes per week. In the platform this became the Quant Lab Law: the
objective is a statistically robust, reproducible, out-of-sample edge, with
"NO ROBUST STRATEGY" as a first-class successful outcome; search touches only
the first 80 percent of a dataset and the final 20 percent is a holdout spent
once; raw return never ranks; selection bias is disclosed on every report.

# Two independent populations agreeing is the standard

The platform's Evidence Authority rule (locked 2026-08-20): paper lanes are a
hypothesis generator, never a gate authority. A lane statistic may propose a
rule change; only v7's own filled trades may justify one. A split sample is a
smaller sample: cut a bucketed result by side and by with-trend versus
against-bias, check n in each cell, and when the deciding cell is under the
evidence floor the verdict is CANNOT SEPARATE.

# Freshness: stale data must never become a valid positive signal

The Freshness Law (locked 2026-08-11): a stale bias is invalid and unused, not
neutral. Missing news is UNKNOWN, not low risk, and UNKNOWN fails a "news at
or below X" condition by default. A stale plan is not ready, a stale server is
not healthy, a stale signal is not a current opportunity, UNKNOWN is not any
direction. Every displayed number needs source, timestamp, freshness,
authority, meaning and expiry.

# A clock needs two witnesses

Locked 2026-08-21 after the incident of 2026-08-20, when the reporter read one
tick during the metals rollover break and inferred the broker offset from it,
stamping every bar an hour late for 25 minutes. Timestamps are inferred from
at least two fresh, independent witnesses, one of which trades around the
clock, or not inferred at all. A wrong clock is corrupted data, not degraded
data, because the candle key is (symbol, timeframe, timestamp) and a shifted
bar creates a parallel series instead of overwriting the wrong one. A push is
not delivered until the receiver says what it stored. A scalar offset cannot
convert a multi-year series because the broker's seasonal hour is inside the
data. Internal consistency is not correctness: a uniformly wrong series passes
every self-consistency test.

# Health endpoints lie; only tickets tell the truth

An executor served HTTP 200 for six days while placing nothing. Since then,
status displays are driven by reported heartbeats with staleness windows,
never by "the endpoint returned 200". Bot-guards on the dashboard exist for
this reason. The same rule appears in the accounting application as "a
calculation is not a filing": nothing may present a computed figure as a
submitted return.

# Never widen risk silently

Risk limits, lot sizes and emergency-stop state are explicit human decisions,
logged with their rationale and their actor. In the platform every such change
is written to the audit log; in the bot and the brain it is a logged human
decision. Brother never proposes widening risk as a side effect.

# The payload contract is append-only

Never rename or remove a field that Pine sends or a bot reads: system, signal,
direction, signal_id, symbol, tf, entry, sl, tp, tp1, tp2, rr, grade. The
brain listener passes unknown keys through; the platform stores the raw
payload verbatim. New fields may be added; nothing may be taken away.

# Pine is the sensor and it stays frozen

Every Pine save requires the alert ceremony: delete and recreate every
TradingView alert, because alerts freeze the script version at creation. A
script that changes weekly means a ceremony every week and history that is no
longer comparable. New intelligence belongs in the evidence tables and the
layer that watches Pine, never in the instrument. Locked 2026-08-20.

# Deploy ceremony

For any service code: backup, then compile or migrate, then restart, then
verify in the logs and the journal. Anchor-safe edits only; abort on an
ambiguous anchor. Every schema change ships with a migration note.

# Secrets

Secrets (.env, tokens, passwords, MT5 credentials, the account registry, API
keys, KSeF tokens) are never committed, never printed in logs, templates or
chat, and never placed in this knowledge pack. Stored credentials are
encrypted at rest; API keys and OTPs are stored hashed.

# Open items

An item deferred in conversation is an item forgotten. Deferred work lives in
docs/OPEN_ITEMS.md of the repository it belongs to, and an entry is deleted
only when it is done and verified, with a pointer to the proof.

# The platform session's working laws

Learned between platform versions v5.00 and v5.17 and carried in the handoff:
never infer from silence; one word carrying two facts is the fault to hunt; a
threshold is never moved as a side effect; render the branch, do not grep for
the words. Commands for Shyam are written paste-ready, with the working
directory, and say what output to expect.

# The developer agent's verdict vocabulary

PASS, FAIL, NOT RUNNABLE, UNKNOWN, NOT TESTED. UNKNOWN is never PASS. A
missing dependency, fixture, contract or identity is NOT RUNNABLE, never a
default. BEHAVIOR CHANGED is reported from replay even when every test
passes; IMPROVEMENT versus REGRESSION is a human or evidence verdict, never
inferred. Nothing is marked PASS from static inspection: if it was not
executed, it is NOT RUN.
