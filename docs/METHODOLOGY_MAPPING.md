# Methodology mapping — SignalMesh → AI Helper

**Decided 2026-09-17 by the owner, after the read-only inspection in
`docs/MARKET_DATA_INSPECTION.md`.** This file is the contract. Nothing in
`app/trading/` may implement a concept below except as this table records it,
and a change here needs the same review a rate change needs.

Format, as requirement 16 asks for it:
`SIGNALMESH DEFINITION → AI HELPER IMPLEMENTATION → SAME / DIFFERENT → REASON`

---

## What AI Helper is

**AI Helper is not a second trading bot.** It is a read-only market-data
consumer and a reasoning and explanation layer. **SignalMesh remains the
trading authority and the executor.** Brother reads what SignalMesh already
decided and already measured, reasons about it, explains it, and learns from
it. It never places, modifies, dispatches, routes or cancels anything, and it
never becomes a second opinion that competes with the desk.

This is why the table below exists at all. Every row that reads DIFFERENT is a
place where Brother could contradict the authority, and each one has to be
either eliminated or declared.

## The two decisions this file records

**1. Mirror Pine's definitions.** Pine is the sensor: it is where the
methodology is written and it is frozen at alert-creation time. Where Pine
defines a concept, AI Helper implements Pine's definition exactly.

**2. Swing length is 5 — Pine's — and the platform's scanner is not touched.**
SignalMesh contains two swing definitions today (AIH-18): Pine
`ta.pivothigh(high, 5, 5)` and the platform's `scanner.structure_state`
with `swing = 3`. The owner's decision: **AI Helper's canonical interpretation
is Pine's 5**, and `scanner.py` keeps its 3 unchanged.

The consequence has to be stated rather than buried. On the same candles,
Brother's swing set and the platform's `structure` field will sometimes
differ — 5 needs a wider window, so it finds fewer and later swings than 3
does. Where the desk's own `structure` is displayed, **Brother quotes the
desk's value and labels it as the desk's**, and its own swing-5 read is
labelled as its own. Two numbers with two names is honest; two numbers with
one name is the defect the clock incident was about.

---

## Group A — mirrored from Pine, exactly

Source: `Sniper-System/pine/BrotherSniperULTIMATE_v18_FINAL_v6.pine`,
read 2026-09-17. Line numbers are from that reading.

| Concept | Pine definition (verbatim logic) | Line | AI Helper | Verdict |
|---|---|---|---|---|
| **Swing high** | `ta.pivothigh(high, length, length)`, `length = 5` | 800, 216 | same: a bar whose high is the maximum of the 11-bar window centred on it, confirmed 5 bars later | **SAME** |
| **Swing low** | `ta.pivotlow(low, length, length)`, `length = 5` | 801, 216 | same | **SAME** |
| **Structure state** | `smHH and smHL → "UP"`; `smLH and smLL → "DOWN"`; else `"TRANSITION"` | 834-844 | same, and it keeps Pine's three names (UP/DOWN/TRANSITION), **not** the platform's HH/HL·LH/LL·MIXED | **SAME** |
| **CHoCH** | `close` crosses the last swing **against** the prevailing trend: `chochUp = crossover(close, lastHigh) and isDownTrend` | 900-901 | same | **SAME** |
| **Range high / low** | the **last confirmed swing** high and low — not a lookback window | 846-851 | same | **SAME** |
| **Equilibrium** | `(rangeHigh + rangeLow) / 2`; above = **PREMIUM**, below = **DISCOUNT**, at = **EQ** | 853-857 | same, with Pine's three labels | **SAME** |
| **FVG (bull)** | `low > high[2]` — a three-bar gap. Zone: top `low`, bottom `high[2]` | 1020, 1029-1030 | same | **SAME** |
| **FVG (bear)** | `high < low[2]`. Zone: top `low[2]`, bottom `high` | 1021, 1034-1035 | same | **SAME** |
| **FVG mitigation** | a **fully-filled FVG is dead structure**: bull dies when `close < bullFVGbot`, bear when `close > bearFVGtop` | 1041-1047 | same — and this one is not optional. v18.5 added it because stale zones made the gate fire into news moves | **SAME** |
| **FVG state** | ABOVE FVG · IN BULL FVG · BELOW FVG · IN BEAR FVG · NO FVG | 1049-1054 | same five labels | **SAME** |
| **Impulse** | `close > close[1] > close[2]` and `(close − close[2]) > 1.2 × ATR` | 1062-1063 | same | **SAME** |
| **Strong impulse** | as above with `1.8 × ATR` | 1064-1065 | same | **SAME** |
| **Order block (bull)** | `impulseUp and open[2] > close[2]` — the last **down** candle before the impulse | 1070 | same | **SAME** |
| **Order block (bear)** | `impulseDown and open[2] < close[2]` | 1071 | same | **SAME** |
| **OB zone bounds** | `high = max(open[2], close[2])`, `low = min(open[2], close[2])` — the **body**, not the wick | 1088-1089, 1100-1101 | same | **SAME** |
| **Liquidity sweep (bull)** | `low < lastLow − pipZone` **and** `close > lastLow` **and** `(close − low) > 0.6 × (high − low)` **and** ≥ 3 bars since the last one | 1139 | same, all four conditions | **SAME** |
| **Liquidity sweep (bear)** | `high > lastHigh + pipZone` and `close < lastHigh` and `(high − close) > 0.6 × (high − low)` and ≥ 3 bars | 1140 | same | **SAME** |
| **`pipZone`** | **per instrument**, not a constant: Gold 1.00 · Silver 0.10 · EURUSD 0.0010 · USDJPY 0.10 · DXY 0.10 · Oil 0.10 · US30 10.0 · NAS100 10.0 · BTC 50.0 · ETH 2.00 · fallback 0.15 | 465-483 | same table, as **data** (a config file), never as literals in the calculators | **SAME** |
| **PDH / PDL** | previous **daily** bar's high and low | 613-614 | same | **SAME** |
| **Pivots** | from the previous daily H/L/C: `PP=(H+L+C)/3`, `R1=2·PP−L`, `R2=PP+(H−L)`, `R3=H+2(PP−L)`, `S1=2·PP−H`, `S2=PP−(H−L)`, `S3=L−2(H−PP)` | 863-871 | same seven levels | **SAME** |
| **Zone tolerance** | `lgZoneTol = ATR × lgZoneAtr × aeZoneMul`, `lgZoneAtr = 0.5`, `aeZoneMul = 0.7` in HIGH volatility else `1.0` | 1379, 290, 309, 566 | same | **SAME** |
| **At a level (up-side)** | `high ≥ lvl − lgZoneTol and close ≤ lvl + lgZoneTol` | 1382 | same | **SAME** |
| **At a level (down-side)** | `low ≤ lvl + lgZoneTol and close ≥ lvl − lgZoneTol` | 1383 | same | **SAME** |
| **Zones the gate accepts** | swing, pivot (PP/R1/R2/S1/S2), PDH/PDL, range edge, equilibrium, FVG, OB — and EMA20 only in trend mode | 1388-1405 | same set | **SAME** |
| **Fake breakout** | `high > rangeHigh and close < rangeHigh and open < rangeHigh and (high − close) > 0.4 × ATR`, 3-bar cooldown | 1166-1167 | same | **SAME** |

**Pine's stated purpose for this set**, which is also Brother's:
*"structure: S/R swing, FVG, Order Block, pivot, prev-day H/L, range edge,
equilibrium, or a fresh liquidity sweep. No more chasing mid-move."*
(line 286-287)

## Group B — mirrored from the platform's Python

Source: `Sniper-System/app/services/`, read 2026-09-17.

| Concept | Platform definition | Where | AI Helper | Verdict |
|---|---|---|---|---|
| **Level ladder** | recent high/low (15m, 40-bar), session high/low, each horizon's high/low — deduped, sorted, each carrying `tf` + `lookback` + `source` | `brief._survey:84-127` | **read from the platform, never recomputed.** The file calls itself *"one level engine, one truth"*, and recomputing would create a second | **SAME by construction** |
| **Horizons** | scalp 15m/12 · session 1h/24 · swing 4h/40 · intraday 15m/40 | `desk.HORIZONS:47-54` | same | **SAME** |
| **Entry** | HH/HL → **BUY LIMIT at the range low**; LH/LL → **SELL LIMIT at the range high** | `desk._rules:165-176` | same. Both sides of SignalMesh buy retests; neither chases breakouts | **SAME** |
| **SL** | `entry ∓ SL_ATR × ATR`, `SL_ATR = 1.0` | `autonomous.py:31` | same | **SAME** |
| **TP1 / TP2** | TP1 = the opposite structural level; TP2 = TP1 ± 1 ATR | `desk._rules` | same | **SAME** |
| **Minimum R:R** | `MIN_RR = 1.0`; below it the lane is WAIT with `RR_TOO_LOW`, and **SL is never moved to make it pass** | `autonomous.py:30`, `desk.tf_candidate` | same, and the same refusal | **SAME** |
| **Distance** | in **ATR**: at-zone ≤ 0.25, near ≤ 1.0 | `desk.AT_ZONE_ATR:59`, `NEAR_ATR:60` | same | **SAME** |
| **Staleness** | `STALE_BARS = 3`, age from the bar's **open**, on the market clock; a stale feed yields **no levels** | `scanner.py:29`, `bar_clock.py:41-70` | same, including the refusal | **SAME** |
| **Bias age** | `BIAS_MAX_AGE_H = 24`; beyond it INVALID and unused, never neutral | `scanner.py:28` | same | **SAME** |
| **Closed bars only** | a forming bar never counts | `market_time.closed_only` | same | **SAME** |
| **Minimum history** | 60 closed bars or the structure read is refused | `desk.MIN_BARS_BY_TF:55` | same | **SAME** |
| **Sessions** | ASIA 0–7 · LONDON 7–13 · NEW YORK 13–21 · ASIA 21–24, **fixed UTC, no DST** | `market_time.SESSIONS:15-20` | same | **SAME** — see the note below |
| **Macro convention** | `INVERSE_TO_DXY = {GOLD, SILVER, US100, US30, US500, EURUSD, BTC, ETH}`, described in-file as *a stated convention, not a discovered fact*; no convention → UNKNOWN | `reaction.py:76-84` | same, and the same UNKNOWN | **SAME** |
| **Macro deadband** | a move < `0.25 × ATR` is FLAT, not a direction | `reaction.py:70` | same | **SAME** |

## Group C — the DIFFERENT rows, each declared

These are the rows where Brother and some part of SignalMesh will not agree.
None is a silent divergence; each is named here and must be labelled wherever
it is displayed.

| # | Concept | SignalMesh | AI Helper | Verdict | Reason |
|---|---|---|---|---|---|
| C1 | **Swing length** | Pine 5 · platform scanner 3 | **5** (Pine) | **DIFFERENT from the platform, SAME as Pine** | Owner's decision, 2026-09-17. Pine is the sensor and the methodology. The scanner is not modified. Brother's own read is labelled as its own; the desk's `structure` is quoted as the desk's. |
| C2 | **ATR** | Pine `ta.atr(14)` = **Wilder's RMA** · platform `scanner.atr` = **14-period simple mean** | **Wilder's, matching Pine** | **DIFFERENT from the platform, SAME as Pine** | Follows C1: the mirrored Pine concepts (impulse 1.2/1.8 ATR, `lgZoneTol`, fake breakout 0.4 ATR) are all defined against Pine's ATR, so using the platform's simple mean would silently mis-scale every one of them. Where a **platform** number is quoted (SL, distance in ATR), the platform's own ATR is quoted with it — never recomputed. |
| C3 | **Price source** | Pine reads TradingView · the platform reads MT5 via the reporter | **MT5, through the platform mirror** | **DIFFERENT from Pine** | Unavoidable and not a choice: AI Helper has no TradingView access. Same arithmetic, different bars, so small differences will remain and are data-driven, not method-driven. Must be disclosed wherever a Pine concept is computed. |
| C4 | **DXY / US10Y source** | Pine reads `TVC:DXY` and `TVC:US10Y` (**a yield percentage**) · the platform's `US10Y` is a **dated futures contract** (`UST10Y_U6`) | whatever the mirror provides, **labelled with which one it is** | **DIFFERENT, unavoidable** | Two numbers that move in opposite directions share one name. Brother must never print "US10Y" without saying whether it is the yield or the contract. |
| C5 | **Sessions and DST** | fixed UTC, no DST | fixed UTC, no DST | **SAME, and knowingly imprecise** | New York's session moves an hour twice a year against UTC and SignalMesh does not follow it. Mirroring keeps Brother and the desk in agreement, which is the rule. Fixing it in AI Helper alone would produce exactly the divergence this file exists to prevent. Named, not quietly corrected. |

## What AI Helper does not implement at all

| Concept | Why |
|---|---|
| Anything that places, modifies, routes, cancels or dispatches an order | Iron Rule 3, and the position at the top of this file |
| A signal, a dispatch, or anything an executor could read | Iron Rule 3 |
| A second level ladder | the platform's is the one truth; Brother reads it |
| A breakout (STOP) entry | both sides of SignalMesh buy retests; a STOP lane would be a strategy this system has no evidence for |
| A price from a web search | `web_search` carries `tool:network`; a market read carries `tool:live_data`. Different tools, different permissions, and no path from a snippet to a price field |

## How a future divergence gets caught

Every calculated item Brother produces carries `method` and `source`. For a
Group A concept that is `pine:v18.12/<line>`; for Group B, `platform:<service>`.
When the desk and Brother disagree about the same instrument at the same
instant, those two fields say immediately whether it is C1/C2 (expected, and
which row), C3 (data), or a bug.

If Pine changes, this file is out of date until someone re-reads it. Pine is
frozen at alert-creation time, so that is rare — but "rare" is not "never",
and a mapping nobody re-checks is a mapping that quietly becomes wrong.
