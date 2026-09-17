# The market mirror — API contract

Two halves of one read path, added 2026-09-17 for AIH-1 and AIH-6.

```
SignalMesh (authority, owns the data)        AI Helper (read-only consumer)
  GET /api/v1/market/candles     ◄─────────   GET /api/v1/market/candles
  GET /api/v1/market/snapshot    ◄─────────   GET /api/v1/market/snapshot
  GET /api/v1/market/desk        ◄─────────   GET /api/v1/market/desk
  GET /api/v1/outlook            ◄─────────   GET /api/v1/outlook
```

**AI Helper is not a second trading bot.** SignalMesh remains the trading
authority and the executor. Neither half computes a price, stores one, or
decides anything from one.

---

## Platform side (`Sniper-System/app/routers/api_v1.py`)

Auth: `Authorization: Bearer bb_...` via `api_user` — the **read** dependency.
`api_user_write` is the one that demands the `write` permission, so a key with
no permissions at all reads the mirror and can write nothing. Least privilege
by construction, not by convention.

Every response carries this envelope:

```jsonc
{
  "symbol": "GOLD",
  "as_of": "2026-09-17T09:14:22+00:00",
  "price_source": "MT5 via mt5_reporter (broker feed), stored as closed candles",
  "instrument": { "kind": "price", "note": "" },
  "quote": {
    "state": "UNAVAILABLE",          // always — see below
    "bid": null, "ask": null,
    "note": "no bid/ask/tick exists anywhere in this system ..."
  },
  "session": {
    "now": "LONDON",
    "convention": "fixed UTC hours, no DST adjustment",
    "windows": [{ "name": "ASIA", "from_h": 0, "to_h": 7 }, ...]
  },
  "read_only": true
}
```

`quote.state` is **always** `UNAVAILABLE`. The platform has never stored a bid,
an ask or a tick — only a per-bar `spread`. The keys are present rather than
omitted on purpose: an omitted key reads as *"not reported this time"*, and
`UNAVAILABLE` says it is never reported, which is a different and more useful
fact.

`instrument.kind` is `futures_price` for **US10Y**, with a note saying it is a
dated futures contract and not the 10-year yield percentage. Pine's
`TVC:US10Y` is the yield. The two move in opposite directions and share a name.

### `GET /api/v1/market/candles?symbol=&tf=&n=`

| | |
|---|---|
| `tf` | `1m 5m 15m 30m 1h 4h 1d`; anything else is **400**, never an empty list |
| `n` | 1…1000, default 300 |
| Order | oldest first |
| Bars | **closed only** — a forming bar is not a fact yet |
| Source | the `candles` table, written only by the MT5 reporter |

```jsonc
{ ...envelope,
  "tf": "15m", "count": 300,
  "freshness": { "state": "LIVE", "age_min": 12, "limit_min": 45,
                 "rule": "bar-clock-v1", "basis": "...",
                 "newest_bar": "09:00–09:15 UTC", "note": "" },
  "candles": [{ "ts": "2026-09-17T09:00:00+00:00", "open": 4268.1,
                "high": 4272.4, "low": 4266.0, "close": 4271.5,
                "tick_volume": 812, "spread": 12.0, "source": "mt5:52901228" }]
}
```

`tick_volume`, not `volume`: MT5 gives tick count, not traded size, and a
consumer must not reason about liquidity from it.

Every `ts` leaves with `+00:00` on it, always. The column is timezone-aware in
PostgreSQL but naive in SQLite, and an ISO string with no offset is read as
**local** time by every consumer that parses it — a whole series silently
shifted by the reader's timezone. That is the clock incident in miniature, so
the stamp is made aware on the way out rather than trusted from the driver.

No rows is an explicit answer, not an empty success:

```jsonc
{ "count": 0, "candles": [],
  "freshness": { "state": "UNKNOWN", "age_min": null, "limit_min": 45,
                 "note": "no closed 15m candles stored for NOSUCHSYMBOL" } }
```

`age_min` is `null` rather than `0`, because `0` reads as *fresh* and there is
no bar to be fresh.

### `GET /api/v1/market/snapshot?symbol=`

`build_decision_snapshot` unchanged, plus `brief.level_ladder`, plus a
`methodology` block. The snapshot is described in its own file as ONE market
read shared by every consumer, *"so two lanes can never disagree about the same
instant"* — handing it out unchanged is the point; recomputing anything here
would create the second reader it exists to prevent.

```jsonc
{ ...envelope,
  "snapshot": { "meta": {...}, "freshness": {...}, "market": {...},
                "news": {...}, "macro": {...}, "history": {...} },
  "levels": { "state": "OK", "ladder": [...],
              "engine": "brief.level_ladder (the platform's one level engine)" },
  "methodology": {
    "swing": "platform scanner swing=3 (Pine uses 5 — row C1)",
    "atr": "platform scanner.atr = 14-period SIMPLE mean (Pine uses Wilder/RMA — row C2)",
    "note": "these are the PLATFORM's values. A consumer mirroring Pine must not relabel them."
  } }
```

That `methodology` block is not decoration. A consumer mirroring Pine's method
on this platform's data has to know which numbers are whose, or it will
present a swing-3 structure as a swing-5 read and nobody will be able to tell.

### `GET /api/v1/market/desk?symbol=`

`desk_view` unchanged, with its label attached so it cannot be lost in
transit:

```jsonc
{ ...envelope, "desk": { "lanes": [...], "plan": {...}, "drift": {...} },
  "authority": {
    "lanes": "PAPER RESEARCH — never READY, never sent to an executor",
    "production_plan": "the `plan` key is the validated planner output",
    "consumer_note": "a reader may explain these; it may not act on them" } }
```

### `GET /api/v1/outlook?symbol=`  (AIH-6)

`outlook.board` unchanged: weekly and monthly rendered against one measured
price so the two cannot disagree about "now", and a refusal rather than a
fallback if storage returns a different symbol than was asked for.

---

## AI Helper side (`app/api/routes/market.py`, `app/market/mirror.py`)

Auth: the ordinary client API key (`current_client`). Reading the market is not
an administrative act, so no admin scope is required.

Same four paths. Every response is the same two-part shape:

```jsonc
{
  "mirror": {
    "endpoint": "snapshot",
    "state": "OK",               // OK | NOT_CONFIGURED | UNREACHABLE | REFUSED
    "note": "",
    "read_at": "2026-09-17T09:14:23+00:00",
    "params": { "symbol": "GOLD" },
    "freshness": { "state": "LIVE", "age_min": 12, "limit_min": 45 },
    "usable": true,
    "source": "SignalMesh platform (read-only mirror)"
  },
  "data": { ...whatever the platform returned, unchanged... }
}
```

**`state` is a word, not a sentence**, because a caller branches on it:

| state | meaning | fix |
|---|---|---|
| `OK` | the platform answered | — |
| `NOT_CONFIGURED` | no `TRADING_PLATFORM_URL` / `_API_KEY` | set them (AIH-1) |
| `UNREACHABLE` | timeout, transport error, non-JSON body | the platform or the network |
| `REFUSED` | 401 (key rejected) or another non-200, with the platform's own detail passed through | the key, or the request |

"The key is wrong" and "the platform is down" have opposite fixes, so they are
not the same state.

**`usable` is `true` only when `freshness.state == "LIVE"`.** STALE is not a
degraded yes: the platform's own rule is that a stale feed produces no levels
at all, and a mirror that softened that would be the first place the Freshness
Law leaked. When the platform reports no freshness at all, the mirror reports
`UNKNOWN` rather than assuming fine — guessing *fresh* is the dangerous guess.

`data` is `null` on any non-`OK` state. It is never `{}`, and never partially
filled with something the mirror worked out.

### What the mirror cannot do

- **Write.** Four GETs, no body, and a test asserts every request is a `GET`.
- **Reach anywhere else.** A caller names an endpoint from a fixed table, never
  a URL, so no input can steer it at another host or route.
- **Invent.** No price, no bid, no ask, no level is ever added to `data`.
- **See a web search.** `app/market/mirror.py` imports nothing from the
  research or web-search modules, and a test reads the import graph to prove
  it. A snippet saying *"gold is around 4270"* has no path to a price field.

---

## Configuration

```
TRADING_PLATFORM_URL=https://signalmesh.dev
TRADING_PLATFORM_API_KEY=bb_...        # a READ key: create it with no permissions
```

Create the key on the platform's `/api-access` page **with the write box
unticked**. The mirror needs no write scope and must not be given one.

## Verification

| # | Claim | Where |
|---|---|---|
| 1 | each endpoint requires the intended auth | `Sniper-System/tests/test_api_market_mirror.py::TestAuthentication`, `AIHELPER/tests/integration/test_api.py::TestTheMarketMirrorEndpoints` |
| 2 | GET / read-only | `TestReadOnly`, `test_no_write_verb_exists`, `test_every_request_is_a_get` |
| 3 | real candle rows are read | `TestCandlesAreRealRows` (rows written directly, then read back through HTTP) |
| 4 | timestamps and freshness correct | `test_every_timestamp_carries_its_utc_offset`, `test_freshness_is_reported_with_its_rule_and_its_limit`, `test_a_forming_bar_is_never_returned` |
| 5 | symbol/timeframe mapping | `test_every_known_timeframe_is_accepted`, `test_an_unknown_timeframe_is_refused_not_answered_empty` |
| 6 | missing data is explicit | `TestMissingDataIsExplicit`, `TestAbsenceIsNamed` |
| 7 | no bid/ask fabricated | `TestNoQuoteIsEverInvented`, `TestNothingIsInvented` |
| 8 | methodology differences explicit | `TestMethodologyDifferencesStayExplicit` |
| 9 | SignalMesh otherwise unchanged | one modified file + one new test; 784 platform tests pass |
| 10 | tests cover the endpoints | 61 platform + 58 AI Helper |
