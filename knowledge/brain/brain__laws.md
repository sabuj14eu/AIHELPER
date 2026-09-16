---
title: Brother v18 Brain — Iron Rules and Locked Decisions
domain: brain
repo: sabuj14eu/brother-brain-v2
sources: CLAUDE.md, docs/decisions.md, docs/PROTOCOL.md, docs/SESSION_COORDINATION.md, docs/SESSION_PENDING_SPEC.md, docs/AUDIT_2026-07-31.md, docs/OPEN_ITEMS.md, docs/PINE_VS_BOT_MAP.md, docs/HANDS_OFF_DEPLOY.md, brain/src/main.py, brain/src/pine_trust.py, brain/src/platform_mirror.py, brain/src/shadow_gate.py, brain/src/utils/decision_journal.py, brain/src/agents/council.py, executor_ic_markets/src/main.py, executor_ic_markets/src/ic_markets/mt5_bridge.py, executor_ic_markets/src/utils/global_stop.py, executor_ic_markets/src/clock_witness.py, tests/audit/2026-09-05_iso15/PROPOSAL_ISO15.md, tests/audit/2026-09-05_iso11/PROPOSAL_ISO11.md
verified_on: 2026-09-16
classification: INTERNAL
---

# The eight iron rules of the v18 brain (CLAUDE.md, "paid for in real losses")

CLAUDE.md opens: "Read this before touching anything. These rules were paid for in real losses." The eight rules below are quoted from it; the rationale after each comes from the same file or the cited source.

**Iron Rule 1 — NOTHING bypasses the council.** "No signal path may go direct to an executor. (The last bypass, an MT5 scanner, lost 60R. It is retired.)" The -60R bleed came from scanner signals riding the pine_trust auto-approve path; `brain/src/pine_trust.py` now refuses any opportunity with `origin == "mt5_scanner"` ("scanner proposals have no Pine gates behind them and must ALWAYS face the council", 07-02). The audit of 2026-07-31 documents two council bypasses that exist BY DESIGN and must stay conscious decisions: the grade gate (pine_trust for B-not-sampled and below) and the fail-soft on AgentError, now budgeted to `FAILSOFT_MAX_PER_DAY` (default 2).

**Iron Rule 2 — Payload contract is APPEND-ONLY.** "Never rename/remove fields Pine sends or bots read (system, signal, direction, signal_id, symbol, tf, entry, sl, tp, tp1, tp2, rr, grade). The brain listener passes unknown keys through." The listener became append-tolerant on 07-20 after a fixed whitelist silently dropped every v18.8 field (`brain/patch_brain_passthrough.py`); the platform mirror and mirror_outcomes only ever add keys (`exec_sl`, `reason` alias, `fail_soft`, `ticket`), and "absent stays absent (None), never invented".

**Iron Rule 3 — Every Pine save requires the ALERT CEREMONY.** "delete + recreate ALL TradingView alerts ('Any alert() function call'). Alerts freeze the script version at creation. The filename never changes." Consequence recorded in docs/PINE_VS_BOT_MAP.md: a 0.18-ATR stop on the 08-06 RIPPLE reject could not come from current code, so either the alert was frozen on old Pine or the setting was hand-lowered. The definitive check is `grep -o '"pine_ver":"[^"]*"' logs/decisions.jsonl | sort | uniq -c`.

**Iron Rule 4 — Deploy ceremony for any service code.** "backup -> compile -> restart -> verify in logs/journal. Anchor-safe edits only; abort on ambiguous anchors." Every `patch_*.py` in the repo follows it (backs up with a timestamp, `py_compile`, auto-restores on failure, "aborts untouched on anchor mismatch"); the Windows release-gate scripts write nothing anywhere if any anchor matches other than exactly once.

**Iron Rule 5 — EVIDENCE LAW.** "no live logic changes without data. New rules must pass the backtest harness (train/validate split; the VALIDATE column decides) or accumulate journal evidence (n>=20 minimum; n<20 is luck). Judge nothing before ~100 trades. One organ changed per week." `truth_layer.py`, `weekly_source_report.py` and `council_calibration.py` all print "n<20 is PROVISIONAL" and the backtests print "the VALIDATE column is the only one allowed to convince you."

**Iron Rule 6 — Health endpoints lie; only TICKETS tell the truth.** "The dashboard bot-guards exist because an executor served 200s for 6 days while placing nothing." The incident is tagged LIVE-20260713-GHOST in `dashboard/backend/patch_dashboard_botguards.py` ("for 5 days the v18 arm journaled approvals with dispatch=200 while placing nothing, and every health tile stayed green"); the fix reads the executor's `/outcomes` tickets and turns the tile RED on "approvals in 24h with zero tickets".

**Iron Rule 7 — Never widen risk silently.** "Sizing/risk changes are explicit human decisions, logged with their rationale." Applied in ISO-15 (2026-09-15): a file named GUARDS_DISABLED can no longer lift the kill switch or daily caps because "a file's presence has no actor, no rationale and no expiry, so it cannot be one" (executor main.py); and in the favorable-only MODIFY invariant (SL may only move toward price), which "is NOT bypassable by GUARDS_DISABLED".

**Iron Rule 8 — Secrets are never committed, never printed.** ".env, tokens, passwords, account registry" are gitignored (`.gitignore`: `.env`, `*.key`, `*.pem`, `*signing*`, `accounts.json`, `*.jsonl`). decisions.md 2026-05-29 adds the habit: "Don't paste partial keys in chat. Math may make a 5-char leak safe; the habit makes the 60-char leak inevitable." An admin halt token that appeared in chat was flagged for rotation before live funding (2026-05-22).

# Working laws from CLAUDE.md "HOW TO WORK HERE"

"Findings first, then code. Small verified diffs over rewrites. When a claim matters, grep the journal (logs/decisions.jsonl) — this system's history is measured, not remembered. If something looks broken, check what the TICKETS say before believing any green light."

# Locked decisions from docs/decisions.md (May 2026)

**2026-05-13 — Sandbox is Monte Carlo, not MiroFish.** The Polymarket pre-trade sandbox uses `_monte_carlo_fallback` in `brain/src/sandbox/mirofish.py`; MiroFish-Offline is not installed because the brain box has 11 GiB RAM, no swap, no GPU, and "adding MiroFish before v18 has proven profitable is premature optimization." Revisit only with 3+ months of live PnL or a separate GPU box.

**2026-05-13 — Brain runs as a systemd unit**, never a foreground process (`brother-brain.service`, restart on-failure, hardened). Known weakness recorded: the Researcher retry used the same max_tokens that just failed; bumped 4000 to 8000 as a workaround.

**2026-05-21 — TradingView's 3-second webhook timeout.** "Council deliberation takes 5-90s. /webhook/v18 must return 200 immediately and run council.evaluate() in a background task." Implemented as `asyncio.create_task(_run_v18_council(...))` in brain/src/main.py.

**2026-05-21 — Decision journal is the truth.** One JSON line per signal at `logs/decisions.jsonl`; "fields always present (null when not applicable) so the file parses as a stable dataframe." Cost estimates in it "are heuristics, NOT accounting."

**2026-05-21 — Anthropic Tier 2.** Tier 1 (30,000 input tokens/min) could not complete a ~60K-token council round once the Researcher retried; decision: add credit to auto-promote to Tier 2.

**2026-05-21 — Permissive auth for shakedown (final auth design).** "bot should adapt to Pine reality, not force Pine edits with every Brain change." A wrong `secret` is a 401; a missing `secret` is accepted on the nginx IP allowlist; `BRAIN_REQUIRE_SECRET=true` enforces strict mode when live. "That's the only Pine edit ever needed."

**2026-05-30 — Polymarket geoblock: migrate to Dublin, never a proxy.** Order placement returns 403 from Germany; proxy circumvention was REJECTED because "Polymarket TOS explicitly forbids; risk of permanent account/wallet ban" and it "doesn't change Polish law about trading on unlicensed gambling sites anyway."

**2026-05-26 — Drill before you need it.** The first emergency HALT drill failed twice silently before revealing the Frankfurt nginx allowlist lacked the Amsterdam watchdog IP: "test BEFORE you need it."

# Locked decisions from the July–September 2026 code and docs

**07-09 (Shyam) — BSv11 LITE alerts are Telegram-only in the brain.** "v7 is the only bot trading v11, via the nginx mirror"; the brain posts the provider message and returns, "NO council, NO pine_trust, NO dispatch, $0 API" (`brain/patch_brain_v11_telegram_only.py`, `brain/src/main.py`). An earlier design that sent v11 to the full council was "wrong design, reverted."

**06-12 — Grade gate as cost control.** Council only for A/A+ and a random one-in-three B; everything else approves from Pine trust or is grade-rejected. The audit names this "council bypass BY DESIGN."

**07-02 — API failures are not trading decisions.** "761 wallet/529/500 errors were journaled as 'Scout' rejections and poisoned the approval stats for weeks." Reclassified as `AgentError`; A/A+ entries fall back to Pine trust (fail-soft), MANAGE results are exempt.

**07-31 (audit P1-1) — Fail-soft is bounded.** After `FAILSOFT_MAX_PER_DAY` (default 2) fail-soft approvals in a UTC day the brain fails CLOSED and alerts on Telegram. docs/OPEN_ITEMS.md 2026-09-02 records the budget was fully spent that day (2/2) and that the final policy (keep 2/day, lower, or always fail-closed) is "DECISION OWED BY SHYAM (Iron Rule 1 exception)".

**07-20 — DECISION-A, min-lot inflation tolerance.** Demo phase tolerates up to 2.5x risk inflation at the broker minimum lot (was 2x); orders whose correct size is under 0.4x the minimum lot are skipped. Cost basis: "ticket 1697829693 asked 0.41 USD risk, lost 25.18" (`mt5_bridge.py`).

**2026-08-05 — Session-caller pending orders are QUEUED, not built** (docs/SESSION_PENDING_SPEC.md). The only legal shape is `session_call -> council judges -> if approved, dispatch a PENDING order`; precedence "council-approved live v18 signal > resting pending" (cancel the pending, place the market order, one position, council on top). Prerequisites: score the paper record first (n>=20), confirm the executor can place and cancel pendings, spec the cancel-then-market step atomically.

**2026-08-21 — BOT-P0-2: Pine's signal_id is THE canonical id.** "adopting Pine's id lets [the executor] refuse a genuine Pine duplicate, which a freshly minted id never could. Minting remains ONLY the fallback" (`canonical_signal_id` in decision_journal.py; the source `pine` / `minted_fallback` is journaled).

**2026-09-02 — B5: A clock needs two witnesses.** The executor `/candles` endpoint converts broker time to UTC only when at least two fresh 24/7 witness ticks agree on the offset; otherwise it returns 503 "clock unverifiable" — "an assumed clock corrupts every consumer" (`executor_ic_markets/src/clock_witness.py`, tests/test_clock_offset.py).

**2026-09-02 — ONE reporter process per box.** After five `mt5_reporter.py` processes were measured writing one platform row (four August orphans), OPEN_ITEMS sets the standing rule: "Every manual reporter run ends with the process list checked."

**2026-09-02 — Shadow symbols go live only by a logged human decision.** `brain/src/shadow_gate.py`: a symbol in `SHADOW_SYMBOLS` (default NVDA) is judged, journaled with `dispatch_mode blocked_shadow`, mirrored as `rejected_by ShadowGate`, and never reaches `dispatcher.dispatch`. "A shadow symbol goes live only by being REMOVED from SHADOW_SYMBOLS on purpose, logged."

**2026-09-05 — ADR-004: identity is asserted, never inferred.** ISO-09: the bridge requires `MT5_LOGIN`/`MT5_PASSWORD`/`MT5_SERVER` (missing = NOT RUNNABLE) and compares `account_info().login` to `MT5_LOGIN` on every attach and probe; a mismatch shuts the MT5 link down. ISO-10: `account_id` is inside the signed envelope; the dispatcher refuses live dispatch without `EXECUTOR_IC_MARKETS_ACCOUNT`; the executor refuses `no_account_id` / `account_mismatch`.

**2026-09-05 — ADR-005: execution values are computed by code.** ISO-19: "The model's prices never reach the wire; only its bounded params and a risk_pct that can be lower than the base do. A calculator failure rejects." ISO-20 (2026-09-15): a missing `risk_pct` is refused, never sized at a default — "a number the sender did not say is a fabricated number." ISO-21: pine_trust rejects when `compute_sltp` fails ("an unknown stop is not a trade").

**2026-09-05 — ADR-006: an invalidated pending LIMIT/STOP is rejected, never converted to a MARKET order** (ISO-14, `mt5_bridge.py`): "a LIMIT that is already through the market is a different trade, not this one, whatever the drift."

**2026-09-05 — ADR-008: one global emergency stop for both arms** (ISO-16, `utils/global_stop.py`): a file present = STOP, absent = CLEAR, unreadable = UNKNOWN treated as STOP; both Windows services read the same path; admin halt engages it; clearing is a human deleting the file.

**2026-09-05 — ADR-009 / Freshness Law: a loss seen with an UNKNOWN balance is parked, never dropped** (ISO-12); new OPENs are refused until it is applied to a measured balance. ISO-11 (2026-09-15): an unreadable margin is `margin_unknown`, never allowed — "UNKNOWN never becomes 'allowed'."

# Protocol laws (docs/PROTOCOL.md)

Every signal carries an Ed25519 signature, a UUID nonce and a UTC `issued_at`; executors reject `version != 1`, wrong `target`, bad signature, age over 60 seconds, a nonce seen in the last 10 minutes, then apply DRY_RUN, kill switch, daily trade cap, daily loss cap and balance floor. "Why Ed25519 not HMAC? ... only the Brain can sign — Executors only verify." "Why per-trade risk_pct not lot_size? Brain doesn't know broker account balance and shouldn't have to." The kill-switch reset is deliberately not an API: "Resetting kill switch requires SSH-ing to the box and editing state.json by hand. That friction is the feature" (shared/src/protocol/halt_admin.py).

# Multi-session coordination laws (docs/SESSION_COORDINATION.md)

1. "Never `git checkout <branch>` on a box whose services are running from the current checkout." 2. Need one file from another branch? `git fetch origin <branch>` then `git checkout origin/<branch> -- path/to/file.py`. 3. Push deploy-ready work to `main` as well as the working branch. 4. "A pull that says 'Already up to date' while the fetch line shows the remote branch moving is the fingerprint of this problem." 5. "Deployed ≠ committed. ... Verify what RUNS from its own mouth (journal `pine_ver`, service endpoints), never from the repo." Shared contracts not to fork: `pine_signal_id` join key, candidate id `SC-<SIDE>-<UTCstamp>`, outcome truth by ticket, and "every re-posted datum carries its true `as_of`; nothing is ever repainted fresh."

# Evidence-handling laws learned in September 2026 (docs/OPEN_ITEMS.md)

"A verdict is posted only with its query output embedded" (INC-0001 lesson: a wrong draft never reached the record because the post failed). "A coincidence dressed as a cause is exactly what the journal exists to prevent" (US10Y/US100 correlation retracted once the 70h figure was found to be paper rows). "A served candle proves data, never fill" (order acceptance is a separate human-approved probe). "A push is not 'delivered' until the receiver says what it stored" — mirror_outcomes and reconstruct read back the platform's `stored`/`skipped` counts and print COUNT MISMATCH.
