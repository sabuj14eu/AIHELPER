# Market-data inspection — READ-ONLY, 2026-09-17

Inspection only. **Nothing was built, changed or deployed in any repository.**
No migration, no endpoint, no feed. This document ends with a proposal and
stops there.

Every claim below carries a verdict:

- **VERIFIED** — read in the named file at the named line; it is in the code.
- **NOT VERIFIED** — depends on runtime or environment state this session
  cannot see (a `.env` on the Windows box, rows in the production database).
  Named, with the command that would settle it.
- **MISSING** — searched for by name and confirmed absent.

The distinction matters more than usual here. *"The code can store 5m
candles"* and *"5m candles exist for GOLD right now"* are different claims,
and only the first is checkable from a repository. Health endpoints lie; only
the data tells the truth.

---

## A correction, first

My first pass through this inspection reported that FVG, order blocks,
liquidity sweeps, pivots, previous-day high/low and equilibrium **do not exist
in SignalMesh**. That was wrong, and wrong in the most expensive direction: I
grepped `Sniper-System/app/` — the platform's Python — and did not grep
`Sniper-System/pine/`.

**Pine is the sensor. Pine is where the methodology lives.** Every one of
those concepts is defined there, precisely, and has been for many versions.
The platform's Python is the watching layer, and it deliberately implements a
narrower set.

You answered a question of mine on the basis of that wrong finding — you chose
"implement all of them in AI Helper" when I told you there was nothing to
mirror. **There is something to mirror, and it is exact.** The right answer is
now the one requirement 16 asks for: mirror Pine. I have set out each
definition below so you can decide again with the real facts.

---

## 1. Where does live market data already exist?

**VERIFIED.** One place, real feeds only.

| | | |
|---|---|---|
| Store | `candles` table, unique on (symbol, tf, ts) | `Sniper-System/app/models/trading.py:161-180` **VERIFIED** |
| Producer | MT5 reporter on the Windows box | `agents/mt5_reporter/mt5_reporter.py` **VERIFIED** |
| Path | `POST /api/v1/heartbeat/candles` | `app/routers/api_v1.py:291` **VERIFIED** |
| Cadence | `BB_INTERVAL_SECONDS`, default **60 s**, 100 bars per symbol/tf per push | `mt5_reporter.py:53`, `:639` **VERIFIED** |
| Columns | `symbol, tf, ts, open, high, low, close, volume, spread, source` | `trading.py:168-180` **VERIFIED** |
| `ts` meaning | the bar's **OPEN** time, UTC | `bar_clock.py:45-46` **VERIFIED** |
| `volume` | MT5 **tick volume**, not traded volume | `mt5_reporter.py:592` **VERIFIED** |
| `source` | `mt5:<login>` — feeds are never silently merged | `trading.py:178-180` **VERIFIED** |

A second, independent producer exists in Pine: the indicator reads
`TVC:DXY` and `TVC:US10Y` directly from TradingView
(`BrotherSniperULTIMATE_v18_FINAL_v6.pine:580, 722, 735, 346`) **VERIFIED**.
That data reaches the platform only as fields inside an alert payload, never
as candles.

**Whether rows are actually arriving for any given symbol right now:
NOT VERIFIED.** Settle it on the box:

```
docker compose exec -T postgres psql -U brotherbot -d brotherbot -c "SELECT symbol, tf, count(*), max(ts) FROM candles GROUP BY symbol, tf ORDER BY symbol, tf;"
```

## 2. Can AI Helper access it safely and read-only?

**VERIFIED: no, not today — and the blocker is authentication, not the data.**

| Endpoint | Auth dependency | Reachable with an API key |
|---|---|---|
| `/api/v1/me`, `/portfolio`, `/stats`, `/trades`, `/signals` | `api_user` | **yes** — `api_v1.py:21-58` **VERIFIED**; these are exactly what `AIHELPER/app/tools/live.py:378-381` reads today **VERIFIED** |
| `/api/v1/heartbeat/*` | `api_user_write` | write only |
| `/chart/candles.json` | **`current_user`** (browser session) | **no** — `app/routers/chart.py:51-53` **VERIFIED** |
| `/chart/levels.json` | **`current_user`** | **no** — `chart.py:155-157` **VERIFIED** |

`grep -rn "api_user" app/routers/*.py | grep -v api_v1` returns **nothing**
**VERIFIED** — there is no other API-key-readable surface anywhere.

So the candle store and the level engine are exposed to a logged-in browser
and to nothing else. An API key cannot read one candle. **That is the whole of
AIH-1: not a missing key, a missing endpoint.**

On safety, if such an endpoint is added: reading is safe by construction. The
platform's own Iron Rule 1 is that nothing in it dispatches
(`Sniper-System/CLAUDE.md`) **VERIFIED**, and AI Helper's Iron Rule 3 is
advisory-only. A GET calling an existing service touches no order, no risk
limit, no lot size and no executor.

## 3. Which instruments are available?

**NOT VERIFIED — and it cannot be verified from any repository.**

The live list is `BB_CANDLE_SYMBOLS`, an environment variable on the Windows
box, **defaulting to empty** (`mt5_reporter.py:76`) **VERIFIED**. With it
empty, `push_candles` returns immediately and **nothing is pushed at all**
(`mt5_reporter.py:629-630`) **VERIFIED**.

What the repositories name as canonical:

| Symbol | Evidence | Verdict |
|---|---|---|
| GOLD, SILVER, US100, EURUSD | enabled in `scripts/seed.py:71`, `:130` | **VERIFIED** as canonical names |
| BTC | `seed.py:130` | **VERIFIED** as a canonical name |
| DXY, OIL | bias seed `seed.py:172`; `reaction.py:59`, `:83` | **VERIFIED** as canonical names |
| US10Y | `reaction.py:60`, maps to a **dated** contract (`UST10Y_U6` today) | **VERIFIED** |

Of the five you asked for — GOLD, SILVER, US100, DXY, OIL — all five are
canonical names in the system. **Whether any of them is in the push list is
NOT VERIFIED.** Settle it on the Windows box:

```
type C:\<reporter dir>\.env | findstr BB_CANDLE
```

## 4. Which timeframes are available?

| Timeframe | Verdict | Evidence |
|---|---|---|
| 1m | schema yes, **not pushed by default** | `trading.py:170`; reporter default excludes it |
| **5m** | **MISSING by default** | `mt5_reporter.py:556` default `BB_CANDLE_TFS="15m,1h,4h,1d"` **VERIFIED**; `desk.py:44-46` states *"5m candles are not stored today"* **VERIFIED**; `reaction.py:65-66` carries a 5m/15m fallback for the same reason **VERIFIED** |
| 15m | **VERIFIED** available | reporter default |
| 1h | **VERIFIED** available | reporter default |
| 4h | **VERIFIED** available | reporter default |
| 1d | **VERIFIED** available | reporter default |

Four of the five timeframes you asked for are available. **5m is one
environment variable on the bot box — `BB_CANDLE_TFS` — not a code change**;
MT5's `TIMEFRAME_M5` is already mapped (`mt5_reporter.py:549`) **VERIFIED**.

The desk currently serves its "scalp" horizon from 15m with a 12-bar lookback
and says so on the page (`desk.py:44-52`) **VERIFIED**.

## 5. How fresh is the data?

**VERIFIED**, and the rule is stricter and more honest than a wall-clock age.

- `gate_age_min` = minutes since the bar's **OPEN**, measured against
  `market_reference_time(symbol)`, which is weekend- and session-aware
  (`bar_clock.py:41-70`, `market_time.py:106`) **VERIFIED**.
- `STALE_BARS = 3` (`scanner.py:29`) **VERIFIED**. Fresh means
  `age ≤ 3 × bar minutes`: **45 min on 15m**, 180 min on 1h, 720 min on 4h.
- A stale feed produces **no levels at all**, never a level with a warning
  beside it (`desk.py:20-21`, and `DATA_STALE` short-circuits
  `tf_candidate`) **VERIFIED**.
- `BIAS_MAX_AGE_H = 24`; beyond that the bias is INVALID and unused, never
  neutral (`scanner.py:28`, `bias_freshness`) **VERIFIED**.
- A forming bar never counts (`market_time.closed_only`) **VERIFIED**.

**The practical floor is minutes, not seconds.** The push runs every 60 s but
carries closed 15m bars. The `DATA AGE: 4 seconds` in your example is not
achievable from this source, and nothing in the system could produce it.

## 6. Is bid/ask available?

**MISSING.**

`Candle.spread` (nullable) carries MT5's per-bar spread in points
(`trading.py:177`, populated at `mt5_reporter.py:592`) **VERIFIED**. That is
the entire quote-side story:

- bid — **MISSING**
- ask — **MISSING**
- mid / tick / any sub-bar price — **MISSING**

Searched: `grep -rn "bid\|ask\|tick" app/services/` returns only unrelated
matches (tick *precision*, tick *volume*) **VERIFIED**.

Consequence: any "current bid/ask" Brother displayed would be invented. The
authoritative price available to Brother is **the last closed bar's close,
with its age** — which is what the whole platform already uses everywhere.

## 7. Are DXY and US10Y available?

**Partly — and the two systems disagree about where they come from.**

| | Platform (Python) | Pine |
|---|---|---|
| DXY | canonical symbol `DXY`; **bias trend + state only**, not price (`decision_snapshot.py:69-75`) **VERIFIED** | reads `TVC:DXY` directly, daily close + EMA10/EMA20 (`pine:722`), and 1-minute series (`pine:580-582`) **VERIFIED** |
| US10Y | canonical `US10Y` → a **dated futures contract** (`UST10Y_U6` today), `reaction.py:55-60` **VERIFIED** | `input.symbol("TVC:US10Y")` — the **yield index** (`pine:346`) **VERIFIED** |

`app/services/reaction.py` is already the macro layer, with the discipline
you asked for **VERIFIED**:

- `INVERSE_TO_DXY = {GOLD, SILVER, US100, US30, US500, EURUSD, BTC, ETH}` —
  described in the file as *"a stated convention, versioned with the ruleset,
  not a discovered fact"*; an asset with no stated convention yields UNKNOWN
  (`reaction.py:76-84`).
- `DEADBAND_ATR = 0.25`: a move smaller than this is FLAT, not a direction
  (`reaction.py:70`).
- `macro_feed_health` reports whether each leg answers at all
  (`reaction.py:344`).

**The trap worth naming:** Pine's `TVC:US10Y` is the 10-year *yield* (a
percentage). The platform's `US10Y` is a *futures contract price*. These are
different numbers that move in opposite directions, and they share a name.
Whichever Brother reads, it must carry which one it is. **VERIFIED** from both
files.

So: direction and freshness for both legs, yes. A DXY *price* only if `DXY` is
in the push list (**NOT VERIFIED**). A US10Y *yield percentage*: **MISSING**
from the platform.

## 8. Does SignalMesh already calculate structure and levels?

**VERIFIED: yes — in two places, with two different swing definitions.**
That second fact is the most important line in this document.

### 8a. The platform's Python (the watching layer)

| What | Where | Definition | Verdict |
|---|---|---|---|
| Swing high/low | `scanner.structure_state:95-114` | fractal, **`swing = 3`** either side (bar is the extreme of its 7-bar window) | **VERIFIED** |
| Trend structure | same | `HH/HL` · `LH/LL` · `MIXED`, from the **last two** confirmed swings | **VERIFIED** |
| ATR | `scanner.atr:54-61` | 14-period **simple mean** of true range (not Wilder) | **VERIFIED** |
| Range high/low | `desk.tf_candidate` | max high / min low over the horizon's lookback | **VERIFIED** |
| Horizons | `desk.HORIZONS:47-54` | scalp 15m/12 · session 1h/24 · swing 4h/40 · intraday 15m/40 | **VERIFIED** |
| **Level ladder** | `brief._survey:84-127` | recent high/low (15m 40-bar), session high/low, each horizon's high/low — deduped, sorted, **each carrying tf + lookback + source**. Described in-file as *"one level engine, one truth"* | **VERIFIED** |
| ATR per timeframe | `_survey` → `atr_by_tf` | already multi-timeframe | **VERIFIED** |
| **Structure per timeframe** | `_survey` → `structures` | **already the MTF agreement input you asked for** | **VERIFIED** |
| Session | `market_time.SESSIONS:15-20` | ASIA 0–7, LONDON 7–13, NEW YORK 13–21, ASIA 21–24 — **fixed UTC, no DST** | **VERIFIED** |
| Session high/low | `session_center.build_session_view` | today's extremes | **VERIFIED** |
| Entry/SL/TP | `desk._rules:165-176` | **HH/HL → BUY LIMIT at range low**; SL = entry − 1.0 ATR; TP1 = range high; TP2 = TP1 + 1 ATR (mirrored for LH/LL) | **VERIFIED** |
| `SL_ATR` / `MIN_RR` | `autonomous.py:30-31` | **1.0 / 1.0** | **VERIFIED** |
| Minimum bars | `desk.MIN_BARS_BY_TF:55` | 60 closed bars or the structure read is refused | **VERIFIED** |
| Distance | `desk.distance_note`, `AT_ZONE_ATR=0.25`, `NEAR_ATR=1.0` | in **ATR**, so it scales with the instrument | **VERIFIED** |
| Everything, once | `decision_snapshot.build_decision_snapshot:41` | ONE market read shared by every consumer, *"so two lanes can never disagree about the same instant"* | **VERIFIED** |

### 8b. Pine (the sensor — where the SMC methodology actually lives)

All **VERIFIED** in `pine/BrotherSniperULTIMATE_v18_FINAL_v6.pine`:

| Concept | Line | Definition, exactly |
|---|---|---|
| Swing | 800-801, 216 | `ta.pivothigh(high, length, length)` with **`length = 5`** |
| Structure state | 834-844 | `smHH and smHL → "UP"`, `smLH and smLL → "DOWN"`, else `"TRANSITION"` |
| CHoCH | 900-901 | `close` crosses the **last swing** against the prevailing trend. The file records that an earlier version never fired once, so the veto protected nothing |
| BOS | 394 | labelled from the same swing breaks |
| **FVG** | 1020-1021 | bull: `low > high[2]` · bear: `high < low[2]` (a three-bar gap) |
| FVG mitigation | 1041-1047 | a **fully-filled FVG is dead structure** and is cleared. Added in v18.5 because stale zones made the gate fire into news moves |
| **Order block** | 1060-1073 | `impulseUp = close>close[1]>close[2] and (close−close[2]) > 1.2×ATR`; `bullOB = impulseUp and open[2] > close[2]` (the last down candle before the impulse). **Strong** = the same with 1.8×ATR |
| **Liquidity sweep** | 1139-1140 | `low < lastLow − pipZone and close > lastLow and (close−low) > 0.6×(high−low)`, and ≥3 bars since the last one |
| **Pivots** | 865-871 | classic floor pivots from the **previous daily** H/L/C: `PP=(H+L+C)/3`, R1/R2/R3, S1/S2/S3 |
| **PDH / PDL** | 613-614 | `request.security(tickerid, "D", high[1]/low[1])` |
| **Range high/low** | 846-851 | the last confirmed swing high and swing low |
| **Equilibrium** | 853-857 | `(rangeHigh + rangeLow) / 2`; above = **PREMIUM**, below = **DISCOUNT** |
| Location Gate tolerance | 1382-1383 | `f_znUp(lvl) = high ≥ lvl − lgZoneTol and close ≤ lvl + lgZoneTol` |
| Zones the gate accepts | 1394-1396, 1405 | swing, pivot (PP/R1/R2/S1/S2), PDH/PDL, range edge, equilibrium, EMA20 in trend mode |
| Fake breakout | 1166-1167 | `high > rangeHigh and close < rangeHigh and (high−close) > 0.4×ATR` |

v7 records the same vocabulary: `learning/telemetry.py:48` lists
`["bos", "choch", "fvg", "liquidity_sweep", "order_block", ...]` **VERIFIED**.

### 8c. The finding that matters

**SignalMesh already contains two swing definitions.** Pine uses
`length = 5`; the platform's scanner uses `swing = 3`. They will disagree
about which bars are swings, and therefore about structure, range edges and
equilibrium, on the same chart at the same moment.

This is not a defect I was asked to fix and I have not touched it. But it
decides what "mirror SignalMesh" can even mean: **there is no single
SignalMesh answer to mirror — there are two, and they have different
authority.** Pine is the sensor and is frozen at alert-creation time; the
platform's Python is the watching layer and changes freely.

## 9. What exactly does AIH-1 need to expose to Brother?

Four read-only GETs, each a thin wrapper over a function the dashboard already
calls on every page load, on the **existing** `api_user` Bearer dependency:

| Endpoint | Returns | Serves which of the 12 inputs |
|---|---|---|
| `GET /api/v1/market/candles?symbol=&tf=&n=` | closed candles: ts, o, h, l, c, volume, spread, source | our own calculations, and any audit of the platform's |
| `GET /api/v1/market/snapshot?symbol=` | `build_decision_snapshot` + `brief.level_ladder` + `atr_by_tf` + `structures` | 1 price · 2 news · 3 macro · 4 structure · 5 session · 6 levels · 12 data quality |
| `GET /api/v1/market/desk?symbol=` | `desk_view` lanes: entry, SL, TP1/TP2, RR, WAIT reason codes, distance in ATR, invalidation, validity | 7 location · 8 buy · 9 sell · 10 R:R · 11 invalidation |
| `GET /api/v1/outlook?symbol=` | the posted outlook and its levels | **AIH-6** |

None writes, computes anything new, or touches an order, a risk limit, a lot
size or an executor.

**Smallest safe version**, if you want to start with one endpoint: `snapshot`
alone covers seven of the twelve inputs and is the single call that already
guarantees internal consistency — it is described in-file as ONE market read
shared by every consumer, which is exactly the "one truth" property you asked
for. `desk` is the second most valuable. `candles` is only needed if AI Helper
is to calculate anything itself. `outlook` is AIH-6 and is independent.

## 10. What is missing?

| # | Missing | Verdict | Where it would be fixed | Blocking |
|---|---|---|---|---|
| 1 | API-key-readable market endpoints | **MISSING** | Sniper-System, four GETs | **yes — AIH-1 and AIH-6 cannot be finished without this** |
| 2 | `TRADING_PLATFORM_API_KEY` in AI Helper's `.env` | **NOT VERIFIED** (owner said empty) | `/api-access` page, owner action | **yes** |
| 3 | 5m candles | **MISSING by default** | `BB_CANDLE_TFS` on the bot box | no — 15m/1h/4h/1d is enough to start |
| 4 | Which symbols are actually pushed | **NOT VERIFIED** | `BB_CANDLE_SYMBOLS` on the bot box | unknown until checked |
| 5 | Bid / ask / tick / sub-bar price | **MISSING everywhere** | nowhere — no component has it | no, but Brother must answer UNAVAILABLE and never invent one |
| 6 | US10Y as a yield percentage | **MISSING** from the platform (Pine has it) | — | no, but must never be labelled a yield if it is the futures price |
| 7 | FVG / OB / sweep / pivots / PDH-PDL / equilibrium in the **platform** | **MISSING** from Python, **VERIFIED present in Pine** | see the decision below | no |
| 8 | One swing definition | **two exist** (Pine 5, scanner 3) | a decision, not a gap | no, but it must be chosen deliberately |
| 9 | DST-aware sessions | **MISSING by design** (fixed UTC) | a decision | no |
| 10 | Any candle rows at all, for any symbol | **NOT VERIFIED** | the production database | **possibly — check first** |

---

## Success condition: can we get ONE market-data truth mirrored read-only?

**Yes, with one change, and the change is small.**

The data, the calculations, the freshness discipline and the level engine all
already exist and are already treated as a single source of truth inside the
platform. Nothing needs to be computed twice and no second feed is needed.
What is missing is an API-key-readable door onto what is already there.

```
MARKET DATA (platform candles + snapshot + desk + outlook, read-only)
        │
        ├──────────────► TRADING CONTEXT ◄──────── WEB RESEARCH (SearXNG,
        │                      │                    trusted tiers — news,
        │                      │                    CPI/PCE/NFP, macro facts)
        │                      ▼
        │            deterministic calculations
        │                      ▼
        │            local model interpretation
        │                      ▼
        │              pending-order scenario
        ▼
  authoritative price: last CLOSED bar + its age. Never a web snippet.
```

The separation you asked for is already enforceable in code, not only by
convention: `web_search` carries `tool:network` and is gated by
`app/tools/egress.py`; a market reader would carry `tool:live_data` and read a
fixed operator-configured URL. They are different permissions on different
tools, and nothing lets a search result reach a price field.

---

## Three decisions this inspection puts back to you

**1. The four endpoints.** You approved these in principle earlier in this
session. They are not built, and will not be until you say so after this
review.

**2. Order type — settled, and worth re-stating with the evidence.** You chose
to mirror SignalMesh. The platform's `desk._rules` is a **pullback LIMIT**
strategy (HH/HL → BUY LIMIT at the range low), and Pine's Location Gate is
also a retest gate — *"structure: S/R swing, FVG, Order Block, pivot, prev-day
H/L, range edge, equilibrium, or a fresh liquidity sweep. No more chasing
mid-move"* (`pine:286-287`). Both sides of SignalMesh agree: this system buys
retests, it does not chase breakouts. Your decision matches the evidence.

**3. FVG / OB / sweep / pivots / PDH-PDL / equilibrium — please decide again.**
You chose "implement all of them in AI Helper" when I had told you no
definition existed. That was my error. Pine defines every one of them, exactly,
and the definitions are transcribed in section 8b above. The options are now:

- **Mirror Pine's definitions** (recommended). Requirement 16 satisfied
  literally: same FVG, same OB, same sweep, same pivots, same equilibrium.
  Brother and the sensor cannot disagree. The cost is that Pine runs on
  TradingView's data and AI Helper would run the same arithmetic on MT5
  candles, so small differences remain possible from the data, not the method.
- **Mirror only what the platform's Python computes** and answer UNKNOWN for
  the rest — the narrowest, least useful, and safest option.
- **Keep your original answer** and let AI Helper define them independently.
  I would build it, and every AI-Helper-originated definition would be tagged
  `AI_HELPER_ONLY` so a divergence is visible rather than silent — but I would
  be inventing a second methodology next to one that already exists.

**And one prior question that section 8c raises:** Pine's swing length is 5,
the platform's is 3. Which is Brother's? They give different structure reads
on the same bars.

---

## To move the NOT VERIFIED items to VERIFIED

Three commands, all read-only, run on the boxes:

> **The checkout directory.** Every `cd` below uses
> `/home/shyam/ai-helper`, which is what `docs/HANDOFF_BROTHER_SESSION.md`
> recorded from the box. If that path does not exist, find it once and use
> what it prints instead:
>
> ```
> ls -d ~/ai-helper /opt/ai-helper ~/AIHELPER 2>/dev/null; docker compose ls | grep -i ai-helper
> ```


**On the Contabo box** — is there any candle data at all, and how fresh:

```
docker compose exec -T postgres psql -U brotherbot -d brotherbot -c "SELECT symbol, tf, count(*) AS bars, max(ts) AS newest FROM candles GROUP BY symbol, tf ORDER BY symbol, tf;"
```

**On the Windows box** — what is actually being pushed:

```
type C:\<reporter dir>\.env | findstr BB_CANDLE
```

**On the Contabo box** — does AI Helper have a platform key yet:

```
cd /home/shyam/ai-helper && grep -c "^TRADING_PLATFORM_API_KEY=.\+" .env
```

Expect `1` if a key is set, `0` if it is empty. **Do not paste the key.**
