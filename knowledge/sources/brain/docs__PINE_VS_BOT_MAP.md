---
title: Pine versus bot map
domain: brain
repo: sabuj14eu/brother-brain-v2
sources: docs/PINE_VS_BOT_MAP.md
verified_on: 2026-09-16
commit: 0f8f49d
classification: INTERNAL
---

# PINE vs BOTS — who decides what (v18.7 Pine, mapped 2026-08-06)

> **⚠ SUPERSEDED IN PART — see the v18.12 addendum at the bottom.** The
> CANONICAL Pine now lives in `Sniper-System/pine/` (branch
> `claude/tradingview-token-limit-kx0tph`, PR #1): Pine v6, `pine_ver 18.12`,
> 210 KB. The copy in this repo is the v18.7-era snapshot the sections below
> were mapped from — the architecture description still holds; specific
> behaviors corrected in the addendum. The `pinev18.6` GitHub repo is empty.

Source at time of writing: a v18.7-era copy that lived at
`brain/src/agents/BrotherSniperULTIMATE_v18_FINAL (5).pine`. That file was
DELETED on 2026-08-19 — see `brain/src/agents/PINE_SOURCE.md`. The canonical
script is `Sniper-System/pine/BrotherSniperULTIMATE_v18_FINAL_v6.pine`.

## The one-line answer
**Pine is the signal FACTORY and the first (biggest) filter. The bots are the
JUDGES and the risk police.** Most signals die inside Pine and are never seen;
what reaches the webhook has already passed ~10 gates. Both bots then re-decide
independently from the same payload: the v18 brain with slots/margin/council,
the v7 bot with mechanical dials and its own survivable-stop and margin rules.

## What Pine computes (two live signal types)

### SMART_SCALP (event-driven, per bar close)
1. **Confluence score 0-10** (line 1089): trend +1, HTF agreement +1/+2,
   inducement +2, order block +1, FVG +1, RSI side +1, active session +1
   (Asia earns it too since v18.6), discount/premium zone +1, candle pattern +1.
2. **Macro modifier** (DXY / yields / oil per asset class): promotion uncapped,
   **demotion capped at -1** (v18.6 F2 — used to silently subtract up to 3).
3. **Structural SL**: tightest of 7 candidates (swings, FVG, OB, MA50, range)
   below/above price, capped by `ssAtrCap`, **floored at `aeSLFloor` (default
   0.7 ATR since v18.6 F3)**.
4. **Structural TP ladder**: first structure ≥1R away = TP1, next ≥+0.5R = TP2;
   fallback 1.8R/+1R when no structure. Fill buffers shave both.
5. **6 veto flags** (informational, sent in payload): v1 trend-trap, v2 H4
   agreement, v3 liquidity sweep, v4 R:R ≥ `fcMinRR` (default 1.6, was 1.8),
   v5 structural TP exists, v6 spread OK.
6. **Grade** from macro-adjusted score + veto count: A+ (≥9, 6/6, HTF full),
   A (≥8, ≥5, H4), B (≥7, ≥5), C (≥7, ≥4), else D.
7. **Bot fire** (webhook) requires ALL: score ≥ `fcThreshold` (6) + side
   dominance (if on) + grade in {A+, A, B} + v4 R:R + location gate + cooldown
   + trigger + symbol whitelist + not DXY-squelched + session + daily quota
   (12). The chart shows every signal; the webhook gets the survivors.

### PULLBACK (v18.7, armed limit orders — the validated n=640 design)
- Arms when 15m AND H1 trend agree and price has ≥0.4 ATR room to the nearest
  REAL level (24-bar swing, PDL/PDH, S1/R1, ORG edge).
- Entry = level ± 0.15 ATR front-run · SL = level ∓ 1.5 ATR ·
  TP1 = 1.0 ATR (Asia) / 1.8 ATR (Ldn/NY) · TP2 = ×1.8 · cooldown 20 bars.
- Fires when price touches the armed entry. **Grade is HARDCODED "A"** — the
  council treats every PULLBACK as A-grade regardless of conditions.
- **This is the exact geometry session_caller v2 reimplements in Python**
  (same swing, same 0.4 room, same 0.15 front-run, same 1.5 SL, same session
  TP) — session_caller is "PULLBACK, but scheduled 3x daily best-of-7 instead
  of event-driven". The 08-06 TP study therefore speaks to BOTH.

Also emitted: `MANUAL_GATE` (hand-trading panel info) and dashboard-only rows.

## What the bots re-decide (same payload, independent verdicts)

### v18 brain (the council path)
webhook → dedupe → **SlotGate** (executor /positions, fail-closed) →
**MarginGate** (account probe, fail-closed; floor max(10% bal, $100)) →
6-agent council (risk cap 0.5%/trade, 6/day) → ExecutorPrep payload validated
fail-closed → Ed25519-signed dispatch → **executor re-checks everything
again**: bearer, clock, nonce, per-symbol slot, margin level ≥150%, min-lot
guard (raw ≥ 0.4×min), usable-margin lot cap (40% free margin) → order_send.

### v7 bot (the mechanical arm)
Own filters (F-dials, asset gate, MIN_RR) → **survivable-stop floor: rejects
when its computed floor exceeds Pine's SL by >1.6×** → GATE-MARGIN (balance
floor 500) → bridge :5001 → MT5 52834417.

## Why signals die — the funnel, in order of kills
1. **Pine kills silently** (score < 6, grade C/D, R:R < 1.6, location gate,
   cooldown, squelch, quota) — the chart shows them, the bots never do.
2. **v7 kills tight stops** ("SL floor reject" — see finding below).
3. **Brain kills on state** (slot occupied, margin unreachable/low — cf. the
   08-04/05 outage) and on council judgment.
4. **Executor kills on affordability** (min-lot 0.4× guard — cf. US30 08-06).

## ⚠ FINDING 08-06: live alerts may be running OLD Pine code
The RIPPLE reject showed **Pine SL dist 0.007 ≈ 0.18 ATR** (v7 floor 0.0589 =
1.5 ATR → ATR ≈ 0.0393). But the CURRENT file floors every SMART_SCALP SL at
**0.7 ATR** (v18.6 F3, default) — 0.18 ATR cannot come out of this code with
default settings. Either (a) the TradingView alert was created before the
v18.6 save and is frozen on old code (Iron Rule 3: alerts freeze the script
version), or (b) `aeSLFloor` was manually lowered in the alert's settings.
**Check:** grep a recent SMART_SCALP payload in `logs/decisions.jsonl` for the
`vwap_side` field (added v18.7). Missing field ⇒ the alert predates v18.7 ⇒
re-run the ALERT CEREMONY (delete + recreate all alerts) to deploy the floors
and caps that were already written to fix exactly these rejects.

## Tensions worth knowing (evidence vs evidence)
- CLAUDE.md: grades/scores are ANTI-predictive (B beat A+), yet the bot-fire
  gate only passes A+/A/B, and PULLBACK hardcodes "A". The gate keeps trading
  the grades the journal says don't predict — by design (engine on trial).
- PULLBACK's 1.0/1.8 TP validated at n=640 (event-driven, per-chart); the
  08-06 session_caller study found 1.8 failing for scheduled best-of-7 Ldn/NY
  calls. Not a contradiction — different selection process — but watch both.

---

## ADDENDUM 2026-08-06 — v18.12 corrections (read from Sniper-System/pine)

Read: v18.9→v18.12 release notes + the 210 KB Pine v6 script at
`Sniper-System/pine/BrotherSniperULTIMATE_v18_FINAL_v6.pine` (commit 12b4f45).
What changed vs the v18.7 mapping above, in bot-relevant terms:

**Corrections to the sections above (v18.9–18.12 fixed these):**
- PULLBACK grade is NO LONGER hardcoded "A" — now A with full HTF alignment,
  else B (v18.11 E2).
- The v1 trend-trap veto now actually works — old CHoCH detection was
  mathematically dead and never fired once (v18.10 P1-9 rebuild).
- A+ grade is direction-aware now (v18.9 GRADE FIX) — a SELL can no longer
  earn A+ because the HTF stack agreed with the BUY side (the exact signals
  the council kept vetoing on 07-29/07-30).
- HTF reads (H1/H4/D + DXY/yield/oil) use the last CONFIRMED bar (v18.10
  P0-1) — live and historical finally see the same trend, at the cost of up
  to one HTF bar of lag (the council covers that window).
- Pullback pendings FREEZE on arm (v18.11 E1) — no more drifting entry/SL/TP.
- Pine NEVER blocks on quota/daily-PnL anymore (v18.11 E3, explicit user
  decision): the bot/council is the sole risk authority; `trades_today` is
  appended for visibility. UNKNOWN symbols can never fire (v18.12 F1).
  Sessions are DST-aware (F2). Per-direction signal IDs (E5) fixed a dedup
  double-fire hazard.

**New appended payload fields** (append-only ✓): `pine_ver` (now "18.12"),
`trades_today`, `struct` (HH/HL/LH/LL state; TRANSITION = no-trade candidate),
`entry_dist_atr` (ATRs travelled from the zone before the fire). Two organs
are built DARK awaiting journal evidence: `FEATURE_STRUCT_GATE` and the
Location-Gate max-distance cap (input, default 0=OFF).

**Definitive stale-alert check** (replaces the vwap_side grep above):
`grep -o '"pine_ver":"[^"]*"' logs/decisions.jsonl | sort | uniq -c`
Live alerts current ⇔ recent rows say 18.12. Anything older (or absent) means
the TradingView alerts are frozen on old code (Iron Rule 3) and the ceremony
is due — which would also explain 0.18-ATR stops like the 08-06 RIPPLE reject.

**Companion scripts** (separate budgets, no alerts, cannot fire): Asset Pulse /
Asset Map v4 — a radar/planning panel only. The doctrine holds: the map plans,
v18 confirms, the council decides, Rule 1 intact.
