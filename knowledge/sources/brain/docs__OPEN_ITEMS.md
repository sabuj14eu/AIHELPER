---
title: v18 brain open items
domain: brain
repo: sabuj14eu/brother-brain-v2
sources: docs/OPEN_ITEMS.md
verified_on: 2026-09-16
commit: 0f8f49d
classification: INTERNAL
---


## BOT-BIAS-1 ROOT CAUSE — US10Y stale 2.9 days (2026-08-31)

US10Y has exactly TWO sources in push_bias.py, and BOTH are dead:

1. FRESH (macro_market_bias, line ~263): asks the MT5 bridge for the
   first alias it serves out of US10Y, TNX, UST10Y, US10YT, ZN1!. If the
   broker carries none, it prints "no alias served by the bridge — left
   honestly stale" and contributes nothing. Most retail MT5 brokers do
   NOT carry a 10-year yield symbol, so this path has likely NEVER
   produced a row — the honesty is working, the feed was never there.
2. JOURNAL FALLBACK (macro_items, line ~137): reads `yield_dir` off Pine
   scalp payloads. This is the path that HAS been feeding US10Y — and it
   dried up the moment Pine started dying (the v18.12 memory-limit bug).
   2.9 days of US10Y silence sits inside the same window as SILVER's 3
   days and US100's 5 days. One bug, now four symptoms.

### THE FINDING THAT MATTERS MORE THAN THE STALENESS

US10Y — and DXY by the same structure — reach the system ONLY through
Pine. That is an AUTONOMY VIOLATION by the Week-2 rule "Pine must be
optional": when Pine dies, the bot loses half its macro context and the
cross-asset card correctly drops to one input. The scenario engine
already records macro_context as UNKNOWN rather than guessing, so
nothing is corrupted — but nothing is learned either.

### PREDICTION (falsifiable, check it tomorrow)

After tonight's v18.13 save + alert ceremony, US10Y and DXY should
resume WITHOUT any code change, because path 2 revives with Pine. If
US10Y is still stale 24h after the ceremony, path 2 is broken on its own
and the journal is the place to look (grep yield_dir in decisions.jsonl).

### THE REAL FIX (needs one probe answer first, no guessing)

Run on the bot box:
    python3 probe_symbols.py US10Y TNX UST10Y US10YT 'ZN1!'
- ANY alias TRADABLE -> one-line fix: set BIAS_US10Y_SYMBOLS in the
  brain .env to put that alias first. Pine-independent macro, done.
- NONE tradable -> the bridge genuinely cannot serve yields, and a
  Pine-independent US10Y needs an external feed (a new organ, harness
  first, per the ceremony). Do NOT invent one on a guess.

### PROBE RESULT (2026-08-31, run on the bot box) — MEASURED, NOT ASSUMED

    US10Y  404 · TNX  400 · UST10Y  404 · US10YT  400 · ZN1!  400
    Candle-tradable names: NONE

The bridge cannot serve a 10-year yield under any known alias. Path 1 is
not stale — it never existed. US10Y is therefore Pine-only, confirmed by
measurement rather than inference, and the honest UNKNOWN on the
cross-asset card is the correct behaviour, not a bug to patch.

DXY is NOT at the same risk: the alias list already carries the successor
contract (DXY,USDX,USDOLLAR,DXY_U6,DXY_Z6,DX1!), so when the September
contract rolls, December is tried next automatically. Checked, not
assumed — no action needed there.

DECISION: no feed is built tonight. A Pine-independent yield source is a
NEW ORGAN (external feed, network dependency, its own failure modes) and
the ceremony applies — spec and offline harness first, one organ per
week. Until then US10Y stays honestly UNKNOWN whenever Pine is silent,
and the gold context runs on DXY alone with that fact stated on the card.

Reassess after the v18.13 ceremony: if US10Y resumes, the dependency is
proven and the organ is a planned upgrade, not an emergency.

## BRIDGE SYMBOL PROBE — 2026-08-31, MEASURED ON THE BOX

    SILVER 200 · GBPUSD 200 · US30 200 · USTEC 200 · GOLD 200 · BTC 200
    US100  400  (no such symbol on this bridge)
    All served names: 5 bars, newest 23 min old — feed healthy, market open.

Two open items close on this evidence:

1. "BRIDGE 400 ON US100 LIVE CANDLES" — CLOSED, and it was never a bug.
   The broker's name for that index is USTEC. US100 is a display name
   only. Any caller asking the bridge for "US100" gets a 400 forever.
   The brain is already correct (CORE uses USTEC, line 175); the alias
   must be resolved CALLER-SIDE by anyone else who asks. US100's bias
   silence was therefore the Pine death alone, not this.

2. "US30/USTEC EXECUTION PROBE" — the FEED half passes: both serve live
   candles. Order acceptance is a SEPARATE, human-approved probe and is
   still open; a served candle proves data, never fill.

auto_live's hunt list (SILVER, GBPUSD, US30 — the cost-discounted net
earners) is unchanged: all three are tradable. Nothing is added on this
result. GOLD and BTC also serve candles, but their nets were −0.091 and
+0.133; a feed being available is not evidence to trade it.

## ALERT CENSUS — 2026-08-31, MEASURED FROM THE JOURNAL

Real Pine alerts only (session_caller paper excluded — counting paper as
a Pine alert is what made two earlier readings wrong):

ON v18.13, FIRING (ceremony done, one fire each since recreation):
    TVC:USOIL 3.5h · TVC:SILVER 6.5h · FX:USDJPY 11.5h ·
    BITSTAMP:ETHUSD 14.7h · COINBASE:XRPUSD 23.0h

STILL ON v18.12 — alert never recreated, still running the dying script:
    BITSTAMP:BTCUSD  42.7h   [18.12:39@43h]
    FOREXCOM:US30   118.2h   [18.12:14@118h]
    OANDA:XAUUSD    141.5h   [18.12:10@141h]

NO REAL ALERT FOR WEEKS — recent rows were session_caller paper only:
    PURPLETRADING:US100  770.5h (32 days!)  [last real: 18.8]
    FX:EURUSD            458.5h (19 days)   [last real: 18.12]
    ACTIVTRADES:USA500   770.7h (32 days)   [retired, delete]

RETIRED NAMING ERA (bare tickers, 53-66 days, no action):
    TVC:GOLD · BTCUSD · XAUUSD · XAGUSD · EURUSD · ETHUSD · MIRRORTEST

### TWO CORRECTIONS TO EARLIER READINGS IN THIS FILE

1. "US100 silent 70h" and "GOLD silent 109h" were PAPER rows. The real
   figures are US100 32 DAYS and OANDA:XAUUSD 141.5h. US100 is far worse
   than reported: it has had no genuine Pine alert since v18.8.
2. The claimed match between US10Y's 2.9-day staleness and US100's 70h
   silence is RETRACTED — 70h was session_caller, so the correlation was
   with paper, not with Pine. US10Y's staleness needs its own diagnosis
   once the alert set is healthy. A coincidence dressed as a cause is
   exactly what the journal exists to prevent.

The ceremony was PARTIAL, not skipped: 5 of 8 active alerts carry 18.13.

## INCIDENT EVIDENCE ARCHIVE (2026-09-02) — ingest blocked, record preserved here

The platform incident route answers 401 unauthenticated (alive) but 404s
authenticated POSTs for INC-0001/INC-0002 after the v5.01 rebuild — the
same script landed INC-0003 before it. Pending the platform's answer
(changed ids, or changed payload key), the corrected findings live here
so no verdict depends on chat scrollback:

INC-0001 (US10Y 15m) — CORRECTED, real feed break, NOT calibration:
  Stored history query (read-only, live): 12,949 rows, first
  2025-01-08 21:00Z, LAST 2026-08-27 20:58Z. Nineteen months of 15m
  flow, hard stop 6 days ago. The v7 bridge never served yields
  (measured 404s), so the feed came from the v18/reporter MT5 path.
  Next: reporter config+logs around 2026-08-27 21:00Z, especially any
  BB_CANDLE_SYMBOLS change; reporter source location still unknown.
  My earlier "never flowed / watcher calibration" draft was WRONG and
  never reached the record — the failed post blocked it. Lesson kept:
  a verdict is posted only with its query output embedded.

INC-0002 (bias silent) — alias mismatch confirmed in code:
  OIL vs USOIL: push_bias.py emits BOTH — macro_items symbol=OIL
  (line 170, oil_spike on every scalp, always fresh) vs derive_bias
  USOIL (journal decisions only): a USOIL watcher starves beside a
  fresh OIL. XRP vs XRPUSD: brain pushes ONLY XRPUSD; bare XRP exists
  nowhere in brain/session_caller — any XRP/XRPUSD split is in the
  platform canonicalizer. USA500: intentionally absent (not in CORE-8;
  alert dead 32d). PROPOSAL, nothing changed yet: ONE canonical set =
  the platform UI's 14 display names, owned by the platform
  canonicalizer at ingest; brain keeps pushing raw names; no push list
  edited until the platform session agrees in writing.

## ROUND 3 (2026-09-02, bot boss session) — INC-0001 / INC-0003 / US10Y lineage

### The reporter is found, versioned, and explains two incidents at once
- "reporter source location still unknown" (archive above) — CLOSED. It is
  `Sniper-System/agents/mt5_reporter/mt5_reporter.py`, REPORTER_VERSION
  1.6.0, committed 2026-08-22 (platform commit 5260ce9). It reads
  BB_CANDLE_SYMBOLS from the service's registry-level environment (plus an
  ALWAYS_ON crypto list) and every cycle posts, in order:
  /api/v1/heartbeat/account → /api/v1/heartbeat/vps → trade → candles.
- INC-0003 (VPS heartbeat "unwired"): the writer EXISTS — report_vps()
  posts every cycle with the same API key that posts candles. Nothing to
  build bot-side. If the board reads never-posted while candles once
  flowed, either the reporter is down or its key belongs to a user whose
  row the board is not reading. Also: the 38-day-old "user 1" row quoted
  in INC-0003 is the SEED row (Sniper-System/scripts/seed.py:67, updated_at
  stamped at seed time) — that 54971m was the age of the demo seed, never
  of a reporter.
- INC-0001 (US10Y 15m stopped 2026-08-27 20:58Z): the platform's US10Y
  candles come from the reporter under the broker name UST10Y_U6 (platform
  alias UST10Y*→US10Y; the 08-20 probe read UST10Y_U6 108.834). The
  reporter has NO front-contract resolver — it is a static env list — so
  when the broker retires the September (U6) contract it keeps asking for
  a dead name and US10Y goes silent with no error. 08-27 is five days
  before the ZN first-notice date (08-31), the usual CFD roll window.
  TWO hypotheses, ONE read-only query separates them (platform side):
      last candle ts per symbol WHERE source = 'mt5:<reporter login>'
  · only US10Y stopped at 08-27 20:58Z, DXY etc. current → CONTRACT ROLL.
    Fix is Windows config, after a probe proves the successor is served:
      (Contabo)  python3 probe_symbol_specs.py UST10Y_Z6 UST10Y_H7
      (Windows, admin PowerShell)
        nssm get BrotherBotReporter AppEnvironmentExtra
        → in BB_CANDLE_SYMBOLS replace UST10Y_U6 with the served successor
          (append-only to everything else), then
        nssm restart BrotherBotReporter
      Proof: platform US10Y 15m rows advancing past 2026-08-27.
    Proper fix (spec for the platform session, which owns that file): the
    reporter resolves DXY/US10Y/US30Y to the nearest non-expired contract
    by MT5 expiration_time, hourly cache, and logs "rolled, no successor"
    instead of silently pushing nothing.
  · EVERY reporter symbol stopped at 08-27 20:58Z → the SERVICE DIED:
      nssm status BrotherBotReporter
      Get-Content C:\brotherbot\*.log -Tail 50
    and INC-0003 closes with the same restart.
- CORRECTED within the hour (partial read, lesson C1 again): the bridge's
  front-contract resolver IS pushed — brother_sniper_v7 branch
  claude/brain-platform-mirror-fcacwl, fc5bd6f (2026-08-20), with
  tests/test_front_contract.py — but not on the deploy branch (34/41
  commits diverged). The 08-31 bridge probe reading US10Y 404 / UST10Y 404
  while unknown names read 400 is that resolver's own "rolled and no
  successor" answer: the bridge already knew on 08-31 that no live 10Y
  contract existed on the terminal. Whether the Windows bridge runs the
  resolver is measured, not assumed (Select-String for _macro_front).

### MEASURED 2026-09-02 14:52-14:54 (Shyam's Windows reporter log, quoted)
    WARNING PUSH UST10Y_U6 1m/15m/1h/4h/1d: symbol_select failed — symbol
    not known to this terminal; 0 bars pushed
    INFO account heartbeat ok (47 ms) ... (62 ms)
- The reporter is ALIVE and cycling. INC-0003's writer runs: report_vps()
  posts right after the account heartbeat that logged "ok". If the board
  still reads never-posted, the row it reads is not the row this key
  writes — a platform-side question, not a bot-side one.
- INC-0001 is the CONTRACT ROLL, confirmed: UST10Y_U6 is gone from the
  terminal, the static list keeps asking, five timeframes push 0 bars
  every cycle with a WARNING that nobody reads. Successor probe pending
  (Windows one-liner in chat); if the terminal lists no 10Y contract at
  all, the honest outcome is "US10Y price candles UNAVAILABLE at this
  broker" and the platform series ends at 08-27 — not a bug to patch.
- PRE-EMPTIVE, same mechanism, ~2 weeks out: BB_CANDLE_SYMBOLS carries
  DXY_U6, the September dollar-index contract. It rolls mid-September and
  the platform's DXY candles die the same silent way unless the successor
  (DXY_Z6) is put in the list first or the reporter gains the resolver.
  Probe DXY_Z6 in the same run.

### US10Y is two inverse quantities under one name (finding for the platform)
Pine's yield_dir is computed from TVC:US10Y — the YIELD (≈4.x%). The
platform's US10Y CANDLES come from UST10Y_U6 — the T-Note futures PRICE
(≈108). Price and yield move inversely. So a bias row "US10Y bearish"
(yield falling, Pine via push_bias) and an EMA200/MTF trend computed on the
US10Y candle series (note price) point opposite ways while both are
correct. Platform ask #4 ("brain says BEARISH, AssetPulse bullish") must
first ask WHICH quantity each side reads; both Pine scripts read the yield
(main script line 346/738, AssetPulse line 58), so a disagreement between
them is freshness — push_bias takes the newest journal row carrying
yield_dir, which is as old as the last scalp alert and is stamped as_of.
Proposal, nothing changed: the platform stores the note-price series under
its own name (e.g. US10Y_PX) and keeps US10Y for the yield, or converts at
read time. No alias edit until the platform agrees in writing (5.03).

### 2026-07-31 audit P1s — all present on this branch (grep-verified, file:line)
P1-1 fail-soft budget: brain/src/main.py:55 `_failsoft_state`, :442
`FAILSOFT_MAX_PER_DAY` · P1-2 midnight rollover: executor_ic_markets/src/
utils/state.py:50 `roll_if_new_day`, called from main.py:66 and :416 ·
P1-3 signal_id in dispatch + executor dedup: brain/src/main.py:485;
executor main.py:199-200 NonceStore `signal_ids`, :417-419
`duplicate_signal_id` · P1-4 min-lot guard: ic_markets/mt5_bridge.py:229
(`raw_lots < volume_min * 0.4`) · P1-5 market price from the live tick:
mt5_bridge.py:363 `symbol_info_tick`. The "STEP 7 P1s" of the 2026-09-01
order are a DIFFERENT list that lives only in the never-pushed audit file;
it must be re-issued before anyone can work it.

### MEASURED 2026-09-02 ~15:00 (Windows, MT5 catalogue of account 52901228 = v18 terminal, quoted)
    ITB10Y_U6 | Euro BTP Italian 10 YR -September 26 CFD | expires - | visible False
    JGB10Y_U6 | Japan JGB 10 YR -September 26 CFD       | expires - | visible False
    DXY_U6    | US Dollar Index -September 26 CFD       | expires - | visible False
    (patterns *10Y* *NOTE* *DXY* *USDX*; no UST10Y*, no UST30Y*, no DXY_Z6)
- NO US 10-year contract exists in this terminal's catalogue. The broker
  delisted the T-Note CFD with the September roll, with no successor. On
  this terminal INC-0001's honest outcome is: US10Y PRICE CANDLES ARE
  UNAVAILABLE AT THIS BROKER; the series ends 2026-08-27 20:58Z; yield
  DIRECTION still arrives from Pine (TVC:US10Y). Not a bug to patch.
  Caveat, one probe outstanding: the reporter attaches to the v7 terminal
  (52834417); the same listing there is the closing evidence.
- "expires -" on every contract: this broker leaves expiration_time at 0
  on its dated CFDs, so NO resolver can know the roll date from MT5
  metadata; the mirror-branch resolver's suffix fallback is the only
  signal. DXY_U6 will vanish the same way in mid-September and DXY_Z6 is
  NOT listed yet — nothing can be pre-configured today. Watch item: the
  first "PUSH DXY_U6 ... symbol not known" line in the reporter log is the
  trigger; then list *DXY* again and swap the name in BB_CANDLE_SYMBOLS.
- Bridge on the box: `Select-String sniper_executor.py -Pattern _macro_front`
  = 2. The Windows bridge IS the mirror-branch bridge (resolver live) plus
  the A1 patch. The deploy branch's sniper_executor.py (DXY→USDX, no
  resolver) must NEVER be copied over it until the branches converge.
- Housekeeping, Shyam's call: UST10Y_U6 in BB_CANDLE_SYMBOLS now logs five
  WARNINGs per cycle for a name that can never serve; removing it silences
  noise that hides real warnings. Config on the box, logged when done.

### INC-0001 — RESOLVED on the board 2026-09-02 ("posted INC-0001 -> 200", quoted)
Closing evidence, both terminals by path (Shyam's PowerShell, quoted):
    C:\MT5_v18\terminal64.exe                              login 52901228
    C:\Program Files\MetaTrader 5 IC Markets EU\terminal64.exe  login 52834417
    10Y: ['ITB10Y_U6', 'JGB10Y_U6']   DXY: ['DXY_U6', 'DXYZ.NYSE-24']   (identical)
The v7 terminal the reporter reads has no US 10Y contract either. Verdict
stands: broker delisted the T-Note CFD at the September roll, no
successor; US10Y price candles UNAVAILABLE at this broker from
2026-08-27 20:58Z; yield direction remains Pine-only. Not a bug.
Still open from this: (a) DXY_U6 watch (mid-September), (b) UST10Y_U6
removal from BB_CANDLE_SYMBOLS (Shyam's call, noise only), (c) INC-0003
is a platform-side row question — the reporter's writer runs.
Observation, not a finding: the v18 path appeared twice in the process
list — two terminal64 processes from C:\MT5_v18. Worth one look
(`Get-Process terminal64 | Select Id,StartTime,Path`) before anyone
reads a v18 ticket count.

### 2026-09-02 evening — platform 5.06 hands back two bot-side facts
1. THE LIVE REPORTER IS 1.1.0 (board row 4, ea_version, quoted by the
   platform session). The repo holds 1.6.0. Five versions behind: no
   two-witness broker clock (1.4.0), no per-bar DST conversion (1.5.0), no
   retry on 502/503 (1.6.0). The clock on the box is the pinned scalar
   BB_BROKER_UTC_OFFSET=3 — correct until the EU clock change on
   2026-10-25, then every bar an hour wrong, the exact 08-20 failure with a
   date on it. Also: the log Shyam pasted at 14:52 says "symbol not known
   to this terminal", a string that exists ONLY in 1.6.0 — so a 1.6.0
   process writes the log while a 1.1.0 process writes the board. TWO
   REPORTERS, ONE ROW is the leading hypothesis (two writers of one desk,
   the failure SESSION_COORDINATION already names). Measure, don't guess:
     Get-CimInstance Win32_Process -Filter "name='python.exe'" | Select ProcessId,CreationDate,CommandLine
     Get-Service | ? {$_.Name -match 'Reporter|Brother|Sniper'} | Select Name,Status
     Get-ChildItem C:\ -Recurse -Filter mt5_reporter.py -ErrorAction SilentlyContinue | Select FullName,Length,LastWriteTime
     Select-String C:\brotherbot\mt5_reporter.py -Pattern 'REPORTER_VERSION ='
2. ROW 4 SAYS mt5_running=false EVERY MINUTE. In every reporter version
   that field is `terminal_info() is not None`, so the 1.1.0 process is
   not attached to a live terminal while its account heartbeat still
   posts. Platform 5.06 now holds RED on that ("reporting but NOT
   TRADING") and it is right to. The same process listing above answers
   which process, attached to which terminal.
3. SHIPPED (Sniper-System, branch claude/session-44nji4, bot-side commit
   on top of v5.06): reporter 1.7.0 — heartbeat carries service_version,
   git_commit (deploy sidecar/env, never guessed), file_sha256; logs why
   when it reports mt5_running=false. Tests tests/test_reporter_identity.py
   (6), suite 634. Deploy to Windows = the ceremony below, ONE reporter
   process at the end of it.

### MEASURED 2026-09-02 (Windows process list, quoted) — FIVE reporters, one row
    4536   8/8  00:52  python C:\brotherbot\mt5_reporter.py
    7424   8/8  01:24  python C:\brotherbot\mt5_reporter.py
    10104  8/8  13:59  python C:\brotherbot\mt5_reporter.py backfill
    2868   8/8  20:18  python C:\brotherbot\mt5_reporter.py backfill
    5016   8/21 18:57  python C:\brotherbot\mt5_reporter.py        <- the NSSM service
    C:\brotherbot\mt5_reporter.py  33307 bytes  written 8/21 18:56:49  REPORTER_VERSION "1.6.0"
    services: BrotherBotReporter Running · SniperExecutorV18 Running · SniperExecutorV7 Running
- Python loads a file once. The four 8 August processes hold the 1.1.0
  text in memory; the file under them was replaced on 21 August and the
  service (5016) was started 21 seconds later. Row 4's "reporter-1.1.0 /
  mt5_running=false" is one of the four orphans: attached in August to a
  terminal that has since been restarted, still posting its account and
  VPS heartbeats every minute with the same API key, overwriting the
  service's honest 1.6.0 row. The two "backfill" runs have been alive for
  25 days — a backfill that never exits is hung or looping; its upserts
  are idempotent, so stopping it loses nothing.
- Therefore: INC-0003's "NOT TRADING" RED is the orphans, not the
  terminal. The service's own log (14:52) shows a live attach. The fix
  is to stop exactly the four August PIDs, never the service, then watch
  the board settle on one identity; THEN deploy 1.7.0 with the sidecar.
- Standing rule from this: ONE reporter process per box. A manual run
  ("python mt5_reporter.py" or "... backfill") that is not stopped
  becomes a second writer of the same row and the board lies for weeks.
  Every manual reporter run ends with the process list checked.

### INC-0003 — CLOSED on evidence 2026-09-02 (board row quoted by the platform session)
    user_id 4 | updated_at 2026-09-02 14:57:48+00 | ea_version reporter-1.7.0 |
    mt5_running t | git_commit 4df80fefd328 | file_sha256 (empty, column added after)
Reporter log (Windows, quoted): "broker timezone Europe/Athens validated
against a measured +3h offset" · "attached to MT5 account 52834417;
reporting to https://app.signalmesh.dev every 60s" · "account heartbeat ok".
Process list after the deploy: reporter PID 5336 (service) + four August
orphans (4536, 7424, 10104, 2868) — stop order issued; the listing after
Stop-Process is the last line this record needs.
- mt5_running is TRUE on the row the service writes. The "NOT TRADING"
  reading was the orphans' row, as measured, not the terminal.
- git_production_match: the platform adopted file_sha256 and expects
  e4dcc04bc382582207165ee9da1b2db8ac81eda7199aa729c01e37b34722fef5 (the
  repo file at 4df80fe, verified here by sha256sum). The next heartbeat
  after their deploy fills the column. CAVEAT, foreseeable: a default
  Windows git checkout converts LF to CRLF; that copy hashes to
  c09a5bc25f638e3273b5c95bd7fe5ad7a5df881d369ab9e422223a9fb26744f6 and the
  board would read AMBER "running bytes differ" — true, and harmless.
  Fixed at the source: .gitattributes `agents/** text eol=lf` in the
  platform repo (bot-side commit on claude/session-44nji4); the Windows
  re-checkout paste is in chat. Measure first: Get-FileHash on the box.
    FINAL LISTING 2026-09-02 (quoted): python.exe = 9964 sniper_executor.py ·
    10728 uvicorn src.main:app (v18) · 5336 C:\brotherbot\mt5_reporter.py.
    ONE reporter. The four August PIDs no longer existed when the stop
    order ran; the listing, not the order, closes INC-0003.
    Get-FileHash C:\brotherbot\mt5_reporter.py = C09A5BC2… — the CRLF copy,
    as foreseen. Board will read AMBER (bytes differ) until the LF
    re-checkout lands; harmless, not a fault. .gitattributes fix rebased
    onto platform v5.07 as 7b227d2 (claude/session-44nji4).

### NVDA PHASE 1 — brain side SHIPPED 2026-09-02 (platform 5.08 alias gate open)
src/shadow_gate.py + main.py hook: a symbol in SHADOW_SYMBOLS (default
"NVDA") is judged by the council, journaled with its full trace
(dispatch_mode "blocked_shadow"), mirrored to the platform as
rejected_by ShadowGate with the council verdict in the reason — and NEVER
reaches dispatcher.dispatch. Going live = removing it from SHADOW_SYMBOLS,
a logged human decision. v7 arm refuses NVDA by construction (bot.py
ALLOWED_SYMBOLS, "unsupported"), pinned by tests/test_shadow_symbols.py.
Tests: brain/tests/test_shadow_gate.py (6). Deploy: git pull + restart
brother-brain; proof = journal row with dispatch_mode blocked_shadow on the
first NASDAQ:NVDA alert.

### NVDA PHASE 1 — LIVE 2026-09-02 18:33 (all three legs configured, quoted)
- Brain: brother-brain restarted 18:33:01 with the shadow gate (3ac9d0f).
- Reporter: BB_CANDLE_SYMBOLS now ends ",NVDA.NAS-24" (registry, quoted);
  restarted 18:33:34, attached to 52834417. First "PUSH NVDA.NAS-24" line
  not yet seen in the pasted tail — still owed.
- TradingView: alert created on NASDAQ:NVDA, frozen Pine (Shyam).
PROOFS STILL OWED before "collecting": (1) reporter log "PUSH NVDA.NAS-24
15m ... bars pushed" > 0; (2) first decisions.jsonl row with
dispatch_mode "blocked_shadow"; (3) platform shows NVDA candles under the
canonical name.

### DATED LANDMINE — the pinned offset dies on 2026-10-25 (found in the 1.7.0 startup log)
"broker UTC offset PINNED by BB_BROKER_UTC_OFFSET: +3h" then "timezone
Europe/Athens validated against a measured +3h". validate_broker_tz()
REFUSES TO RUN (SystemExit) when the tz calendar disagrees with the
offset in use. On 2026-10-25 Europe/Athens becomes +2 while the pin says
+3: the service exits at start, NSSM restarts it every 5s, forever, and
every feed stops — silently, on a Sunday. The pin was for reporter 1.1.0
(no detection). 1.7.0 detects from >=2 fresh 24/7 witnesses. FIX (config,
Windows): remove BB_BROKER_UTC_OFFSET from the service environment and
restart; the start log must then show a DETECTED offset line, not PINNED.
Do it now, not in October.

### 2026-09-02 18:48 — pin removed, DETECTED clock, NVDA ticking (Windows log, quoted)
    INFO broker UTC offset detected: +3h (agreed by AUDUSD, BTCUSD, DXY_U6,
    ETHUSD, EURUSD, GBPUSD, LTCUSD, NVDA.NAS-24, NZDUSD, SOLUSD, US30,
    USDCAD, USDCHF, USDJPY, USTEC, XAGUSD, XAUUSD, XRPUSD)
Landmine defused: no BB_BROKER_UTC_OFFSET; two-witness detection at every
start; NVDA.NAS-24 is served and fresh (it voted). The reporter logs
candles only on FAILURE (0 bars / stored-count mismatch), so "no NVDA
line" after a healthy start means pushes succeeded — the platform's row
count is the proof, not the log.

### PINE-INDEPENDENT ANALYSIS OF NVDA — already exists, in shadow (Shyam's ask 18:50)
"Pine did not alert" is normal: Pine fires only at its own setups. The
bot's own analysis without Pine is auto_live.py (auto-live-v1, pullback
engine, reads closed 15m candles from the bridge, journals candidates to
logs/auto_live.jsonl and posts scenarios to the platform; AUTO_LIVE_ARM=0
posts nothing to v7). Adding the broker name to AUTO_LIVE_SYMBOLS puts
NVDA under that engine IN SHADOW with zero code: two gates keep it
shadow — the ARM flag, and v7's ALLOWED_SYMBOLS refusing NVDA even if
armed. This MEASURES whether the pullback logic fits NVDA; the "different
logic" Shyam expects is designed from that record (phase 2), not before.
Config: AUTO_LIVE_SYMBOLS=SILVER,GBPUSD,US30,NVDA.NAS-24 in the v7 .env
(broker name, because the box bridge passes unmapped names verbatim to
MT5 and has no NVDA alias). Proof: a scenario row for NVDA.NAS-24 in
logs/auto_scenarios.jsonl, and the platform showing it under NVDA.

### NVDA context — what the bot side OWES the card (Shyam's read of the NY lane, 2026-09-02 evening)
1. MAJOR_EARNINGS rows in the calendar feed (platform ask #3, open since
   08-28, now material): the platform's "earnings = special risk state"
   can only be a FACT on the NVDA card if the brain's calendar push
   carries the earnings date. Bot-side organ, harness-first as usual;
   until it ships the card must say "earnings date UNKNOWN", never
   assume clear skies.
2. Session tiers for a single-stock CFD are not Asia/London/NY. The
   honest tiers are REGULAR (09:30-16:00 America/New_York = 13:30-20:00 UTC summer, 14:30-21:00 winter; the only liquidity worth
   the name), PRE/AFTER-MARKET (tradable, thin, spread wider — measure
   it, the overnight spread is still unmeasured), OVERNIGHT/WEEKEND (if
   the broker quotes, do not read it as Nasdaq). Every NVDA state must
   carry its tier: a BREAKOUT_CONFIRMED in after-hours is a weaker fact
   than the same words at 15:00 UTC. Platform read-model work; the bot's
   session engines (scalp/session/swing-v1) stay frozen.
3. Direction on a state card: BREAKOUT_CONFIRMED must name the SIDE
   (UP above 218.550 / DOWN below 216.050) — a state without a side is
   half a fact. It must NOT say BUY/SELL: the card judges state, the
   engines decide, and 16 closes after the break the actionable event
   is the RETEST the card already names, not a chase at +3 ATR
   (Location-Gate evidence: far entries bleed).
4. Cross-asset for NVDA = US100 first (one exposure, PLAT-EXPOSURE-1
   pending Shyam), DXY second, yields only via Pine's yield_dir (the
   US10Y price feed is gone).

### BIAS PUSH GAPS (platform relay 2026-09-02: XRP 1d, SILVER 2d, US100 5d, recurring) — ROOT CAUSE
push_bias computes a FRESH candle-derived bias for the CORE list every
30 min (market_bias: 260 H1 bars from the bridge, EMA20/50/200 + ATR),
and falls back to the journal's last decision otherwise. Two facts:
1. XRP was NOT in CORE — its bias was journal-only, so it went silent
   whenever Pine was silent on XRPUSD. Structural, not intermittent.
   FIX: XRPUSD joins CORE_DEFAULT (BIAS_CORE_SYMBOLS overrides).
2. SILVER / USTEC(US100) ARE in CORE, so their gaps mean market_bias
   returned None — and it returned None SILENTLY for "< 210 bars" and
   "ema/atr invalid" (only exceptions printed, and only the type). The
   box log therefore cannot say why, which is why the gap looks like a
   mystery that "recovers" and returns. FIX: every None now logs
   "[bias] SYM: NO fresh row — <reason>" plus a per-cycle summary line;
   the NEXT gap is diagnosed from logs/bias_push.log, not guessed.
   Leading hypotheses for the reason line to confirm: the bridge
   returning < 210 H1 bars after the Windows executor restart (MT5 fills
   history lazily), or a 10s timeout on a busy single-threaded bridge.
Tests: brain/tests/test_bias_gap_reasons.py (5). Proof: the first
"[bias] ... NO fresh row" line in logs/bias_push.log names the reason.

### FAIL-SOFT (audit P1-1 policy, 2/2 spent 2026-09-02) — now VISIBLE, decision still Shyam's
The council API failed twice on A/A+ signals today; both traded on Pine
trust under the bounded fail-soft (max 2/day, then fail-closed). The
platform could not tell: the mirror sent "approved, council 0/0". Shipped:
the mirror payload carries fail_soft (bool, always), fail_soft_reason and
fail_soft_count (append-only), and main.py always lands the marker even
when the trust result has no trace. Tests: tests/test_mirror_failsoft.py
(3). UI: render "TRADED WITHOUT COUNCIL (fail-soft n/2)" on those rows.
DECISION OWED BY SHYAM (Iron Rule 1 exception): keep fail-soft at 2/day,
lower it, or fail-closed always. Evidence to decide with: outcomes of
every journal row with trace.agent_error_fallback (grep decisions.jsonl).
Not changed tonight.
Log to read tomorrow: grep -c AgentError brain/logs/*.log and the provider
error codes (429/500/529) — a wallet/limit problem looks like an outage.

### "GOLD SELL still open" (ticket 1900277473) — ROOT CAUSE, measured 2026-09-03
MT5 deals: pos 1900277473 on 52834417, IN 4359.46 @ 2026-09-01 15:00:12Z,
OUT 4330.18 @ 18:38:40Z (tp; v7 log: profit=58.56). Platform trades table:
    id 155 | open_time 15:00:17.950 | status closed | close_time 21:38:51
    id 156 | open_time 15:00:18.022 | status open   | sl 4377.69
Two rows, same (user 4, account 3, ticket), created 70 ms apart, both
"open": TWO REPORTER PROCESSES posted the same open position at the same
instant (the August orphans, five reporters at the time), and the
platform's read-then-insert upsert had no uniqueness on (user, account,
ticket). The close from history updated the first match (155); 156 has
been an orphan since, and every STOP_THROUGH/ORPHAN management row
descends from it. The reporter's close post was correct; the forked
v7 id contract is NOT involved; the 502s on 09-02 18:09 were a platform
deploy window, retried and landed.
Bot side: the concurrent writers were removed 2026-09-02 (one reporter,
PID 5336) — recurrence is closed on this side. Platform side: dedupe the
existing duplicate ticket rows (keep the row that carries the close, log
the removal) and add a unique index on trades(user_id, account_id,
ticket) so a race can never mint a twin again. Then the orphan mgmt rows
resolve on their own.

### SILVER / US100 "bias STALE" — THE ACTUAL ROOT CAUSE (from the pushed list, 2026-09-03 21:00Z)
    pushed=15 (XAUUSD, XAGUSD, USTEC, US30, EURUSD, USDJPY, BTCUSD, ETHUSD,
    XRPUSD, DXY, SILVER, US100, USOIL, US10Y, OIL)
Two rows per instrument: the FRESH market read under the broker name
(XAGUSD, USTEC) and the STALE journal opinion under Pine's name (SILVER,
US100). merged_items deduped by raw name, the platform canonicalizes both
to one symbol, and the stale row landed last — every 30 minutes, for a
week. GOLD escaped (Pine XAUUSD == broker XAUUSD); XRP escaped (no journal
row). Earlier "bridge returns < 210 bars" hypothesis: WRONG, retracted —
the fresh read was always there. FIX (ba966f1 + this): dedupe by
canonical name; the council opinion rides on the fresh row as
council_as_of; rows keep their own names. Also fixed: BIAS_* settings
were read from the process env only, so the .env lines for NVDA and the
retired US10Y aliases did nothing; _cfg() honours .env and an explicit
empty. PROOF: next pushed= line has no SILVER/US100/USOIL twins, carries
NVDA, and prints no US10Y gap lines; the Radar's SILVER/US100 bias age
drops to minutes.
PROVEN 2026-09-03 21:08:41Z (quoted): pushed=14 (XAUUSD, XAGUSD, USTEC,
US30, EURUSD, USDJPY, BTCUSD, ETHUSD, XRPUSD, NVDA, DXY, USOIL, US10Y,
OIL) resp updated=14 refused=[] — no SILVER/US100 twin, NVDA present, no
gap line. Remaining cosmetic: USOIL (journal) and OIL (Pine oil_spike)
both go out; the platform has USOIL RETIRED, so it is inert. Canonical
dedupe for the macro fallback path is a later tidy, not a fault.

## 2026-09-04 — Job 3 dual-MT5 isolation evidence (bot-side engineering window)
Re-runnable reproductions under `tests/audit/2026-09-04_job3/` (run:
`python3 -m pytest tests/audit/2026-09-04_job3 -q`; green `test_repro_*` =
gap still present). P0s on this arm, each with a memory record in
`brother-developer/brother_developer/memory/bugs/BUG-2026-09-04-ISO*.json`:
ISO-09 bridge attaches with no login assertion (mt5_bridge.py:42-71),
ISO-10 signed envelope has no account (envelope.py:40-49, main.py:371-373),
ISO-12 daily-loss counter drops a loss on unreadable balance (main.py:168,
state.py:67), ISO-14 LIMIT->MARKET conversion (mt5_bridge.py:377-386),
ISO-16 no global kill reaches both arms. Nine box flags are UNKNOWN from
the repo (DRY_RUN, MT5_LOGIN, MT5_PATH, MAGIC_NUMBER, GUARDS_DISABLED,
ADMIN_HALT_TOKEN, BRAIN_DISPATCH_MODE, EXECUTOR_IC_MARKETS_URL, v7
EXECUTOR_URL) — paste-ready read-only commands in
`brother-developer/docs/JOB3_ISOLATION_2026-09-04.md` §3. Delete this entry
only when each P0 record is `resolved` with its golden fixture named.

## 2026-09-05 — platform work order for the v18 executor /health
The platform (v5.25.4) shows the v18 account as CONFIGURED LABEL until the
executor reports it. `executor_ic_markets/src/main.py:236-249` `/health`
must gain `account_login` and `trade_mode` (MT5 `account_info().login` and
`.trade_mode`, 0 demo / 1 contest / 2 real), append-only, display-only.
This is also the first half of ISO-09's fix (the login must be asserted
against `MT5_LOGIN`, not just reported). Order stays: ISO-02 (v7) first,
then ISO-09 and ISO-10 here. Evidence: brother-developer
`docs/JOB3_ISOLATION_2026-09-04.md` §8-9.
