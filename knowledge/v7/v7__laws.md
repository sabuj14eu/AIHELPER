---
title: Brother Sniper v7 — iron rules and locked decisions
domain: v7
repo: sabuj14eu/brother_sniper_v7
sources: CLAUDE.md, INTENT_v5.md, ROADMAP.md, docs/START_HERE.md, docs/OPEN_ITEMS.md, docs/V7_AUTONOMY_PLAN.md, docs/ADAPTIVE_GATES_SPEC.md, docs/AUTONOMY_READINESS_2026-08-30.md, docs/SESSION_COORDINATION.md, docs/PINE_UPDATE_NOTE.md, docs/A2_NGINX_MIRROR_SECRET.md, docs/V7_AUDIT_2026-08-01.md, filters/news_gate.py, filters/freshness_gate.py, filters/ai_filter.py, risk/equity_guard.py, utils/asset_gate.py, core/v7_status.py, learning/platform_mirror.py, learning/telemetry.py, bot.py, sniper_executor.py, post_outlook.py, post_incident.py, git log f7cacfd, 2229753, e349749
verified_on: 2026-09-16
classification: INTERNAL
---

# The eight Iron Rules (CLAUDE.md, "paid for in real losses")

1. **Nothing bypasses the council.** "No signal path may go direct to an
   executor. (The last bypass, an MT5 scanner, lost 60R. It is retired.)"
   For the v7 arm this means: every order passes v7's full gate chain and
   the bridge; `auto_live.py` posts candidates to v7's OWN webhook so "EVERY
   existing hard gate applies untouched... We add none and we bypass none".
2. **Payload contract is APPEND-ONLY.** Never rename/remove fields Pine sends
   or bots read (system, signal, direction, signal_id, symbol, tf, entry, sl,
   tp, tp1, tp2, rr, grade). Unknown keys pass through. The v7 bot extends
   this to its own outputs: telemetry columns, heartbeat fields, mirror close
   rows and decision records are all "append-only" (learning/telemetry.py,
   core/v7_status.py, learning/platform_mirror.py).
3. **Every Pine save requires the ALERT CEREMONY**: delete + recreate ALL
   TradingView alerts ("Any alert() function call"), because alerts freeze
   the script version at creation. The filename never changes. "An
   un-recreated alert keeps running the OLD broken version — which is
   exactly how a symbol goes quiet for days" (docs/PINE_UPDATE_NOTE.md).
4. **Deploy ceremony** for any service code: backup -> compile -> restart ->
   verify in logs/journal. Anchor-safe edits only; abort on ambiguous anchors.
   Every `patch_*.py` implements it: backup `<file>.bak.<stamp>`, every anchor
   must match exactly once or NOTHING is written, `py_compile`, restore on
   failure, idempotent (prints ALREADY PATCHED).
5. **EVIDENCE LAW**: no live logic changes without data. New rules must pass
   the backtest harness (train/validate split; the VALIDATE column decides)
   or accumulate journal evidence (n>=20 minimum; n<20 is luck). Judge
   nothing before ~100 trades. One organ changed per week. Encoded as
   `FLOOR = 20`, `MEASURED_N = 100` in learning/conditional_profile.py and
   `MIN_N = 20` in nightly_edge.py / scorecard.py.
6. **Health endpoints lie; only TICKETS tell the truth.** "The dashboard
   bot-guards exist because an executor served 200s for 6 days while placing
   nothing." In v7 this produced the truth guards (positions-shape guard,
   unverified-close guard), the heartbeat (so "v7 quiet" differs from "v7
   down"), the A1 bridge 503, and the Panel Law ("A blank panel means the
   CHART DISPLAY died, not the trade").
7. **Never widen risk silently.** Sizing/risk changes are explicit human
   decisions, logged with their rationale. Code corollaries: `ASSET_GATE_SIZE`
   multiplier clamped <= 1.0 (can only reduce), the `_tighter` guard (SL may
   only tighten, never widen), the F8 counter-trend dial default OFF, DD
   guard numbers change only on Shyam's explicit words (risk/equity_guard.py).
8. **Secrets are never committed, never printed in logs or chat.** Lesson
   H-0 (2026-08-01): bot.py logged the raw payload after injecting the secret,
   so the webhook secret landed in bot.log/journalctl and a committed dump.
   Now the log redacts `secret`; probe scripts never print URL, token or
   account; `fetch_platform_state` keeps the secret out of error strings.

# Evidence Law corollaries locked in v7

- **Two independent populations agreeing is the standard.** The platform's
  paper lanes propose; only v7's own filled trades justify. "Nothing moves
  until v7's own filled trades agree" (docs/START_HERE.md on the >3 ATR
  distance finding, n=620 one population).
- **A split sample is a smaller sample**: cut by side and with-trend vs
  against-bias and check n in each cell before reading a finding; below the
  floor the honest verdict is CANNOT SEPARATE (Pine/bot agreement n=7 vs 14,
  docs/AUTONOMY_READINESS_2026-08-30.md).
- **UNKNOWN is never PASS; NOT RUN never converts to PASS** (readiness report
  rules, sections 15-16 and 20).
- **Shadow first, then enforce**: every adaptive or new gate ships in shadow
  and earns enforcement with its own log at n>=20 (freshness gate v1,
  adaptive gates). Exception recorded: NEWS01 tightened an existing hard gate
  and "adds no new way to trade, so it does not need shadow evidence to earn
  enforcement" (filters/news_gate.py).
- **Never refute from a partial read** (lesson C1, 2026-09-02: the auditor
  was right; the refutation had read a truncated view of bot.py).
- **Judge nothing early**: "THE PRIME DIRECTIVE OF THIS PHASE: v7 only,
  collect for a week, judge nothing early" (docs/V7_AUTONOMY_PLAN.md).

# Freshness Law as applied in the v7 bot

Adopted from the platform constitution: STALE DATA MUST NEVER BECOME A VALID
POSITIVE SIGNAL; MISSING NEWS != low risk, it is UNKNOWN. v7 code paths:
`fetch_atr` refuses candles older than 3 bars (bot.py); `auto_live.candidate`
returns "candles stale (>3 bars) — DECISION BLOCKED, DATA FRESHNESS";
`filters/freshness_gate.py` names the state `DECISION BLOCKED — DATA
FRESHNESS` (signal age > 900 s, or |ref-entry|/ATR > 1.5 in v2); NEWS01
treats a dead or aged calendar as UNKNOWN, which blocks. Every re-posted datum
carries its true `as_of`; nothing is repainted fresh (docs/SESSION_COORDINATION.md).
Documented exception: freshness gate v1 does NOT block on UNKNOWN inputs
(age None, ATR None) "to match the codebase's documented fail-safe posture";
flipping that to fail-closed "is a listed future decision, not a silent
default" (filters/freshness_gate.py).

# NEWS01 — three states, two witnesses (locked 2026-09-15, after-soak job 6)

The v7 news gate returns CLEAR only when v7's OWN ForexFactory reading AND the
platform's `GET /api/v1/news/state` BOTH say CLEAR; BLOCK when either says
BLOCK ("a known event beats a doubt"); UNKNOWN when either cannot say (own
feed never fetched / empty week / older than its max age; platform
unreachable, non-200, malformed, expired, not configured). UNKNOWN blocks
exactly like BLOCK. The platform witness is asked on EVERY signal and never
cached. The own window rule is unchanged: 30 min either side of any
HIGH-impact event, 45 min for USD/EUR/JPY/GBP/CAD/AUD/XAU/XAG/BTC. Rationale:
the old gate "returned the cache on any fetch failure, and the cache starts
EMPTY, so a dead feed, a 429, or the first signal after a restart read as
clear" (commit 2229753; filters/news_gate.py).

Own-reading max age (2026-09-15, commit e349749): the 600 s was a refetch
interval, never a max age; a last-good reading stands for at most 3 h, the
platform's `FEED_MAX_AGE_H` for the same calendar — "one calendar, two
readers, one staleness law". `V7_NEWS_OWN_MAX_AGE_S` overrides (explicit
human decision).

# NEWS01 modes and the observe decision (2026-09-16, Shyam)

`V7_NEWS_GATE` has three modes: `enforce` (code default — "a box with no
V7_NEWS_GATE line is the cautious one"), `shadow` (the OLD two-state verdict
decides; the three-state one is logged as evidence, for day-one platform
misbehaviour), and `observe`. Observe was Shyam's explicit decision
2026-09-16: "the bot should be intelligent, not a sleeper" — v7 trades
through high-impact news on the DEMO account so what it does there can be
measured. In observe mode the verdict is still computed on every signal, the
trade proceeds, the verdict is written to telemetry as `news_observe` (joined
to the outcome by signal_id) and `[NEWS OBSERVE]` is logged; the AI filter
still scores news minutes; nothing else moves. Switching modes is an explicit
human decision logged with its reason (commit f7cacfd). Whether the box .env
currently carries `V7_NEWS_GATE=observe` is UNKNOWN from the repo.

# UNKNOWN never reads as something else (the family of guards)

- UNKNOWN is not FLAT: an executor error reply or a body without a
  `positions` key skips the monitor cycle instead of parsing as an empty
  list (patch_truth_guards.py, 2026-08-31).
- UNKNOWN is not a LOSS: a ticket missing from `/positions` and `/history` is
  held 10 cycles, then closed LOUDLY as UNVERIFIED with no loss count and no
  streak increment (patch_unverified_not_loss.py, A1 round 2, 2026-09-02).
- UNKNOWN is not a BALANCE: `get_balance()` returns None on non-200, missing
  field or exception; None never reaches the guard, sizing, heartbeat or
  Telegram; `ACCOUNT_BALANCE` is dead config (ISO-02, 2026-09-05).
- UNKNOWN is not an ACCOUNT: the bridge refuses every order until
  `V7_MT5_LOGIN` is set and matches the terminal (ISO-01); `/execute`
  without `account_id` is 400 (ISO-03).
- UNKNOWN is not CLEAR: the seen-store unreadable = 503; the global stop file
  unreadable = STOP (ISO-06, ISO-16); the news calendar absent = UNKNOWN.
- UNKNOWN is not a VALUE on the wire: heartbeat and decision records drop
  None keys; "the consumer renders UNKNOWN, never a manufactured value"
  (core/v7_status.py). Close rows send absent levels as absent, never 0.

# Identity and dedupe law (ADR-004, dual-MT5 isolation, 2026-09-04..15)

Uniqueness is `(account_id, signal_id)`. The bridge asserts ONE account
(`V7_MT5_LOGIN`), stamps `V7_MAGIC_NUMBER` (default 70007) on every order,
refuses to close/modify positions that are not v7's (magic 70007 or legacy
`BS_` comment), keeps an `(account, signal_id)` seen-store marked BEFORE
`order_send` (409 on duplicate, TTL 6 h), and reads ONE global stop file
shared with the v18 executor (`C:\brotherbot\GLOBAL_STOP`; present = STOP,
unreadable = STOP). The bot's persisted dedupe key is
`<V7_MT5_LOGIN>:<symbol:signal_id>`; the EquityState is stamped with its
account and a foreign state hard-stops the guard with counters kept ("never
reset = never widened") (sniper_executor.py, bot.py, risk/equity_guard.py).

# No LLM in the decision path, ever (V7_SELF_DEPENDENCE_PLAN; ISO-24 2026-09-05)

The model vote (Gemini/DeepSeek "eye") is asked only on a rule block so the
journal can grade it, is recorded in `breakdown["deepseek"]` with
`shadow_only: True`, and "can never turn `passed` from False to True... a
model may remove risk, never add it" (filters/ai_filter.py). Earlier law F6
(2026-07-02): never let the AI override a news-flagged block. ROADMAP
principle (2026-06-06): "AI as vote, not boss"; "100+ recorded signals before
AI chart layer added". `learning/consult_brain.ai_gate` is fail-open ALLOW
and is not wired (STEP 5, "once a cluster has earned it").

# Pine is the sensor and stays frozen

"A sensor that keeps changing measures nothing." New intelligence belongs in
the evidence tables and read models, never in Pine. The only two Pine fields
worth adding were `pine_ver` (already present since v18.8) and `structure`
(shipped in v18.13) (docs/PINE_UPDATE_NOTE.md). ICT features (FVGs, order
blocks, CISD, rejection blocks, opening gaps) are FEATURES for the platform's
research layer, not gates, and touch neither Pine nor the bot until a table
says they deserve to (docs/V7_AUTONOMY_PLAN.md).

# Read-only mirror law (every v7 -> platform emitter)

"This module NEVER affects trading. Every entry point swallows every
exception. A mirror that can break the order path is worse than no mirror"
(core/v7_status.py). The platform displays what v7 decided; it never
dispatches trades, never modifies signals, never becomes an input to a
trading decision (learning/platform_mirror.py). Telemetry and reject capture
carry the same hard rule (learning/telemetry.py).

# Session-coordination law (docs/SESSION_COORDINATION.md)

1. Never `git checkout <branch>` on a box whose services run from the
   current checkout. 2. Need one file from another branch? Take the file:
   `git checkout origin/<branch> -- path/to/file.py`. 3. Push deploy-ready
   work to `main` too. 4. "Already up to date" while the remote branch moved
   is the fingerprint of this problem — check `git branch --show-current`.
5. Deployed != committed: verify what RUNS from its own mouth (journal
`pine_ver`, service endpoints). Do not fix the forked v7->platform contract
by adding the second emitter; pick ONE at convergence.

# Trading intent (INTENT_v5.md, Shyam, 2026-05-05, "calm, deliberate")

The February disaster was manual revenge-averaging into Gold, not Gold the
instrument; do NOT re-lock Gold as "observed only". Symbol thesis to be PROVEN
by 100 trades: GOLD and BTC Asia-preferred; SILVER and USDJPY distrusted but
still traded. Unchanged from HANDOFF v4: 0.5% risk per trade all symbols
equal; 3-loss pause stays at 3; Max DD 12%; demo until 100 trades + 55%+ WR +
positive expectancy; live capital target $300–500 mid-June 2026 only after
rules satisfied; no code changes, no whitelist, no per-symbol risk weighting.
"When the two conflict, this file wins on symbol intent." (The 0.5% and 12%
figures are NOT what the code implements today; see the overview.)

# Adaptive gates law (Shyam, 2026-08-24, docs/ADAPTIVE_GATES_SPEC.md)

"Gates protect, they do not blind." HARD SAFETY GATES that learning can never
override: broker/execution unavailable, stale or corrupt data, impossible or
missing price, spread beyond absolute limit, duplicate/corrupt candle stream,
risk/position limits, emergency state, invalid SL, R:R floor, dedupe.
ADAPTIVE GATES have four states: ALLOW / CAUTION (reduced risk via
ASSET_GATE_SIZE or the cluster 0.25x/0.5x/1.0x scale) / WAIT / BLOCK. UNKNOWN
cells (resolved n<20) are never proven, never pretended, never traded as if
measured. Path: OFFLINE REPORT -> SHADOW -> EVIDENCE REVIEW -> EXPLICIT HUMAN
APPROVAL -> ceremony, CAUTION before ALLOW, one organ per week. "Never:
yesterday-bad -> AI edits gate -> today-trades." Developer verdict: APPROVED;
"Gates do NOT loosen yet."

# Decision cards that are Shyam's alone (recorded 2026-08-31, open)

1. PULLBACK on v7: the validated trigger never reaches v7 (noise filter drops
   every non-SMART_SCALP type). Recommendation (a): leave v7 as the scalp arm;
   auto_live is the pullback path. Recorded as C4 at the bot.py gate.
2. DD guard: daily/weekly/total effectively OFF at 99%. If real limits are
   wanted, Shyam names the numbers; tightening only, never widened silently.
Also Shyam's: the weekly AI budget (brain .env), USA500 in BIAS_CORE_SYMBOLS,
dead rows USOIL/XRP/USA500, RESOLVE buttons on incidents, AUTO_LIVE_ARM=1.

# GOLD demo collection decision log (Shyam, 2026-08-24)

Gate ENABLED for one week (2026-08-24 open -> 2026-08-29 close) for
SECOND-POPULATION MEASUREMENT ONLY, DEMO, sizing UNCHANGED, no rule change.
Review at window close: RE-GATE or KEEP ENABLED from the rejected-vs-traded
comparison, never from P/L feelings. "GOLD is doing well, enable
permanently" is NOT an available outcome. Standing decision from the readiness
report: GOLD is EXCLUDED from auto-live-v1 because its own record said no.

# Authorship and status contracts with the platform

- Outlooks: `post_outlook.py` refuses confidence/probability/chance words,
  blank thesis, blank source, and a level with no reading; a changed mind is a
  NEW post, never an edit. Auto-weekly outlooks are signed
  `source="bot box auto-weekly-v1"` and never impersonate Shyam.
- Incidents: an agent may report only INVESTIGATING or PATCH_PROPOSED
  (platform contract v5.04); APPROVED/REJECTED/RESOLVED are Shyam's buttons.
  The poster refuses "resolved" at argparse and prints any refusal, because
  "a bare 200 hid it once" (post_incident.py, docs/OPEN_ITEMS.md).
- Readiness: "an absent report is a fact, not a blank" — post_readiness.py
  refuses when no `docs/AUTONOMY_READINESS_*.md` exists.

# Lessons written as rules after the August/September incidents

- Probe before trusting an alias (DXY->USDX pointed at a symbol the terminal
  does not list; RIPPLE died at MT5). "An alias is a claim about a name
  existing somewhere else, and nothing checks it until something tries."
- Render the reason, never the absence. Build to the wire, not to the spec
  (bridge sends `rows`/`time`, not `candles`/`ts`).
- A scalar offset cannot convert a multi-year series; internal consistency
  is not correctness; check the distribution, not the mode.
- Config that is accepted is not config that is applied (`BB_PUSH_CANDLES`,
  NSSM registry overrides, `nssm set` failing silently on UTF-16).
- "Every one of these failed without an error. That is the family to look
  for." (docs/START_HERE.md)
- Git green != live until the ceremony runs on the box (OPEN_ITEMS round 2).
- One launcher per Windows service: two writers of one heartbeat row is a
  fault of its own (round 4, reporter Scheduled Task vs NSSM).

# The one rule that outranks the rest (docs/START_HERE.md)

"Nothing here changes a trading rule. Evidence proposes; v7's own filled
trades justify; two independent populations, a validate split and n>=20–30
before promotion is even a conversation. Iron Rules 1, 5 and 7 stand above
anything written in this file."
