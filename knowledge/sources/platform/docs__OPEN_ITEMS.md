---
title: Sniper-System open items (both sides)
domain: platform
repo: sabuj14eu/Sniper-System
sources: docs/OPEN_ITEMS.md
verified_on: 2026-09-16
commit: 3257184
classification: INTERNAL
---

# OPEN ITEMS — written down so they don't stay "later" forever

## ⚡ START HERE (new session, 2026-09-02 23:30 UTC)

Read CLAUDE.md, then **docs/HANDOFF_PLATFORM_SESSION.md** (the state,
the habits, and the paste-ready opening prompt for a new window), then
this file. Current state in six lines:

- **Platform v5.24 ready (v5.23 LIVE, migration APPLIED 2026-09-03 10:35 UTC):** 8 twin
  groups removed (facts in audit_log as `trade_twin_removed`, 0 refused),
  `uq_trade_ticket` created, `open_rows_for_ticket = 0`. The GOLD ghost
  (#1900277473) cleared on its own — Brain View reads `Open position
  NONE`. 721 tests, branch `claude/brother-bot-trading-platform-58o7gr`.
  No migration pending.
- **Three days of screen-honesty fixes shipped** (v5.14–v5.17): every
  one was a true value under a label answering a different question.
  CHANGELOG 5.16 and 5.17 are the working description of how this
  system fails.
- **FAIL-SOFT now visible (v5.18):** the mirror carries `fail_soft` keys
  and every decision row renders `TRADED WITHOUT COUNCIL, fail-soft
  n/2`. The policy is the brain's bounded exception to Iron Rule 1;
  keeping it is Shyam's call, not either session's.
- **Still owed by the platform:** PLAT-HOLDOUT-1, the startup schema
  guard, and a legend audit (render every documented desk state once).
- **Bias gaps CLOSED (2026-09-03 09:30 push):** SILVER and US100
  refreshed once the bridge served enough bars, XRP was already LIVE —
  the v5.15 prediction held. XRPUSD/USA500/USOIL RETIRED by Shyam's
  decision (C11 done).
- **Nothing about the trading logic changed and nothing may.** Every
  v5.16/5.17 rename kept its threshold; see EVIDENCE AUTHORITY.

### WATCH-ITEMS (opened 2026-09-02, observation only — no building)

Three things to LOOK at, none urgent, none a fix. Each carries the
condition that turns it into a finding, because a watch-item without a
falsifier is just a worry.

1. **Outlook scorecard grades after expiry — verified by design, not a
   bug.** `scorecard()` filters `Outlook.valid_until < now` and passes
   its candles through `closed_only(..., "1d")`, so an ACTIVE outlook is
   never graded (marking your own exam halfway) and a forming daily
   never grades a thesis. The current weekly (written 26 Aug) expires
   2026-09-02 18:08 UTC. **Finding if:** it has not appeared in the
   scorecard by the morning of 2026-09-03, after the window's last daily
   candle has closed.
2. **Auto-weekly successor at the 18:08 expiry.** The bot box's
   auto-weekly should post a successor outlook. **Finding if:** the desk
   shows a GAP instead — which is the honest display, and the signal to
   nudge the bot box. Nothing on this side may invent a successor.
3. **UNSTAMPED sensor count must stop growing.** `sensor_versions` reads
   `pine_ver` out of the verbatim `raw_payload`, so no ingest change was
   needed — the mirror forwarding it is the whole fix. Baseline at
   2026-09-02: **439 unstamped · 17 v18.12 · 15 session_caller**, with
   the unstamped window running to 02 Sep. **Finding if:** the unstamped
   count keeps climbing this week — that means the mirror fix is not
   live, and it is a bot-side relay, not a platform fix. **Pass if:** it
   freezes at 439 and new rows arrive stamped 18.13.

Not watch-items, because they are the design working and need no
follow-up: the monthly outlook reads ABSENT because nobody wrote one
(the desk never invents an opinion); the desk price trails the live tick
because it reads only CLOSED bars, each stamped with its age.

### C10 — US10Y IS THE YIELD. DECIDED ONCE, RECORDED (2026-09-02)

Two different series have worn one name. Pine's `yield_dir` describes the
US 10-year **YIELD**; the broker's UST10Y candles were the **T-NOTE
PRICE**, and the two move INVERSELY. Averaging or comparing them under a
single symbol would not be noisy — it would be backwards.

**The decision: `US10Y` means the YIELD, permanently.** Any future
note-PRICE series gets its own name (`UST10Y_PRICE` or similar) and its
own row. This is append-only like every other naming decision: the
meaning of an existing name is never re-pointed, because history stored
under it was measured against the old meaning.

Consistent with the two facts already recorded: the note-price feed is
RETIRED (broker roll, no successor, v5.05), and the alias map still
folds broker spellings of the yield onto `US10Y`. Nothing to migrate —
the decision exists so the NEXT person to add a bond series does not
quietly reuse the name.

### C11 — DEAD ROWS USOIL / XRPUSD / USA500: SHYAM'S CALL, STILL OPEN

The board names them UNREACHABLE (v5.03) and opens no incident. Merging
or deleting destroys stored history, so it stays a human decision made
once and logged. No deadline; the current state costs nothing and hides
nothing.

### BIAS PUSH GAPS — ROOT-CAUSED BOT-SIDE, c378012 (2026-09-02)

The recurrence named in platform v5.15 has a diagnosis, and it was TWO
faults wearing one symptom — which is exactly why restarting never held:

1. **XRP: structural.** It was journal-only, not in the core
   candle-derived list, so it went silent whenever Pine did. Nothing was
   broken; it was never wired to be continuous. **Fix:** XRPUSD joins
   the core list.
2. **SILVER and US100: a silent failure.** Both ARE in the core list;
   their fresh read returned nothing — under 210 bars, or an invalid
   EMA/ATR — **and logged no line at all.** An empty read that says
   nothing is indistinguishable from a read nobody made, which is the
   same class of fault as a health endpoint returning 200 while placing
   nothing. **Fix:** every empty read now logs its reason, with a
   per-cycle summary, so the next gap is diagnosed from the log instead
   of from a stale Radar row.

**Falsifiable prediction, recorded so it can be checked rather than
assumed:** XRP refreshes on the next cycle; SILVER and US100 refresh
once the bridge serves enough bars. **Finding if:** XRP is still STALE
after a full cycle, or SILVER/US100 stay STALE and the log names no
reason — the second fix exists precisely so a continued gap arrives with
its cause attached. Baseline at the fix: XRP 1d, SILVER 2d, US100 5d.

**Platform side: nothing to change, deliberately.** STALE is the honest
display of a real fact, and the 1-to-5-day naming plus the 5-day
incident threshold stand as shipped (confirmed by the bot side). The
board will show the recovery on its own — a resolved incident with its
recovery time, and OCCURRENCE #N if it returns again.

### EIGHT TWINS, NOT ONE (v5.23 migration, 2026-09-03 10:35 UTC)

The dry run found **8** twin groups, not the 1 the GOLD ghost had
revealed. Same day, same cause — five reporters racing a read-then-
insert — and seven of them had a close land on the right row by luck,
so their twins never surfaced as a ghost. A fault that shows itself
once has usually happened more; the count is in `audit_log`
(`trade_twin_removed`, 8 rows, every field kept).

**Refused: 0.** No group disagreed on symbol or direction, so nothing
here was a mismatch dressed as a twin.

**The partial index now makes this class impossible**, and the
heartbeat adopts the winner's row on collision. The bot side removed
the concurrent writers on 2 September; both halves are closed.

**Watch-item:** `trades` still has no `updated_at`. "When was this row
last touched" stayed unanswerable through the whole investigation.
Cheap column, one migration; add it the next time `trades` is migrated
for any other reason rather than as its own ceremony.

### A RENAME IS NOT DONE UNTIL EVERY READER IS FOUND (v5.20, 2026-09-03)

v5.17 retired `PASSED` from `distance_note` and grepped Python for it.
The chart TEMPLATE still compared `bdist.state == 'PASSED'` to decide
whether a paper candidate draws dashed — so from v5.17 to v5.20 every
far candidate drew as a solid bright line, the exact lie v4.82 fixed.
Nobody noticed because the chart is rendered by a browser, not a test.

**Rule:** when a vocabulary value is retired, grep templates AND
JavaScript AND docs for the literal, not only `.py`. Better: a test that
asserts the retired literal appears nowhere under `app/`. Added for
PASSED; do it for the next one at retirement time, not discovery time.

### A BOOLEAN WEARING A STRING (v5.19, 2026-09-03)

`stage = "ACTIVE"` looked like a state. It was a boolean: "some position
exists". The direction lived in `setup = "SELL ACTIVE"` — display text —
so the next function did `pos = stage == "ACTIVE"` and gave BOTH the
BUY and the SELL card the same POSITION OPEN. One real SELL, two open
cards, for as long as v4.64 has existed.

**The smell to hunt:** a field that can only be equal-compared to one
value. If `x == "ACTIVE"` is the only thing anyone ever asks of `x`, it
is a boolean, and whatever fact it was supposed to carry has already
been dropped one function upstream. Look for the `[0]` next to it.

**What was NOT done:** no side is inferred from a signal, a plan, a bot
state, a level or a journal — the audit's forbidden list. A position
without a broker-reported side renders SIDE_UNKNOWN, named, never
guessed. `position_state` imports nothing so it cannot reach any of
those sources; a test asserts it.

**Legend audit, again.** This is the third screen-vs-legend disagreement
in four days (v5.16 EMA, v5.17 PASSED, v5.19 POSITION OPEN). The
watch-item stands: render every documented card state once. It is now
the top platform debt.

### THE INVERTED LIMIT, AND WHY IT SURVIVED 13 VERSIONS (v5.17, 2026-09-02)

Worth keeping because of HOW it was found and how long it hid.

`distance_note` decided whether a limit had been "passed" with:

    beyond = ("BUY" in ot and last > entry) or ("SELL" in ot and last < entry)

A BUY LIMIT sits BELOW the market and fills when price falls TO it. So
that test flagged the ORDINARY awaiting-a-pullback state of every
candidate this desk generates — and because `PASSED` outranked every
distance past 0.25 ATR, it swallowed AT ZONE / NEAR / APPROACHING / FAR
whole. **The documented vocabulary in the desk legend was effectively
unreachable, and nobody noticed for thirteen versions**, because the
legend and the labels were never read against each other.

**The card contradicted itself in plain sight.** The invalidation line
said *"before the limit fills"* — an unfilled limit — directly below a
label saying price had blown through it. Two engines on one card,
disagreeing, in every screenshot since v4.36.

**Why the test did not catch it: the test was written from the same
wrong model.** v4.36 shipped a genuine finding (a card saying "not a
today setup" beside "TRIGGERED (position open)") and a test that
encoded the author's inverted mechanics as the expected result. A test
written from the same misunderstanding as the code cannot falsify it —
it locks it in and makes it look proven. Watch for this whenever a test
asserts a value rather than a property.

**And the real finding underneath was unfixable as stated.** Price alone
CANNOT tell whether an order at a level filled — that is a broker fact.
v4.36 tried to infer it from which side price sat on; both sides are
ambiguous. The caveat is now stated rather than guessed.

**Watch-item.** The desk's own legend is a spec nothing tests against.
An audit that renders each documented state at least once would have
caught this in v4.36. Not built yet; noted because it is cheap and this
is the second time a screen and its legend disagreed (v5.16 item 2 was
the first).

### ONE CLOCK, TWO ANCHORS (v5.17)

Freshness ages were being measured from a bar's OPEN in the lanes and
from its CLOSE in the session panel — 21m and 6m for the same bar, in
the same snapshot. Both right, neither labelled.

**The fix deliberately did NOT unify the threshold.** Every gate here
has always compared against the open anchor; moving to the close anchor
would widen every freshness window by one whole bar. That is a risk
change, and risk changes are explicit human decisions (Iron Rule 7), not
a side effect of tidying up a display. `bar-clock-v1` computes both,
names which one the gate uses, and prints them together.

**Residual, known:** the session panel judges against the wall clock and
the lanes against `market_reference_time` (which freezes on weekends).
They agree on every trading day and can differ over a weekend. The
reference is carried in the bar-clock dict so it is explicit rather than
silent. Worth unifying only with a measured reason to.

### FOUR LABELS THAT ANSWERED INVISIBLE QUESTIONS (v5.16, 2026-09-02)

Shyam read one live SILVER desk and found four faults. Worth recording
because they were **one fault wearing four costumes**, and the shared
shape is the thing to watch for next time:

> a screen printing a TRUE value under a label that answers a DIFFERENT
> question, with the question invisible.

Not one of them was a wrong number. `news LOW` and `news risk HIGH` were
both correct. `61m since close` and `bar 20:30` were both correct. The
`data LIVE` chip on the 13:00 brief was correct **at 13:00**. In every
case the reader had no way to know which question was being answered,
and read the difference as the page contradicting itself.

**The recurring smell: two facts sharing one word.** UNKNOWN meant both
"no EMA200 exists" and "an EMA200 exists and its label is withheld".
"news" meant three different measurements. STALE meant a broker break,
a dead reporter, a closed market or a young feed. Whenever a vocabulary
is doing two jobs, the screen will eventually look wrong while being
right — and the reader who notices is doing the QA the tests are not.

**What was NOT done, deliberately.** No threshold moved. `symbol_news`
still carries exactly what the planner's NEWS gate has always read (a
test pins it to `build_snapshot`), and the brief's historical cutoff
reuses the existing candle-freshness window rather than inventing a
number. A naming layer that quietly changes a decision is worse than
the confusion it fixes.

**Watch-item, feed diagnosis.** `feed-diag-v1` decides FEED_WIDE vs
SYMBOL_ONLY from the cohort of tracked feeds. It refuses to infer
retirement from silence, and `SYMBOL_ONLY` explicitly cannot separate a
stopped feed from a broker session break — both look identical in
stored candles. **Finding if:** a SYMBOL_ONLY ever turns out to have
been a platform-wide stop (would mean the cohort or the 7-day peer
window is wrong), or FEED_WIDE fires while peers are demonstrably
current. The counts are on screen precisely so this can be checked
rather than trusted.

**Still open here:** the platform has no model of a broker's daily
maintenance break — `market_status` knows weekends only. That is why
the 21:00-ish metals gap can only be reported, not named. Adding one
means asserting broker session hours the platform cannot verify, so it
waits for measured evidence (a per-symbol histogram of when bars
actually stop) rather than a hardcoded table.

### ADDING AN ASSET TOUCHES THREE PLACES (learned 2026-09-02)

NVDA arrived with a full Trade Desk and an EMPTY Daily Market Brief.
Nothing was broken — a hardcoded list simply did not grow when the asset
did. Written down so the next asset costs one checklist instead of one
live discovery:

1. **`SYMBOL_ALIASES`** (`app/routers/webhooks.py`) — the broker name
   must fold onto the canonical one BEFORE the feed turns on, or the
   instrument grows two lineages that may never be merged (v5.03).
2. **`CORE_UNIVERSE`** (`app/routers/scanner_page.py`) — what the Daily
   Market Brief writer iterates (`brief.maybe_refresh`) and what
   `ai_analyst` builds plans and session views for. Absent here means no
   brief, no matter how many candles exist. **Costs AI budget: one brief
   per symbol per session block**, which is why it grows one named asset
   at a time rather than pointing at every tracked symbol.
3. **The reporter's symbol list** (bot side, Windows runtime config) —
   without it there are no candles at all.

Everything else follows the candles on its own: `/desk`, `/chart`,
`/brain-view` and the paper-lane collector all read `tracked_symbols`,
which is `SELECT DISTINCT symbol FROM candles`. `/radar` is the
exception — it lists symbols from `MarketBias`, so it waits on a brain
push.

### NVDA PHASE 0 — BASELINE, WRITTEN DOWN (2026-09-02 ~17:00 UTC)

Three independent shadow populations are collecting on NVDA and NOTHING
can trade it. The decision in ~four weeks is Shyam's; this is the state
it will be measured against, recorded now because a baseline remembered
is a baseline invented.

**Measured at the start:**
- `candles` 15m under `NVDA`: **101 rows**. Under `NVDA.%`: **0**.
- `lane_observations` for NVDA: **6**.
- `market_bias` for NVDA: none yet — so `/radar` shows no NVDA row. That
  is correct: the radar lists symbols from MarketBias, while `/desk`,
  `/chart`, `/brain-view` and the paper-lane collector list symbols with
  stored CANDLES. Two pages, two sources; an empty radar row is not a
  missing feed.

**The three populations, and the one key they share:**
1. Pine alerts — `NASDAQ:NVDA` → `NVDA` (already canonical).
2. Reporter candles — broker `NVDA.NAS-24` → `NVDA` (platform v5.08).
3. v7 paper lanes — canonical name keys the record, broker name only on
   the wire (brother_sniper_v7 `aa16bca`).
All three join on `NVDA`. The Evidence Authority rule needs these
populations independent AND comparable; a differing join key would have
left them independent but incomparable, which reads as agreement failure
rather than what it is.

**Falsifiers — any of these is a finding, not a shrug:**
- ANY row under `NVDA.%` in candles: the two-lineage split the v5.08
  ordering exists to prevent. Report immediately; do NOT merge lineages
  after the fact (v5.03 naming contract).
- Lane observations stop growing while 15m candles keep arriving.
- Trend context still reading "insufficient history" past ~200 closed
  15m bars (~50 hours of market time, so ~3 trading days from 2026-09-02).

**Evidence floors that govern the four-week read:** n<20 is luck, ~100 to
judge, and CANNOT SEPARATE is a first-class outcome. Two populations
agreeing is the standard; one alone is a note.

**Still true until PLAT-EXPOSURE-1 ships:** NVDA and US100 count as TWO
exposures on any page that sums risk, though Nvidia already drives the
US100 earnings playbook. Not a bug — an unmade decision.

### BOT-SIDE RELAYS (measured 2026-09-01 by the engineering watchers)

Numbers, not impressions — these came off the board's first run.

- **US10Y candle feed dead 122h** (INC-0001). Every other tracked symbol
  is current, so this is US10Y alone, not a feed outage.
- **Bias push stopped: USA500 34d, USOIL 20d, XRPUSD 19d** (INC-0002).
  Candles for these are unaffected — a PUSH gap, not a data outage.
- **SILVER and US100 have RECOVERED** and no longer appear in the
  coverage gap. The Pine v18.13 memory fix is confirmed working, by
  measurement rather than by report.
- **Git↔Production reads UNKNOWN** — no service reports `git_commit` in
  its heartbeat yet. The column exists and is read; the boxes have to
  start sending it before that check can ever say MATCH.
- **VPS heartbeat rows are ~38 days old** and identical in age, which is
  either a regression on ~26 July or a seeded row that never had a live
  writer. Unresolved: check whether those rows carry real telemetry
  (`cpu_pct`, `ea_version`) or defaults before treating it as a fault.

### EVIDENCE INTEGRITY ORDER (12 items, received 2026-08-21)
Scope: evidence transparency, NOT strategy. Items 9 and 12 are already
satisfied by today's work (`candle_audit` + the ceremony; no rule was
touched). **ALL 12 SHIPPED as v4.52** — proof:
`app/services/evidence_integrity.py` + `tests/test_evidence_integrity.py`
(16 tests, suite 486) + docs/CHANGELOG.md 4.52. Item status:
1. ✅ **Contamination count, per bucket AND per trend-split** —
   `contamination_report`, rendered on /desk with the `>3 ATR
   WITH-TREND` cell highlighted as load-bearing; CANNOT SEPARATE when
   its CLEAN count is under n=20, counts only, never a re-derivation
   from survivors. ✅ VERDICT READ on the live /desk 2026-08-21 22:47
   UTC: **CLEAN SAMPLE SUFFICIENT** — 492 of 599 with-trend
   observations beyond 3 ATR born outside the incident window. The
   number now exists outside a plan. Re-examination on clean rows
   stays a deliberate human act; the page imposes nothing.
2. ✅ Denominator explicit — `distance_funnel` separates candidates /
   filled / no-fill / resolved / pending / wins / losses; the formula
   prints verbatim on the page; a no-fill flood provably cannot move
   expectancy (regression test).
3. ✅ `distance_provenance` stored at birth on every observation (all
   factors from one candidate dict — numerator and ATR cannot come
   from different snapshots); tf lanes now stamp `entry_dist_atr`.
4. ✅ Items 4–8, 10, 11 — snapshot identity chips per /desk section,
   bucket labels with units/bounds, sample-strength labels
   (informational only), with-trend split preserved, the per-round
   `round_snapshot_id` proof table on /three-lane, forming-candle
   exclusion + arithmetic consistency pinned by test, and the /desk
   self-check that renders RED with the offending rows on any
   contradiction.

### WHO OWES WHAT (2026-08-21)
- **Shyam:** delete the USOIL alert in TradingView (30s). Secret
  rotations at the finish line (PLAT-SEC-1, four secrets now).
- **Bot box:** Friday grade verdict (unaffected by the candle work —
  it reads `learning/trades.jsonl`, broker fills, not candles);
  send `sniper_executor.py` with the **sha256 of the bytes as sent** —
  the platform serves that digest, not a hash of its stored copy.
  Still pending 2026-08-22: nssm's UTF-16 console output broke the
  first hash attempt; a registry-based command is with Shyam.
  /downloads keeps 404ing honestly until a hash-verified copy lands.
- ✅ **BOT-P0-2 canonical signal_id — BOT SIDE DONE** (brain commit
  `6063676`, verified in brother-brain-v2: Pine's id adopted verbatim,
  minting only as fallback, `signal_id_source` stamped append-only).
  **ACCEPTANCE WATCH, platform:** the FALLBACK_ID share on /funnel
  falls toward zero after the brain deploy. If it has not fallen
  within a few trading days of 2026-08-22, that is a FINDING — say so.
- ✅ **entry_dist_atr into v7 telemetry — BOT SIDE DONE** (v7 commit
  `89185a3`, verified: append-only schema field, captured VERBATIM
  from Pine v18.12 on opens AND rejects, never computed bot-side;
  deployed to the box 2026-08-22 01:27 per the bot session).
  Forward-only: the n>=20–30 per bucket clock started at deploy. This
  is the SECOND population for the >3 ATR question; the platform's
  lane table stays a hypothesis generator, and nothing gates until
  both populations agree, with-trend cell rules intact.
- ✅ **Trade closes into the mirror — DEPLOYED** (bot side confirmed
  2026-08-24: bot.py calls `mirror_v7_close`, service restarted
  `active`). Closes now reach the platform in real time; the 12h TTL
  and the 30s re-poll are backstops again, not the mechanism.
  VERIFY: watch the next real close drop its levels off /chart within
  a minute, not at the TTL.
- ⏳ **Outlook posts** — bot box built `post_outlook.py` (verified on
  their branch: posts to `/webhooks/brain/outlook` with symbol,
  horizon, thesis, source, scenarios when:level:reading, valid_hours —
  matches this ingest's contract exactly, banned words refused
  locally too). ABSENT chips remain correct until real posts arrive.
- 📋 **SPEC FOR THE BOT BOX — periodic spread sampler (build only if
  Shyam wants it; UNKNOWN stays the honest fallback meanwhile).**
  POST `/webhooks/brain/bias` (existing route, existing secret
  header), one item or a list, each item EXACTLY:
      {"symbol": "<canonical, e.g. GOLD>",
       "spread": <price units, float>,
       "spread_points": <broker points, float, optional>,
       "spread_source": "mt5_tick_sampler",
       "spread_at": "<UTC ISO8601 of the SAMPLE moment>"}
  Cadence: at least every 10 minutes per open symbol
  (SPREAD_MAX_AGE_MIN=10 is the platform's staleness gate); skip
  closed markets rather than posting a stale tick. `spread_at` is the
  sample time, never the post time. Send NO other keys: as of v4.55
  the ingest refreshes the BIAS clock only when a post carries bias
  content (trend/strength/confidence/council/risk/as_of), so a
  spread-only post can never dress an old bias as fresh — that guard
  is deployed platform-side and is what makes this sampler safe.
- 🚨 **BOT-BIAS-1 — the v18 bias push has stopped covering SILVER and
  US100** (reported by Shyam from the live radar, 2026-08-25: SILVER
  silent 4 days, US100 6 days, while BOTH symbols' candles stay LIVE
  here). Nothing to repair platform-side — the ingest is up and
  accepting, and the Freshness Law is doing exactly its job by holding
  them STALE. The ask is on the bot box: does the push still include
  those two symbols? **Do not backfill an old opinion with a new
  timestamp** — post what the council holds now, or stay silent. A
  refreshed clock on an old view is the one outcome worse than silence.
  Evidence command (platform side, read-only):
  `cd /srv/brotherbot && docker compose exec app python -m
  scripts.bias_coverage` — prints both clocks per symbol and the relay
  paste. Full entry under "Bot box" below.
- **Platform (me):** the evidence-integrity order above; serve the
  executor once it arrives. *Already done and needing no further
  work: BTC wipe+refill, faster candle ingest (60s timeout + retries
  on timeouts AND 5xx), NY lane as a visual peer of the four desk
  lanes (v4.35).*

Last reviewed 2026-08-17. Phase 1 is complete **as engineering** on both
sides (see `V7_SELF_DEPENDENCE_PLAN.md` §3 and its status ledger). Nothing
below blocks the Phase-1 dataset; all of it is real.

The rule this file exists for: an item deferred in conversation is an item
forgotten. Anything not in the repo does not exist.

## THE PATH FROM HERE (agreed 2026-08-20, both sides)

One organ per week, whatever the evidence names loudest. In order:
1. ⬜ **Friday: the grade verdict.** The all-grades collection week ends
   and finally answers whether Pine's grades mean anything — the first
   six-month-old rule put on trial with real data. Bot box owns the call;
   `/grades` is the platform's read model for it.
2. ⬜ **`entry_dist_atr` into v7 telemetry — BOT BOX, and it is the
   blocker for the Location-Gate cap.** Pine emits it (appended in
   v18.12), the payload carries it to the bot, and `learning/telemetry.py`
   has no such field, so `load_unified()` cannot bucket it and
   `setup_edge` cannot cut by it. One append-only field plus the capture
   at the open call site. **Forward-only**: every trade already fired
   dropped the value, so the clock on n≥20–30 per bucket starts when the
   column lands.
3. ⬜ Then one organ per week, evidence-led.

**Nothing touches Pine's Location-Gate max-distance cap** until item 2
exists AND both populations agree — the platform's lane table and v7's
own filled trades. See CLAUDE.md "EVIDENCE AUTHORITY".

### Measurement layer (spec locked 2026-08-20, both sides) — status
- ✅ **DXY/US10Y/US30Y front-contract resolver — BOT SIDE, done
  2026-08-20** (bot box report: nearest non-expired contract by MT5's
  own `expiration_time`, hourly cache, 404 "rolled and no successor"
  when none, `_U6` suffix parsed only as fallback; two planted bugs
  confirmed red first — epoch-expiry on missing `expiration_time`, and
  /execute routed through an analytics resolver. Read paths only).
- ✅ **EMA200 + MTF trend context — PLATFORM, v4.38** (`trend_context`,
  trend-ctx-v1, /desk strip, context only, structurally un-gateable).
- ✅ **Row 2: Weekly/Monthly Outlook + Scenario Map — PLATFORM, v4.39**
  (`outlooks` table + `/webhooks/brain/outlook` + `outlook.board`).
  Both approval sharpenings enforced structurally: no confidence
  column exists and the ingest refuses `confidence`/`probability`/
  `chance` BY NAME (counted context renders instead); every outlook
  carries the envelope and EXPIRED renders loudly. Append-only.
  Adopted the stricter validation bar as instructed: n≥20–30 AND a
  validation split AND two populations AND out-of-sample before any
  outlook-derived pattern is even a candidate for authority.
- ✅ **Outlook scorecard + desk chips + ABSENT law — PLATFORM, v4.53**
  (`outlook.scorecard`, outlook-score-v1 + chips at the top of /desk +
  `state`/`gap_note` on the board). Expired outlooks graded against
  the CLOSED 1d candles of their own window, each leg KNOWN or
  UNKNOWN with its reason; a window under 60% stored refuses the
  negative. An expired outlook with no successor renders as a GAP,
  never as the standing opinion. Proof: `tests/test_outlook_scorecard.py`
  (8 tests, suite 494). Confidence-by-name refusal untouched.
- 📋 **ICT FEATURE LAYER — PLATFORM, dark, QUEUED (work order
  2026-08-22; per V7_AUTONOMY_PLAN.md builds start only AFTER the
  collection week, one per week, in this order):** 1. FVG → 2. Order
  Block → 3. CISD → 4. Rejection Block → 5. Opening Gap. Each computed
  from stored CLOSED candles as columns on lane observations exactly
  like `entry_dist_atr` — evidence only, no gate, no Pine change, no
  council change; n>=20 per cell with the with-trend split before any
  of them is even a finding.
- ✅ **17 DXY distance rows — RESOLVED (2026-08-24, both sides).**
  Bot side proved the candle feed clean (single source mt5:52834417,
  no parallel series, no twins). Platform side identified the query:
  `evidence_integrity.distance_consistency` over LANE_OBSERVATIONS
  (not candles — the ids were lane row ids), and the root cause was
  the CHECK's arithmetic, not the data: stored entry/reference are
  px-rounded, and on DXY one tick (0.01) is ~0.3 of its ATR (~0.03) —
  six times the fixed ±0.05 tolerance. All 17 deltas (0.06–0.20 ATR)
  sit inside the one-tick rounding bound. v4.61 makes the tolerance
  precision-aware: max(±0.05 ATR, one tick ÷ ATR) per row; rows inside
  the rounding bound are counted and named, never listed as
  contradictions; rows beyond it still fail loudly. Nothing repaired.
- ⬜ **DXY 1d feed watch (bot side finding, 2026-08-24):** newest DXY
  daily bar is 2026-08-20 while finer tfs are current. Likely just the
  reporter restart week; tonight's close should print it. **If the DXY
  1d series has not advanced past Aug 20 by Tuesday 2026-08-25, flag
  it to the bot session as a stalled series.**
- 📋 **ADAPTIVE TRADE MANAGEMENT — spec received 2026-08-25, routed:**
  the never-widen law (BUY: new_SL >= old_SL; SELL: new_SL <= old_SL),
  setup-SL vs position-SL separation, closed-bar-only trailing, no
  future information, and shadow-before-enforce are all AFFIRMED — they
  restate mgmt-v1's and the autonomy plan's own laws. Ownership split:
  · PLATFORM (done, v4.66): management journal timeline on /chart
    (desk_messages, §17); MAE/MFE management-evidence seed on /desk
    (§11 counts: died-with-profit, survived-drawdown). mgmt-v1 keeps
    suggesting and journaling; SL suggestions already only tighten.
  · BOT BOX (stage 6, harness first, AFTER the collection week, one
    organ per week): any engine that actually MOVES a stop — BE rule,
    structure trail, dynamic TP beyond the current ladder. The
    managed-vs-entry-only expectancy comparison is a HARNESS run over
    stored bars (no hindsight), never a casual division; management
    profiles (per-condition best action) come only after that, through
    shadow → review → explicit approval, exactly like the entry gates.
  · News-aware management uses the existing news regime card inputs;
    the HIGH-news block stands unchanged.
- ⬜ **Item 11: macro transmission read model — PLATFORM, next organ.**
  Event → T+1D/5D/20D legs (DXY, US10Y, asset) computed from stored
  1d candles over the recorded `event_reactions`, each leg KNOWN or
  UNKNOWN ("only 1 of 5 days elapsed" is a state, not a blank), so
  sequences like "Aug 19 Treasury buyback doubling → yields ↓ →
  DXY ↓ → gold/BTC ↑" become countable rows instead of a remembered
  story. No schema change needed — read model over existing tables.
  NOTE the amplifier lesson from the BTC leg: a short squeeze is not
  the macro channel; the read model must record the move, never
  attribute it.
- ✅ Macro event reaction + optional-UNKNOWN US10Y leg — already live
  since v4.24–4.26 (`reaction`, EventReaction); needed alignment, not
  construction.
- ⬜ **BOT BOX: send `sniper_executor.py` through the relay** so it can
  be committed under `agents/sniper_executor/` and served at
  `/downloads/sniper-executor.py` (+`.sha256`). The serving side is
  live since v4.40 and 404s honestly until the file lands; the
  platform never serves a file it has not versioned. Then the bot box
  writes Shyam the one-command updater (fetch → hash-verify → backup →
  copy → restart, refuse on mismatch).
- 🚨 **DATA INCIDENT 2026-08-20 23:50–00:16 UTC — one-hour clock, NOT
  yet remediated on production.** The reporter inferred +2h from a
  stale gold tick; truth was +3h. Affected: XAUUSD/GOLD, XAGUSD/SILVER,
  BTCUSD/BTC and part of ETHUSD/ETH. Source fixed in reporter v1.4.0
  and audited by `scripts/audit_candle_offsets.py` (v4.41), but the
  STORED ROWS ON CONTABO ARE STILL DIRTY.
  ~~Earlier remedy: re-backfill with a PINNED SCALAR, then purge.~~
  **SUPERSEDED 2026-08-21 — do not follow it.** Pinning the scalar
  stops the drift but does not make winter bars correct, and purging
  before the rebuild deletes rows the rebuild would replace while
  leaving the invisible half untouched, then reads "0 provable" as
  clean. The live order is the REBUILD entry further down.
  **SCOPE — revised TWICE on 2026-08-21, and the second revision
  retracts the first. Read both; the sequence is the lesson.**
  - First revision (bot box): the blast radius is one manual run, four
    symbols, and the history is clean — evidenced by GOLD's dailies at
    21:00 UTC and 4h at 13/17/21, the grid a correct +3 produces.
    I recorded that as proof. **It was the MODE, not the
    distribution.** The audit then read every row and found 30,209
    off-grid, with bar dates reaching back to 2007 and 2011 — the bad
    run was 5000 bars DEEP, so it rewrote history in bar-time, not
    just recent bars. Direction came back MIXED: GOLD's off-grid
    dailies sit at 00:00 UTC (an offset of ZERO — the old "Assuming 0"
    fallback firing) while its 4h rows sit +3600s (an offset of 2). At
    least two bad episodes, not one.
  - Second revision, and the reason NOTHING may be deleted yet: **the
    broker is EET/EEST and MT5 returns history in server wall-clock,
    so the seasonal hour is inside the data.** A scalar offset applied
    to a deep backfill is wrong by an hour for every bar of the
    opposite season EVEN WHEN DETECTION SUCCEEDS. That breaks the
    grid test in both directions: a correct, season-aware series has
    TWO daily grids (21:00 summer / 22:00 winter) and the modal test
    calls the minority corrupt, while a scalar-converted series
    flattens both onto one tidy grid and looks immaculate while being
    an hour wrong for half the year. **Internal consistency is not
    correctness.** So: confirm the DST question, purge only what
    survives it, re-backfill the holes, re-audit. Better another day
    than deleting a decade of silver dailies recorded in January.
  - ✅ **THE STRUCTURAL FIX — BUILT, reporter v1.5.0 (not yet
    deployed).** Per-bar conversion through `BB_BROKER_TZ`
    (Europe/Athens) replaces the scalar; the detected offset is now
    only a validator and the agent refuses when calendar and clock
    disagree. **Windows needs `pip install tzdata`** — zoneinfo has no
    tz database on Windows and the agent refuses rather than falling
    back. DO NOT deploy it before the wipe+rebuild below: per-bar
    conversion moves winter bars to a different timestamp, so running
    it against the existing scalar table adds a THIRD population.
  - ✅ **DEPTH PROVEN 2026-08-21.** Every affected series is
    recoverable; nothing reads TOO_SHALLOW. Four 1d series match
    EXACTLY (stored − flagged == what MT5 serves: GOLD 7483, SILVER
    6274, BTC 4655, ETH 3265), which independently confirms the
    off-grid rows are surplus rather than other-season history — the
    terminal answering purge-block #3 without a grid argument. GOLD 1d
    history starts 1998-04-21, so its shortfall is "that is all there
    is", not a Max-bars ceiling: no terminal setting needs changing.
  - ⬜ **THE REBUILD, in this order and no other** (Priority 3):
    **(0) depth probe on Windows — `python mt5_reporter.py depth` —
    and (1) pg_dump kept until the re-audit reads clean**, both now
    ENFORCED: `wipe_series` refuses without a dump that mentions the
    symbol and a probe under 24h old proving MT5 serves at least what
    is stored. Then deploy reporter v1.5.0 → wipe each affected
    symbol/tf → deep re-backfill → purge whatever survives → re-audit.
    ⚠️ Depth is NOT assumed to be fine: SILVER holds 11,375 dailies and
    BTC 8,960 back to 2011, while a 5000-bar request has already failed
    outright on XAUUSD 1d. Raising Tools > Options > Charts > Max bars
    may lift the ceiling — the probe VERIFIES it, nobody assumes it.
    Affected: GOLD, SILVER, BTC, ETH on 4h/1d (30,209 provable rows,
    ~15% of those four symbols). The other 14 symbols were untouched
    by the corruption events, though every deep backfill everywhere
    carries the scalar caveat until rebuilt.
  - 📌 **THE COLLISION that fixes the order:** under correct conversion
    a 4h winter bar belongs at residue 7200s — exactly where a summer
    bar shifted +1h sits today. Rebuilding without wiping leaves three
    populations in one table with no rule that separates them.
  - (superseded) per-bar conversion as unbuilt work: Either convert each bar through the broker's DST
    calendar (zoneinfo, e.g. Europe/Athens) or store the raw server
    timestamp plus the broker timezone and convert at read time. A
    single `BROKER_OFFSET_S` cannot be right for a multi-year series;
    pinning it to 3 stops the drift but does not make winter bars
    correct. This is a planned migration, not a midnight patch — new
    data converted per-bar while old data is scalar would put two
    grids in one table for a THIRD reason.
  So: the EMA200/MTF/outlook pause applies to THOSE FOUR SYMBOLS AND
  THAT WINDOW, but the DST finding is dataset-wide and unresolved.
- 🔄 **Backfill RUNNING 2026-08-20 ~23:5x UTC** (18 symbols × 5 tfs,
  5000 bars each; XAUUSD/XAGUSD done in the pasted log). Shyam must
  still run `Restart-Service BrotherBotReporter` after "backfill
  complete: N candles" — NOT yet done at the time of the paste. Known
  benign: `XAUUSD 1d: 0 bars (Terminal: Call failed)` = MT5 Max-bars
  chart-history limit, logged loudly by the v4.29 fix; raise Tools →
  Options → Charts → Max bars later if daily depth matters.
- ⬜ **SHYAM, next time on the Windows box: run the reporter backfill.**
  The macro legs show `UNKNOWN — insufficient history (~100/200 bars)`
  until it runs: DXY 464 rows, US10Y 474, XRP/LTC/GBPUSD ~400 (counts
  2026-08-20). One run fixes every young feed AND lifts the MAE replay
  ceiling. On the box:
  `set BB_BACKFILL_BARS=5000` then `python mt5_reporter.py backfill`
  (same env vars as the service; symbol_select is done per symbol
  inside; server dedupes, so re-running is safe).
- ⬜ Recording trend context INTO evidence rows (alignment leg #2,
  beside birth bias) — future organ; the read model computes for any
  timestamp from closed candles, so nothing is lost by waiting.

## What is NOT in this repo (checked 2026-08-20 — do not go looking)

A summary in conversation listed several organs as platform-side. Two of
them are not, and a new window hunting for them would waste hours or,
worse, assume a question is answerable that is not:
- ❌ **No counterfactual lane exists here.** Nothing in this repo replays
  what a refused signal would have done. If that is wanted it is
  unbuilt work, not an existing table.
- ⚠️ **`setup_edge` here is a RENDERER, not a computation.**
  `v7_view._setup_edge` displays what the bot box sends in its artifact;
  the platform does not compute setup edge and cannot re-cut it by a
  dimension the bot box did not include.
- ✅ Genuinely platform-side and real: the snapshot-outcome memory
  (`market_memory`, v4.2), the event-reaction recorder (`reaction`,
  v4.24), the lane observation dataset (`collector`, v4.0) and the
  distance confounder table (`desk.distance_confounders`, v4.37).

## Platform (this repo)

**A standing rule, earned on 2026-08-20: BUILD TO THE WIRE, NOT TO THE
SPEC.** The chart reported EMPTY for a day because `bridge.py` read
`candles`/`ts` (the names in the written spec) while the feed sends
`rows`/`time`. 180 bars discarded per call, HTTP 200, no error. Nobody
had ever looked at a raw reply. Before integrating ANY external feed:
curl it once, read the actual keys, and make the parser say which keys
it got when it recognises none of them. A field-name mismatch is
indistinguishable from "no data" unless the code is written to tell them
apart.

**Its twin, earned the same week: RENDER THE REASON, NEVER THE ABSENCE.**
The NY block vanished instead of failing, and a missing panel reads as
"nothing to report" rather than "I broke". Any block that can fail must
render in every state — dormant with a countdown, active, or FAULT with
the reason — and must never be nested inside an unrelated condition. Two
concrete rules that follow: a read model may not raise (catch and return
a named fault state), and a Jinja `[key]` lookup is banned in favour of
`.get(key, default)`, because one unknown key takes the whole page down.


**PLAT-SEC-1 — rotate the shared secrets that have been through a chat
window.** THREE now: the **v7 webhook secret** (pasted weeks ago, never
rotated), the **bridge key** for the live chart feed (issued
2026-08-19, delivered through chat with the last two characters withheld
and completed by hand on the server), and the **MT5 reporter API key**
`bb_…` (pasted in full on 2026-08-21 while sharing the reporter's env
block — the whole point of loading it from the registry was that nobody
should have to handle it). That key carries heartbeat-write permission,
so a rotation is a dashboard action: create a new key, put it in the
service env via `nssm edit`, restart, then revoke the old one. Neither value is in this repo, in a
log, or on a page — the bridge key is scrubbed from every error string by
`app/services/bridge.py` and asserted by test. Status: **deferred by
explicit user decision** — the standing instruction is that security,
passwords and API keys wait until demo development ends, and all accounts
are DEMO. Recorded here so the decision is a *choice* and not an
oversight.
- Bridge key rotation, when wanted: the bot box re-posts
  `/webhooks/brain/bridge-config` with the new value (v4.23 — nothing is
  typed on the platform side, so nothing is mistyped), then reload
  `/live-bridge` and confirm LIVE rather than UNAUTHORIZED and that the
  fingerprint matches theirs. Seconds, chart-only outage. The `.env`
  fallback still exists for a cold start with no bot box.
- What it protects: the brain→platform ingest endpoints (`/webhooks/brain/*`),
  which are read-only mirrors — a leaked secret lets someone POST false
  signals/candles/bias into the platform's records. It cannot place a trade
  (Iron Rule 1), but it can poison the evidence tables the whole V7 plan
  depends on.
- Rotation when wanted: set the new value in the platform `.env`
  (`BB_BRAIN_WEBHOOK_SECRET`) and in the bot box's poster config, restart
  both, verify a candle POST returns 200. Never echoed to chat or logs
  (Iron Rule 4). Roughly a five-minute job with a short outage window.
- Do this **before** any real-money account exists, not after.

**PLAT-CHART-1 — CLOSED as engineering (v4.27–v4.29).** Chart (v4.27),
stored-candle fallback (v4.28), position-management panel + NY column
(v4.29, built to the envelope spec the bot box restated in relay — SL is
the hard invalidation `V7_FACT`; structural levels `DESK_DERIVED` from
the one level ladder; ORPHAN first-class; two engines with disjoint
vocabularies; every message journaled `UNVALIDATED` in `desk_messages`;
`valid_until` enforced as EXPIRED; no Desk→MT5 path, structurally). The
"no action" guard graduated in the SAME commit as the panel, exactly as
this file required. Proof: `tests/test_mgmt_panel.py` (12 tests) +
`tests/test_chart_bridge.py`.
- ⬜ Remaining, deliberately: the management ruleset `mgmt-v1` and the NY
  machine `ny-v1` are UNVALIDATED and must stay so labelled until the
  `desk_messages` journal is replayed against outcomes in Phase 2. Do not
  promote a label without that replay.

**PLAT-MACRO-1 — CLOSED 2026-08-19. All three legs are live.** The
recorder (v4.24) now has asset + dollar + yields. Proof it is closed:
`dxy_coverage` / `y10_coverage` on `/event-reaction` stop reading zero.
- ✅ **`US10Y` and `DXY` candles — LIVE 2026-08-19.** Both flowing on
  15m/1h/4h/1d, newest bar level with GOLD's, arriving on
  `/api/v1/heartbeat/candles` under the logical names. Blocker was two
  more instances of the day's pattern: `BB_PUSH_CANDLES` defaulted off
  (the symbol list alone did nothing), then machine-level env vars were
  silently overridden by the service's registry-level
  `AppEnvironmentExtra` — accepted config, no error, nothing happening.
  Probed first as `UST10Y_U6` 108.834 / `DXY_U6` 98.678 on the same 15m
  bar. Bot side it was config, not a deploy — the reporter reads
  `BB_CANDLE_SYMBOLS`, appended to (never replacing) the existing value,
  set at the REGISTRY level or the service ignores it. Platform side
  needed nothing: both ingest doors share `upsert_candles`, which
  canonicalizes, pinned on the webhook path (v4.25) and on the heartbeat
  path the reporter actually uses (v4.26).
- ✅ **The `USDX` mapping bug, found by the same probe.** The v7 bridge
  had `DXY`→`USDX`, which that terminal does not list — every dollar-index
  read through the bridge had failed invisibly since the map was written.
  Fixed bot-side to `DXY_U6`, matching the brain box. Recorded because it
  is the third instance of the same failure shape (bad alias looks exactly
  like a working symbol until something is actually attempted).
- ⬜ **5-minute candles** for the measured assets, if T+5 is wanted. With
  15m storage the first honest horizon is T+15. Not blocking. (v4.29:
  `BB_CANDLE_TFS` now exists, so enabling `5m` — or `1m`, which is being
  turned on for MAE evidence — is a registry config change plus service
  restart, no code.)
- The probe (`probe_symbol_specs.py`) must run on the **Windows bot box
  where MT5 lives**, not on the Contabo host — it is not on the Linux box
  and never was.

**PLAT-MACRO-2 — dated contracts roll and nothing errors.** `_U6` is
September 2026. When `UST10Y_U6` / `DXY_U6` roll, the old symbol simply
stops printing bars; a dead feed is indistinguishable from a quiet
market. **Largely closed (v4.25).** Ingest strips the month suffix, so `DXY_U6`,
`DXY_Z6` and `DXY_H7` are one continuous series — the roll itself now
costs nothing, proven by test. A bar-less leg is UNKNOWN, never "flat"
(v4.24). And `macro_feed_health` on `/event-reaction` names a macro
symbol whose newest bar has stopped advancing (LIVE / STALE / ABSENT /
CLOSED, weekend-aware), which is the failure aliasing cannot fix: a dead
reporter or a contract delisted with **no successor**. Remaining: nobody
is alerted, it must be looked at. Bot side the symbol is an env override,
so a roll is a config change and a restart, not a deploy.

## Bot box (brain-v2 / v7 — coordinate via the user's brain session)

**Recorded, not open — the bridge auth scope, and why it is right
(2026-08-19).** The bot box gated `/candles?live=1` and left closed-bar
`/candles` open on purpose. A pre-deploy grep found closed bars are read
by the trading bot itself (`bot.py fetch_atr`, live ATR when Pine omits
it), by `analyst_eye`, and by their status dashboard — none carrying a
key — and `fetch_atr` **fails safe to `None`**. Gating them would have
changed how the bot sizes and skips trades, silently, with no error
anywhere. `/spread` and `/symbolspec` are gated unconditionally (verified
no live callers). Worth keeping written down because it is the shape of
bug this whole project keeps meeting: a fail-safe default turning a
security change into a behaviour change that nothing reports.

**BOT-OPS-1 — CLOSED 2026-08-19. Hash match, byte-identical.** The
premise ("342 lines of production code, unversioned, on one disk") was
wrong, and the running file is confirmed to BE the repo file — settled by
`Get-FileHash` on the box against `sha256 af90372…59c1a`, not by pasting
a copy into chat. Kept below because the reasoning is the reusable part.
The reporter lives in this repo at
`agents/mt5_reporter/mt5_reporter.py` and has been since the original
"Add MT5 reporter agent" commit — **five commits of history**, and the
platform serves it at `/downloads/mt5-reporter.py`. It is **342 lines**
and reads `BB_CANDLE_SYMBOLS`, matching the bot box's description exactly.
No secrets: every value comes from an env var, the docstring holds
placeholders only.
- ✅ **The question was whether the file RUNNING on the Windows box was
  this file.** Matching line count and matching env var is strong
  evidence, not proof — `PINE-1` below is this exact situation, where two
  plausible-looking copies of the indicator had silently diverged from
  what was live.
- Settle it with a hash, never a paste. **Re-anchored v4.29:** the repo
  copy CHANGED (CANDLE_TFS became env-driven `BB_CANDLE_TFS` for the 1m
  evidence feed), so the box's file no longer matches until the next
  Windows redeploy — expected drift, not an alarm. New repo hash:
  `sha256 3165ff0c29463f19a2f95edb2de079aa6aeab7bf2958000d1a82918794f2adfd`
  (v4.30 — adds symbol_select + 0-bars logging to `_push_rates`; the
  earlier v4.29 hash `0110d1a6…` lasted one commit and was never
  deployed).
  (Matched byte-identical on 2026-08-19 against the previous hash
  `af90372…59c1a` before this change.)
  Bot box runs `Get-FileHash -Algorithm SHA256 <running path>` (the path
  comes from `nssm get BrotherBotReporter Application` / `AppParameters`).
- Match (what happened) → closed as already-done, nothing to commit.
- Differ → **the RUNNING file is authoritative**, and it comes here so
  the diff shows what drifted. Do not overwrite the box from the repo.
- ❌ **Do not paste the repo copy into chat for them to commit.** That
  creates a third copy whose provenance is a chat window, and risks
  replacing a live file with a stale one — precisely the PINE-1 failure,
  repeated with the reporter instead of the indicator.

**BOT-P0-1 — CLOSED 2026-08-19 (both sides, verified).** The bot box fixed
the journal writes and backfilled 202 finished trades to
`/webhooks/brain/signal` (`status="closed"`, `backfill:true`,
ids `v7-<signal_id>`). Platform side then found and fixed its own half:
the status whitelist silently dropped the unknown word "closed" while
storing the row (v4.18) — vocabulary extended, unknown statuses now leave
a visible `status_unrecognized` event, and `repair_signal_statuses`
normalized the stored rows from their verbatim raw_payload with **no
re-send** (the bot's cursor stands at 202, untouched). Proof:
`tests/test_signal_status_vocabulary.py` + the startup repair log line.

**BOT-P0-2 — the brain mints its own `signal_id` instead of adopting
Pine's.** The executor's dedupe guard is keyed on the minted id, so it cannot
catch a genuine Pine duplicate.
- Platform compensation already in place: `opportunity.group_signals` treats
  `pine_signal_id` as authoritative and falls back to a deterministic
  join (symbol + direction + entry within 30 minutes), **labelled
  `FALLBACK_ID` on `/funnel` and the asset page** so a joined-by-guess row is
  never mistaken for a joined-by-id row.
- Measurable finish line: when the brain adopts Pine's id, the share of
  `FALLBACK_ID` groups should fall toward zero. That column is the
  acceptance test — no new instrumentation needed.

**PLAT-OUTLOOK-1 — verify the outlook scorecard's first real grades
(due week of 2026-08-31).** The bot box's auto-weekly cron (Sunday
21:30 UTC, source "bot box auto-weekly-v1", up to 7 symbols) starts
filling the board; the first weekly envelopes lapse next week and the
scorecard (outlook-score-v1) begins grading real rows. Verify then:
KNOWN legs score, UNKNOWN legs stay UNKNOWN (COVERAGE_FLOOR=0.6), no
leg is invented for a scenario price never visited. Also: after Friday
2026-08-29, the ⚖️ rejected-vs-traded card on /v7 feeds the GOLD
RE-GATE / KEEP ENABLED review — platform mirror population beside v7's
own journal, two populations as always.

**PINE-CALC-1 — v18.13 calculation fix + the sensor boundary
(2026-08-31; ASK CLOSED same day).** The version stamp already existed:
`pine_ver`, in every payload since v18.8. My "no version key" claim was
a case-sensitive grep miss, corrected by the Pine session; v4.91 keys on
`pine_ver` and a new test reads the name from the indicator source so
the mistake cannot recur. NO new key is to be added — two version keys
would one day disagree.
ROOT CAUSE (Pine session, 2026-08-31): ONE bug, not three — v18.12's
three `request.security_lower_tf` calls for the DXY squelch blew
TradingView's per-study memory limit on the heaviest 24h symbols; a
stopped study draws nothing (the vanished panels) and never reaches
`alert()` (SILVER 3d / US100 5d silent). v18.13 collapses them to one
guarded request, fixes bare `"DXY"` → `"TVC:DXY"`, stamps
`pine_ver:"18.13"` and appends `structure`. This CLOSES BOT-BIAS-1's
silence symptom and BOT-BRIDGE-1's sibling — verify by watching SILVER
and US100 resume posting after the ceremony.
STILL OWED: the ALERT CEREMONY (delete + recreate EVERY alert — an old
alert keeps running the OLD dying script, which is exactly how a symbol
stays quiet for days while the chart looks fine), and if the ⚠ ever
returns, capture the one-line red text BEFORE anything else. ALSO REQUIRED at the change: the ALERT CEREMONY —
delete and recreate EVERY TradingView alert ("Any alert() function
call"); alerts freeze the script at creation time, so an un-recreated
alert keeps firing the OLD calculation while the chart shows the new
one. Filename never changes.

**PLAT-MIRROR-1 — ✅ CLOSED in v5.00 (2026-09-01).** Their mirror now
forwards `pine_ver` / `payload_schema` / `fired_at` / `session` / `tf` /
`score`, so the platform half shipped: `normalize_tf()` on both signal
and decision ingest (`15`→`15m`, `60`→`1h`, `240`→`4h`, `1440`→`1d`),
`parse_event_ts` accepting epoch MILLISECONDS as well as seconds and
ISO, and a `signals.fired_at` column that keeps Pine's firing clock
separate from ours. The sensor banner (v4.91) splits v18.12 from v18.13
on its own from here. ⚠️ Needs the Postgres ALTER in CHANGELOG 5.00
before the deploy — a missing column names itself in the plan panel
rather than blanking the page, but it stays missing until run.

**PLAT-EXPOSURE-1 — NVDA and US100 are ONE exposure (opened 2026-09-02,
bot-side measurement).** Nvidia is already the MAJOR_EARNINGS driver
behind US100, so any page that SUMS risk across symbols currently treats
a correlated pair as two independent positions and understates it. The
measurement is not in doubt; the change is, because coupling symbols
inside a risk sum is a risk-semantics change and Iron Rule 3 says risk
is never widened or narrowed silently. Ships alone, with tests, as
Shyam's logged decision — never as a quiet constant.

**PLAT-HOLDOUT-1 — the Model Lab holdout re-arms on every retrain
(opened 2026-08-31, bot-session audit #7).** Direct breach of QUANT LAB
LAW: "the newest 20% is the FINAL HOLDOUT, spent exactly once per
experiment and never re-armed." The delicate part is defining what
counts as a NEW experiment (a changed variant family? a new dataset
window?) — so it ships alone, next release, with tests that prove a
second spend is refused.

**SHYAM'S TWO DECISIONS (relayed 2026-08-31, no rush — Friday is fine).**
(a) PULLBACK through v7: the bot session recommends LEAVING it —
auto_live IS the pullback engine and is already collecting in shadow;
revisit Friday. (b) DD guard effectively OFF (99%): demo money, but bad
measurement. Real limits require Shyam to NAME the numbers (their
example: daily 5% / weekly 10% / total 20%); Iron Rule 3 means no risk
number is invented on his behalf — it ships as HIS logged decision.

**THE RUNNER FINAL GATE (recorded 2026-08-31, bot-session order,
verbatim).** No broker-side stop movement until ALL of: ✓ replay
comparison complete (🏃 /v7 card, n≥20) · ✓ management evidence
sufficient · ✓ no-widen invariant proven · ✓ state-machine invariant
proven · ✓ real shadow sample collected · ✓ explicit human approval.
Until then: SHADOW ONLY. The replay table never says "better" — the
ceremony does. Runner logic is FROZEN at the v4.88 baseline; evidence
collects.

**PLAT-CF-1 — the counterfactual classifier (accepted 2026-08-30,
Week-2 §9/§10, assigned to the platform's truth layer).** Over WAIT
lane observations (each carries level, distance, bar_ts): replay every
refused candidate through the SAME fixed resolve rules the filled
population uses — would the limit have filled, and TP1 or SL first? —
then cut by the gate that refused it. Output: per-gate counterfactual
expectancy with n, CANNOT SEPARATE under the floor, labelled
COUNTERFACTUAL everywhere (a replayed fill is not a fill). This is the
"do gates protect or suffocate" headline number of the ADAPTIVE_GATES
review. Build next platform release; harness-style offline first.

**THE ONE-TIME BOT-SIDE LIST (compiled 2026-08-28 at Shyam's request —
"give me full list so one time update").** Everything the platform is
waiting on from the bot box, oldest first; delete lines as they land:
1. **Bias push coverage** — SILVER + US100 silent 7d+ (BOT-BIAS-1;
   Shyam's own step: the TradingView alert-log check, active ≠ firing).
2. **Bridge rejects US100 live candles** — 400 BAD REQUEST
   (BOT-BRIDGE-1; symbol allow-list or USTEC alias).
3. **Earnings events** — calendar posts flow (GDP/PCE seen) but no
   MAJOR_EARNINGS rows yet (Nvidia → US100 playbook idle).
4. **US10Y direction conflict** — the brain's bias push says BEARISH
   while Pine's AssetPulse shows bullish (Shyam, 2026-08-28 21:34 UTC).
   Two sensors disagreeing is a SOURCE question, not a display bug:
   the platform shows the brain's push with its timestamp. Reconcile
   at the source and say which is authoritative.
5. **Executor hash** — the registry-based Get-FileHash command is still
   with Shyam; /downloads keeps 404ing honestly until a verified copy
   lands.
6. **v4.82 perf order — DONE platform-side, measure after deploy:**
   read models cached 60s, 4 uvicorn workers, sweeper off the event
   loop behind a flock, market clock frozen exactly while closed.
   Their ask ("measure a slow endpoint before and after") = run
   `python -m scripts.page_timing GOLD SILVER ETH` after the deploy and
   compare against the 2026-08-26 numbers in chat.
7. **Weekly readiness push (new, v4.83):** the /readiness page renders
   whatever the bot box posts as a doc artifact whose path contains
   AUTONOMY_READINESS (existing `/webhooks/brain/artifact`, kind
   "doc", markdown in payload). Add one POST to the Sunday cron after
   the report generates; the page goes ⛔ OVERDUE at 8 days on its own.
8. **Friday agenda confirmed:** GOLD verdict (⚖️ /v7 card + their
   journal), gate counterfactuals, Phase 1 formal close (their
   coverage: 14,941 resolved vs target 200).

**BOT-BRIDGE-1 — CLOSED 2026-08-31, both sides.** Measured by the bot
session: the bridge serves **USTEC**; `US100` is a display name only, so
any caller asking for "US100" gets 400 forever — the brain already
resolved it caller-side. Platform side fixed in v4.98
(`bridge.BROKER_TICKER`, outbound request only; canonical US100 stays
untouched in storage, pages and statistics). Their US30 feed probe
passed in the same paste (data proven; order acceptance remains a
separate probe — a served candle is never a fill). Original entry kept
below for the reasoning.

**BOT-BRIDGE-1 (original) — the live bridge rejects US100 (opened 2026-08-26).**
`http://…:5001/candles?symbol=US100&tf=15&n=180&live=1` returns
400 BAD REQUEST; every other symbol serves. The platform behaves as
designed — /chart falls back to its own stored CLOSED candles, labelled
"STORED (delayed)", and the error renders verbatim — so nothing to fix
here. The ask to the bot box: is US100 missing from the bridge's symbol
allow-list, or does the broker name it differently (USTEC)? Their own
queue already carries "the USTEC/US30 probe before index trading" — this
is likely the same root. Evidence: Shyam's live paste, 2026-08-26
19:41 UTC.

**BOT-NEWS-1 — PARTIALLY CLOSED 2026-08-26 (same day):** Shyam's
live GOLD page showed Prelim GDP and Core PCE flowing through the
playbook and the news regime — the brain IS posting the calendar
now. Still open: scheduled MAJOR EARNINGS posts (Nvidia etc. for
US100) have not appeared yet. Original entry kept below for the
contract.

**BOT-NEWS-1 (original) — the economic calendar feed is the fuel of the new
MARKET MAP (opened 2026-08-26, with v4.73).** The platform now runs a
deterministic event playbook (PCE/CPI/NFP/FOMC + MAJOR_EARNINGS such as
Nvidia): PRE_EVENT → INITIAL_MOVE → WAIT_15M_STRUCTURE → WAIT_RETEST →
NORMAL_EVALUATION, computed from posted events + closed 15m bars. It is
fully built and fully idle, because `/webhooks/brain/news` has received
nothing — on PCE day the calendar was empty (see v4.72). The ask to the
bot box: post the high-impact calendar (title, impact, currency,
event_time, affected_symbols), including scheduled MAJOR EARNINGS for
US100 (title containing the company name or "EARNINGS" routes to the
long pre-window playbook). Until then the map honestly shows "no
high-impact event in window" and news risk stays UNKNOWN — the platform
never invents an event. Behaviour changes on the v7/brain side (acting
on event phases, size reduction on CAUTION cells) are THEIR work; this
platform only mirrors and displays.

**BOT-BIAS-1 — bias push coverage gap: SILVER (4d) and US100 (6d),
opened 2026-08-25.** Shyam's report was "market radar not update sir
silver and usa100". The radar was NOT wrong: v4.70 already prints
`brain silent Nd — candles unaffected` beside `LIVE HH/HL our candles`,
which is the honest reading of two independent sources. The residue is a
real coverage gap on the pushing side.
- **What the platform sees:** a `market_bias` row for each symbol whose
  `updated_at` has not moved for 4 and 6 market-clock days. Past
  `BIAS_MAX_AGE_H` the row is INVALID, not neutral, so Zone reads STALE
  and Regime reads STALE. That is the Freshness Law working, not a bug.
- **What is unaffected:** this platform's own 15m candles for both
  symbols are current, so structure, ATR, VWAP distance, the lane
  observations and the Autonomous Bot keep running on live data. A
  silent brain never makes live candles look dead here, and a live
  candle never refreshes a brain opinion.
- **Why it is not the spread guard.** Since v4.55 the bias ingest moves
  the BIAS clock only when a post carries bias content
  (trend/strength/confidence/council/risk/as_of). If the bot box is
  posting spread-only heartbeats for these symbols, the row exists and
  the spread is current while the bias stays honestly old — which is
  precisely the intended behaviour, and would look exactly like this.
  **First thing to check on their side: are SILVER and US100 in the
  bias push list at all, or only in the spread sampler's?**
- **The refusal that comes with the ask:** do not re-stamp an old bias
  to clear the badge. STALE is information; a fresh timestamp on a
  4-day-old view is a lie the Freshness Law cannot catch, because it
  only measures the clock it is given.
- **Evidence, not screenshots:** `python -m scripts.bias_coverage`
  (v4.71, read-only) prints every bias row with bias age, council age,
  spread age and candle age side by side, names the silent symbols with
  their market-clock ages, and emits the relay paste. Run it before and
  after the bot box's fix — the finish line is those two symbols
  dropping out of the silent list on their own, from a real push.

## Pine provenance (recorded 2026-08-17, from the bot box's audit)

**PINE-1 — two stale copies of the indicator exist.** `pinev18.6` is an
EMPTY repo, and the Pine copy inside `brother-brain-v2` is a stale v18.7
snapshot. The real **v18.12** lives in this repo at `pine/`. Anyone
reading either of the other two will draw conclusions about code that is
not running. The only proof of what is ACTUALLY live is the `pine_ver`
field on the brain journal — grep that, never a repo file. Deleting or
clearly marking the two stale copies is a bot-box housekeeping task.

## Broker instrument facts (probe, 2026-08-17) — read before staging a coin

- **LINKUSD does not exist on this account.** It never resolved even after
  `symbol_select`. Dropped from staging; our alias and 24/7 entries are
  harmless but moot. Do not re-add it without a fresh probe.
- **SOLUSD: `volume_min` 1.0, `volume_step` 1.0** — whole lots only. On a
  small demo account that is a very coarse risk grid: position size cannot
  be tuned, so risk per trade is whatever one lot happens to be.
- **ADAUSD: `volume_min` 100.0** — the minimum position is 100 lots. The
  sizing maths must be checked before this is enabled, bot-side.
- **BTC/ETH controls:** digits 2, tick 0.01, min 0.01 — matches live.
- ⬜ **Still needed from the probe:** the `digits` value for SOLUSD. Our
  display precision (SOL=3) is currently an assumption, and a wrong digit
  count collapses two tradable levels into one displayed price. ADA=5
  is confirmed against the probe.

**Cross-system lesson recorded (bot box, same probe):** the v7 bot renames
`XRPUSD`→`RIPPLE` and `LTCUSD`→`LITECOIN` internally, the bridge had no
entry for either, and unmapped names pass through verbatim — so MT5 was
receiving the literal string `RIPPLE` and rejecting every v7 XRP and LTC
order. Invisible for as long as it ran, because a bad alias looks exactly
like a working symbol until an order is actually attempted. This is the
same failure the platform's canonical-symbol layer exists to prevent, one
hop further down. **Any new instrument must be probed end to end — name
resolves, spec returns, one order attempted — before it is enabled.**

## How to close an item here

Delete it only when it is *done and verified*, and say where the proof is
(test name, migration, or a live check). Moving an item to "won't do" is a
legitimate outcome; silently dropping it is not.
