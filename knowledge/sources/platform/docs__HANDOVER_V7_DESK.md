---
title: Trade Desk handover for v7
domain: platform
repo: sabuj14eu/Sniper-System
sources: docs/HANDOVER_V7_DESK.md
verified_on: 2026-09-16
commit: 3257184
classification: INTERNAL
---

# HANDOVER — v7 Desk page + altcoin coverage (written 2026-08-17)

You are a new session picking this up because the previous window got too
heavy to keep working in. Everything you need is here or linked from here.
**Read `CLAUDE.md` first, then `docs/V7_SELF_DEPENDENCE_PLAN.md`, then this.**

## The user's request, in his words

> "i want to update v7 bot with altcoin and desk ai intelegent … He should
> make new page only for v7 similer trade desk. but no need new rules or
> code only take data."

Two pieces of work. The second sentence is the binding constraint on both.

## THE ONE RULE THAT GOVERNS THIS WHOLE TASK

**"No new rules or code — only take data."**

This page is a **read-only mirror of v7's own state**. It must not:
- compute a v7 entry, SL, TP or grade the bot did not send;
- re-derive, "correct" or recompute anything v7 reported;
- add a gate, a filter, a threshold or a score of its own;
- reach an executor (Iron Rule 1 — unchanged, forever).

If a number is not in v7's payload, the page shows **UNKNOWN**, never a
platform-computed substitute. The Trade Desk's four lanes are OUR engines
and stay clearly separated from v7's numbers on any shared screen — the
whole head-to-head experiment dies if the two get blended.

## Part 1 — the /v7 page

### What data already exists (no bot work needed to start)

- `Signal` rows with `system == "v7"` — entry/sl/tp1/tp2/rr/grade/status,
  plus everything else verbatim in `raw_payload` (Iron Rule 2).
- `DecisionEvent` rows with `system == "v7"` — including **rejections and
  blocks with their gate and reason**. This is the richest v7 data we hold
  and the reason the page is worth building today.
- `Trade` rows from the MT5 heartbeat — real pending/open orders, matched
  by symbol + direction + entry ≤0.1%, scoped per user.
- `MarketBias` — includes `spread`/`spread_points`/`spread_at` (v4.8).
- `Signal.rr_in_grade` (v4.9) — did the sender's grade consult R:R?
  `None` means unstated; render UNKNOWN, never assume `true`.

Build the first version from these. Do not wait for the bot box.

### Shape to follow

Copy the Trade Desk's structure, not its content: `app/routers/intel.py`
(`trade_desk`) + `app/templates/dash/desk.html`. Per asset:

1. **v7's current view** — its latest signal/decision for the symbol, with
   status and age, and the market-open badge (`market_time.market_status`).
2. **Why v7 is NOT trading it** — the gate that stopped each signal, from
   `DecisionEvent`. `/three-lane` already renders this well
   (`pine_blocked`); reuse the pattern.
3. **Live MT5 truth** — pending/open orders for that symbol.
4. **Freshness on everything** — v7 heartbeat age, spread age, candle age.
   Iron Rule 5: silence is not health. A v7 that has said nothing for an
   hour is UNKNOWN, not "no setups".

Add `('v7_desk','/v7','🤖','v7 Desk')` to the WORKSPACE group in
`app/templates/dash/_base.html`.

### "Desk AI intelligent"

The user means the **explanation layer** he already likes — the WHY block
and the Daily Market Brief — applied to v7. Reuse, do not reinvent:
- `services/desk.py: validity()` — the ✓/✗ WHY block vocabulary.
- `services/brief.py: deterministic_narrative()` — fixed sentences filled
  from stored values, no AI required.
- If you add an AI narration path it MUST go through
  `services/ai_ledger.call_messages` (budgeted, metered) — a test asserts
  that is the only door, and it will fail you otherwise.
- The AI never decides. Ever. See the plan, §5.7.

## Part 2 — altcoins

**The platform already supports any symbol the bot ships candles for** —
`desk.tracked_symbols` is `SELECT DISTINCT symbol FROM candles`. So the
bot-side work is the real work. Platform-side, only these need attention:

1. `services/precision.py: SYMBOL_DECIMALS` — add each new symbol. Unknown
   symbols fall back on magnitude, which is safe but imprecise; a wrong
   decimal count collapses two distinct levels into one displayed string.
2. `routers/webhooks.py: SYMBOL_ALIASES` — map the broker's names
   (e.g. `SOLUSD` → `SOL`) so filters and gates match canonical symbols.
3. `services/market_time.py: CRYPTO_247` — already covers
   BTC/ETH/XRP/SOL/DOGE/ADA/LTC/BNB/DOT by prefix. Add anything else, or
   the weekend logic will treat it as a closed market.
4. `routers/scanner_page.py: CORE_UNIVERSE` — decides which symbols get an
   automatic Daily Brief and blind AI round. Adding symbols here increases
   AI spend; check the cap first (`BB_AI_WEEKLY_BUDGET_USD`).

**Disclose the shorter history.** A symbol added today has days of data
while GOLD has weeks. Never pool them into one statistic without saying
so — same rule as mixed prompt versions and mixed engines (v4.5, v4.11).

## Standing constraints — do not renegotiate these on your own

- `pytest -q` must pass before every commit (288 at handover).
- Every schema change ships with a migration block in `docs/CHANGELOG.md`
  (Iron Rule 6). **SQLite ignores VARCHAR limits — Postgres does not.**
  See v4.6: a 29-char value in a `varchar(24)` broke production silently
  while every test passed. `tests/test_column_widths.py` exists for this.
- Never swallow an exception on a user-triggered action (v4.4).
- A number without source + timestamp + freshness is a bug (Freshness Law).
- `docs/OPEN_ITEMS.md` lists deferred work of both sides. Read it before
  telling the user anything is "finished".

## Working agreement with the bot box

The user relays messages between this session and his brain-v2 session;
they do not talk directly. **Do not ask for write access to the bot repo,
and do not accept it for the platform repo** — the two halves auditing
each other across a data contract is what found most of this month's real
bugs. Ship a payload contract, not a pull request.

## Status at handover

Phase 1's exit gate is MET: 412 resolved trade candidates, 2056
observations, every dataset field populated. Phase 2 (conditional tables,
statistics only, no ML) is the next planned step and is NOT part of this
task. Do not start it without the user saying so.
