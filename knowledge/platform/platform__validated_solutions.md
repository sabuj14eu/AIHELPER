---
title: Sniper-System platform validated solutions
domain: platform
repo: sabuj14eu/Sniper-System
sources: docs/CHANGELOG.md, docs/OPEN_ITEMS.md, docs/HANDOFF_PLATFORM_SESSION.md, docs/audits/COMBINED_FORENSIC_AUDIT_2026-08-13.md, docs/SERVICE_AUDIT_2026-08-08.md, pine/V18.9_RELEASE_NOTES.md, pine/V18.10_RELEASE_NOTES.md, pine/V18.11_RELEASE_NOTES.md, pine/V18.12_RELEASE_NOTES.md, agents/mt5_reporter/mt5_reporter.py, app/services/candle_audit.py, app/services/trade_twins.py, app/services/position_state.py, app/services/bar_clock.py, app/services/feed_diag.py, app/services/news_lens.py, app/services/fail_soft.py, app/routers/webhooks.py
verified_on: 2026-09-16
classification: INTERNAL
---

# Sniper-System platform — problems actually solved in this repo's history

Each entry below is a problem that was diagnosed and fixed in the Sniper-System platform (or its Pine/reporter workspace), with the symptom, the root cause, the shipped fix, the rule it produced, and where the proof lives.

### Every bar stamped an hour late (the one-hour clock)
question: Why did every candle pushed on 2026-08-20 get stamped an hour late, and how was it fixed?
answer: At 23:50 UTC the MT5 reporter's `detect_broker_offset` read a single stale gold tick during the metals rollover break and inferred a +2h broker offset when the truth was +3h; every bar pushed for ~25 minutes (XAUUSD, XAGUSD, BTCUSD, part of ETHUSD) was stamped an hour late. Because the candle key is (symbol, tf, ts), the wrong rows did not overwrite the right ones but formed a second parallel series, and on 1m/15m/1h they overwrote other bars' prices in place. Reporter v1.4.0 now asks 24/7 markets first, measures staleness by comparing witnesses, and requires at least two fresh symbols (one 24/7) to agree or it refuses to run; the "Assuming 0" fallback is gone and a structural test forbids its return; both ends count stored rows. This produced the CLAUDE.md law "A CLOCK NEEDS TWO WITNESSES".
evidence: docs/CHANGELOG.md 4.41 (2026-08-21); agents/mt5_reporter/mt5_reporter.py `detect_broker_offset`; tests/test_reporter_offset.py (replays the incident's exact ticks); app/services/candle_audit.py; CLAUDE.md "A CLOCK NEEDS TWO WITNESSES".

### A scalar broker offset cannot convert a multi-year series
question: Why was the whole candle history wrong even where offset detection succeeded?
answer: The broker runs EET/EEST and MT5 returns history in server wall-clock, so the seasonal hour is inside the data. Subtracting one scalar offset from a deep backfill is wrong by an hour for every bar of the opposite season. The audit confirmed SCALAR_SUSPECTED on every multi-season series (SILVER dailies held one residue across 2007–2026, impossible for a season-aware series). Reporter v1.5.0 converts each bar through the broker's DST calendar (`server_epoch_to_utc`, zoneinfo, `BB_BROKER_TZ` default Europe/Athens); the detected offset became only a validator; Windows needs `pip install tzdata` or the agent refuses. The rebuild order was fixed as writer fix → wipe → rebuild → purge → re-audit, because a rebuild on top of the scalar table would leave three populations in one table.
evidence: docs/CHANGELOG.md 4.42; docs/OPEN_ITEMS.md "DATA INCIDENT" (second revision); tests/test_reporter_offset.py; tests/test_candle_audit.py.

### The audit condemned the correct winter bars
question: Why did the candle audit flag 3,047 correct GOLD winter dailies as off-grid after the rebuild?
answer: The modal grid test was scalar-minded: a correctly converted series has TWO daily grids (21:00 UTC summer / 22:00 winter), so the minority season looked corrupt. `grid_check` became season-aware (v4.47): when each season's dominant residue covers ≥90% of that season and the two differ by exactly the DST hour, every bar is checked against its own season's grid; on 1m–1h the seasonal hour is a whole number of bars so `season_check` says NOT_DECIDABLE_TF. Rule: internal consistency is not correctness; the tidy single grid is the suspect.
evidence: docs/CHANGELOG.md 4.47; app/services/candle_audit.py `grid_check`, `season_check`; tests/test_candle_audit.py (24 tests at 4.47).

### Wiping a series MT5 cannot re-serve destroys history
question: What stops a candle wipe from deleting bars the terminal will never give back?
answer: MT5's history depth is capped by the terminal's Max-bars setting (XAUUSD 1d answered 0 bars to a 5000-bar request), so wiping SILVER's 11,375 dailies could lose them permanently. `wipe_series` now refuses unless a verified pg_dump that mentions the symbol exists AND a depth probe under 24h old (`python mt5_reporter.py depth` → `POST /api/v1/heartbeat/feed-depth`, table `feed_depth_probes`) proves MT5 serves at least what is stored; states NO_PROBE / PROBE_STALE / PROBE_ERROR / TOO_SHALLOW / DEEP_ENOUGH / SHORTFALL_IS_FLAGGED. The probe first hit the wrong door (`/webhooks/brain/feed-depth` wants `X-Brain-Secret`, the reporter uses an API key) and got a 401, fixed in 4.44. A `--wipe-rebuilt` guard was added after a re-pasted wipe command deleted 7,483 fresh rows.
evidence: docs/CHANGELOG.md 4.43, 4.44, 4.45, 4.46, 4.47; docker-compose.yml (backups mounted read-only into app); scripts/audit_candle_offsets.py.

### Forming candles were being pushed every cycle
question: Why could research read a partial candle, and how was repainting stopped at three layers?
answer: MT5 `copy_rates_from_pos(..., start_pos=0, ...)` position 0 is the forming bar, so the live reporter pushed a partial candle each cycle. Reporter v1.3.0 fetches from position 1; the platform ingest refuses any bar whose close time has not passed; research and scanner paths run `closed_only()`. The forensic audit later confirmed closed-candle enforcement at ingest and read as a real defence.
evidence: docs/CHANGELOG.md 1.8.4 (2026-08); app/routers/webhooks.py `upsert_candles_report`; app/services/market_time.py `closed_only`; docs/audits/COMBINED_FORENSIC_AUDIT_2026-08-13.md §A.

### Future-dated candles from broker server time
question: How did the platform become immune to a misconfigured agent's clock?
answer: Reporter v1.2 auto-detects the broker UTC offset (override `BB_BROKER_UTC_OFFSET`) and the platform rejects candles more than 3 minutes in the future at ingest; production was cleaned with `DELETE FROM candles` and a full re-backfill. Rule: a wrong clock is refused at the door.
evidence: docs/CHANGELOG.md 1.8.2 (commit 860d17d); app/routers/webhooks.py (future-ts rejection).

### 202 backfilled v7 trades stored but invisible
question: Why did 202 closed v7 trades answer 2xx and never appear?
answer: The rows WERE stored (raw_payload verbatim) but the inline status whitelist did not contain "closed", so the status column silently stayed "pending". Fix: `KNOWN_SIGNAL_STATUSES` is a named vocabulary, an unknown status leaves a visible `status_unrecognized` timeline event, and `repair_signal_statuses` at startup re-reads raw_payload and fixes only rows that disagree with it — no re-send, the bot's cursor stayed at 202. Rule: Iron Rule 2 (verbatim payload) is what made the repair possible.
evidence: docs/CHANGELOG.md 4.18, 4.19; tests/test_signal_status_vocabulary.py; app/main.py startup repair.

### Every signal labelled as the v7 arm (PLAT-P0-1)
question: Why could the two-arm comparison never report a disagreement?
answer: `Signal.system` was stored raw ("BSv18"), while `opportunity._arm` and `fingerprint.lane` tested exact equality with "v18", so every row was labelled v7 and `disagreement` was always False. Fix in v3.2: `normalize_system()` at ingest plus substring-based arm/lane functions; raw_payload keeps the verbatim label. The same release threaded ONE snapshot through `build_decision_snapshot` (PLAT-P0-2) and scoped plan lifecycle to the user's accounts (PLAT-P0-3).
evidence: docs/audits/COMBINED_FORENSIC_AUDIT_2026-08-13.md §B; docs/CHANGELOG.md 3.2 (170 tests).

### A v7 verdict could be filed as a v18 decision
question: Why must v7 send `system:"v7"` and carry Pine's name separately?
answer: `normalize_system` folds anything containing "18" onto v18, so a v7 verdict labelled with the Pine system name it judged ("BSv18ULTIMATE") would corrupt the head-to-head comparison. The bot box sends `system:"v7"` and `pine_system`; the platform surfaces `Signal.pine_system` and pins the hazard by test.
evidence: docs/CHANGELOG.md 4.12; tests referenced there.

### One Pine signal counted twice
question: Why were hypothetical stats inflated ~2× and how are signals deduped?
answer: BSv18 and BSv7 both receive the same Pine alert, producing two Signal rows. `services/opportunity.group_signals` groups by `pine_signal_id` (authoritative) with a deterministic FALLBACK_ID join (symbol + direction + matching entry within 30 min), labelled as such on /funnel and never silently merged; v3.2 required real entries on both sides for the fallback. Raw rows stay untouched. The `fallback_id` watcher (>20% RED) now measures whether the brain adopts Pine's id.
evidence: docs/CHANGELOG.md 3.0.1, 3.2; app/services/opportunity.py; app/services/engineering.py `fallback_id`.

### The Daily Brief could never be stored (varchar too small)
question: Why did the Daily Market Brief produce nothing for six days?
answer: `market_briefs.current_scenario` was varchar(24) and the most common value "RANGE / WAIT FOR CONFIRMATION" is 29 characters; Postgres rejected every RANGE insert while SQLite in tests ignored the limit. Widened to 48 (and `market_snapshots.scenario` to 48) with a Postgres migration, plus `tests/test_column_widths.py` asserting every emitted vocabulary against its declared width in Python.
evidence: docs/CHANGELOG.md 4.6 (migration block); tests/test_column_widths.py.

### Swallowed exceptions hid a failed brief and a doubled API bill
question: Why did "Generate brief" say it worked when nothing was written?
answer: `POST /desk/brief` caught every exception and redirected as success; the automatic writer swallowed per-symbol failures; failed AI rounds rendered the bare word ERROR. v4.4 returns the reason to the page ("Generation FAILED — nothing was written and no API call was billed"), logs and remembers the last writer failure, and prints `ai_call.error`. Rule: never swallow an exception on a user-triggered action.
evidence: docs/CHANGELOG.md 4.4; docs/HANDOVER_V7_DESK.md "Standing constraints".

### The "one door" AI guard was theatre against the SDK
question: How is it guaranteed that every AI call is metered?
answer: The guard only banned the API hostname, so a file using the official SDK never matched. It now bans the hostname, `import anthropic`, `messages.create` and other providers' endpoints anywhere in `app/` except `services/ai_ledger.py`, strips docstrings/comments first, and a second test plants an SDK bypass and asserts the guard fires.
evidence: docs/CHANGELOG.md 4.10; tests/test_ai_ledger.py.

### The chart went blank on a one-minute feed gap
question: Why did /chart render EMPTY and what is the fallback?
answer: The chart read only the live bridge, so the daily metals rollover gap emptied it while a full stored history sat unused. v4.28 falls back to the platform's own stored CLOSED candles badged "STORED (delayed)" — never a blend, a working feed always wins — and the empty canvas explains itself. Guard: no writes anywhere on the chart path (verified by planting a `db.add`).
evidence: docs/CHANGELOG.md 4.28; tests/test_chart_bridge.py.

### The feed was never empty — the parser read the wrong keys
question: Why did the live bridge report EMPTY for a day while returning 180 bars?
answer: The bridge answers `rows` and `time`; `bridge.py` read `candles` and `ts` from the written spec, discarding every bar with HTTP 200 and no error. Fix: read both key sets, and when no recognised array exists return DOWN and print the keys actually received. Rule: BUILD TO THE WIRE, NOT TO THE SPEC — curl once before integrating.
evidence: docs/CHANGELOG.md 4.32; docs/OPEN_ITEMS.md "Platform (this repo)" standing rule; tests built from the real curl output.

### The NY panel vanished instead of failing
question: Why did the NY block disappear and what rule came out of it?
answer: The whole management + NY panel sat inside `{% if configured %}` for the bridge, which it never needed, so an unprovisioned feed deleted it silently. v4.33 renders it unconditionally, `ny_state` can no longer raise (FAULT state with reason), WAIT carries a countdown, after 21:00 UTC says NO_TRADE, every Jinja `[key]` became `.get(key, default)`, and the running VERSION is printed on every page. Rule: RENDER THE REASON, NEVER THE ABSENCE.
evidence: docs/CHANGELOG.md 4.33; app/version.py docstring.

### A passed limit is not a far one, and then the fix was inverted
question: What was wrong with the desk's "PASSED" distance label, and why did it survive 13 versions?
answer: v4.36 added a side to the distance note after one card said "FAR — not a today setup" next to "TRIGGERED (position open)", but its side test was backwards: a BUY LIMIT sits BELOW market, so price above it is the ordinary awaiting-a-pullback state, and because PASSED outranked every distance past 0.25 ATR the documented vocabulary AT ZONE/NEAR/APPROACHING/FAR was unreachable. It survived because the v4.36 test encoded the same wrong model. v5.17 keeps only the distance vocabulary, adds a separate `side` (AWAITING/THROUGH), and states that whether a limit filled is a broker fact price cannot see. v5.20 then found the chart template still compared `== 'PASSED'`.
evidence: docs/CHANGELOG.md 4.36, 5.17, 5.20; docs/OPEN_ITEMS.md "THE INVERTED LIMIT"; tests asserting the retired literal appears nowhere under app/.

### Is the far bucket measuring distance or direction?
question: Why can't the >3 ATR negative expectancy justify a distance cap yet?
answer: Counter-trend entries are the documented #1 loss driver, so if the far bucket is mostly counter-trend then −0.19R measures alignment, not distance. `desk.distance_confounders` (v4.37) cuts the buckets pooled, by side and by alignment (bias recorded at birth), returning DISTANCE SURVIVES / LIKELY COUNTER-TREND / CANNOT SEPARATE (with-trend cell under n=20). Nothing gates on it; this became the "A SPLIT SAMPLE IS A SMALLER SAMPLE" clause of EVIDENCE AUTHORITY.
evidence: docs/CHANGELOG.md 4.37; tests/test_far_bucket_audit.py; CLAUDE.md "EVIDENCE AUTHORITY".

### The 12-item evidence-integrity order
question: How is every stored distance made reproducible and every denominator explicit?
answer: v4.52 shipped contamination counts per bucket and trend-split (CANNOT SEPARATE below the floor, never re-derived from survivors), a distance funnel printing the expectancy formula verbatim (NO-FILL and PENDING in neither side, pinned by a no-fill-flood regression test), `distance_provenance` stored at birth from one candidate dict, snapshot identity chips per section, bucket labels with units, sample-strength labels, a per-round `round_snapshot_id` proof table, and a /desk self-check that renders RED with offending rows. No trading rule changed.
evidence: docs/CHANGELOG.md 4.52; app/services/evidence_integrity.py; tests/test_evidence_integrity.py (16 tests).

### 17 DXY rows failed the distance check
question: Were the 17 flagged DXY lane rows corrupt data?
answer: No. The rows were lane observations, not candles, and the check's fixed ±0.05 ATR tolerance ignored that DXY's tick (0.01) is ~0.3 of its ATR (~0.03); all deltas sat inside one-tick rounding. v4.61 made the tolerance precision-aware, `max(±0.05 ATR, one tick ÷ ATR)`, counting in-bound rows by name. Nothing in the data was repaired.
evidence: docs/CHANGELOG.md 4.61 (closed jointly 2026-08-24); docs/OPEN_ITEMS.md measurement-layer ledger.

### Stale bias rendered as a direction
question: Why did a 16-day-old "81% bullish" gate trades, and how was the Freshness Law enforced?
answer: MarketBias had no age gate. v2.2.1 treats bias older than `BIAS_MAX_AGE_H` (24 market-clock hours) as ABSENT inside `scanner.build_snapshot`, so scanner, planner, AI command and thesis engine inherit it; empty calendar → news UNKNOWN, never LOW. v2.9.2 stamps staleness from the decision's `as_of`, not post time. v4.55 stops spread-only pushes refreshing the bias clock. v4.72 found /macro still reading MarketBias raw and a dead calendar reading LOW; both fixed (72h dead-feed window → UNKNOWN).
evidence: docs/CHANGELOG.md 2.2.1, 2.9.2, 4.55, 4.72; app/services/scanner.py `BIAS_MAX_AGE_H`; CLAUDE.md "FRESHNESS LAW".

### A spread-only post stored the literal string "None" as trend
question: How did a fresh SELL ZONE appear for a symbol the brain never pushed?
answer: The bias ingest ran `str(item.get("trend", bias.trend))` on an unflushed new row, storing "None", which every zone reader treated as not-bullish on a fresh clock for 24h — a Freshness Law violation reproduced live. v4.99 creates such rows `neutral` with the bias clock at NEVER_POSTED, refuses unknown trend words, and refuses malformed items by name instead of 500-ing the whole batch (`float(confidence)` was unguarded).
evidence: docs/CHANGELOG.md 4.99 (#1, #2); tests referenced there.

### Every reporter heartbeat wiped trade→signal attribution
question: Why did the funnel and runner replay lose their trade-to-signal join?
answer: The trade heartbeat did `trade.signal_id = sig.id if sig else None`, and heartbeats rarely carry a signal_id, so each beat cleared the join. v4.99 sets attribution and never clears it: a heartbeat silent about a signal is not a denial.
evidence: docs/CHANGELOG.md 4.99 (#3); app/routers/api_v1.py heartbeat/trade.

### Open redirect on login and unauthenticated /metrics
question: What security holes did the bot-session audit find on the platform?
answer: `next` went straight from the query string into the post-auth redirect (fixed: only same-site absolute paths survive; `//evil.com`, `https://…`, backslash tricks fall back), and `/metrics` served user/account/ticket counts to anyone (fixed: `BB_METRICS_TOKEN` Bearer or `?token=`, else admin-session-only in production).
evidence: docs/CHANGELOG.md 4.99 (#5, #6); app/config.py `metrics_token`.

### Timeouts at 0.35% CPU (the weekend perf order)
question: Why did the site time out with an idle CPU, and what fixed it?
answer: Request queuing, not computation: eight /desk read models full-scanned lane_observations on every view, the synchronous sweeper ran on the asyncio event loop so every request queued behind it, and the market clock aged symbols against a running wall clock from Friday 22:00. v4.82: `read_cache.ttl_cache(60)` on read models, `uvicorn --workers 4`, sweeper in `asyncio.to_thread` with a flock electing one sweeping worker, and `market_reference_time` frozen exactly while `market_status` says closed. v4.75/4.76 trimmed ORM hydration and replaced Python bar walks with SQL aggregates after `scripts.page_timing` named the sections.
evidence: docs/CHANGELOG.md 4.75, 4.76, 4.82; app/main.py `_sweeper_loop`; Dockerfile CMD; scripts/page_timing.py.

### The "cheap" read model measured 2,180 ms on the box
question: Why did /desk still take 2.3 s after the research moved to /evidence?
answer: `desk_summary`, kept as the one cheap evidence line, calls `fill_rate_by_distance` — the same aggregation that costs ~2.5 s in the Lab — and shipped uncached. v5.12 caches it 10 minutes and the sweeper warms it every cycle; expected /desk ≈ 130 ms. Rule: measure "cheap" on the box before believing it. v5.11 had moved the thirteen aggregations whole to `/evidence` as a data-path change with a test asserting the desk route's source contains none of their names.
evidence: docs/CHANGELOG.md 5.11, 5.12; scripts/page_split_timing.py.

### A monitor took down the thing it monitors
question: What went wrong inside the v5.00 engineering watchers on day one?
answer: `run_checks` ran on the sweeper's own session, so one UNIQUE violation rolled back the entire sweep (`PendingRollbackError` killed management journal, candle prune, recorder, brief); the violation came from `_next_public_id` using `COUNT + 1` under `autoflush=False`; and NEVER_POSTED rows were reported as 20,000-day silences. Watchers now get their own session, `_next_public_id` flushes and reads the highest existing id, and never-posted symbols are named as their own fact. All three were caught by the suite.
evidence: docs/CHANGELOG.md 5.00 "Three faults the watchers themselves shipped with"; app/services/engineering.py.

### The board's first false alarm (never-posted ≠ stale)
question: Why did `check_heartbeats` raise HIGH against a row that never reported?
answer: It counted a never-posted VPS row as LATE. v5.01 returns UNKNOWN "the channel is unwired, not healthy" when nothing has ever posted, keeps genuinely stopped reporters RED, and reads a second liveness channel (the council's `brain_status` artifact, 30-min cadence), naming both on every verdict. v5.02 then stopped an incident from asserting evidence its watcher could no longer see (UNKNOWN annotates once, never resolves).
evidence: docs/CHANGELOG.md 5.01, 5.02; app/services/brain_status.py.

### A fresh heartbeat is not health
question: Why was a reporter beating every minute still a RED executor?
answer: The live `vps_status` row carried `mt5_running=false` while fresh; the old check read only the timestamp. v5.06 checks what a live row REPORTS, names reporting-but-not-trading as RED distinct from staleness, and treats silence as a fault only where a report is EXPECTED (an ACTIVE MT5 account), never inferring "not expected" from age. Rows 1–2 were demo records from 2026-07-25.
evidence: docs/CHANGELOG.md 5.06; tests/test_brain_liveness.py.

### A commit string is a label; a digest is a measurement
question: How does the platform know which reporter file is actually running on the VPS?
answer: `git_production_match` compared commit strings nobody could verify, and five reporter processes (four orphans holding 1.1.0) made the row flap. Reporter 1.7.0 sends `service_version`, `git_commit` (from a `DEPLOYED_COMMIT` sidecar or `BB_GIT_COMMIT`, never guessed) and `file_sha256` of the running file; the platform compares it to the sha256 of `agents/mt5_reporter/mt5_reporter.py` as shipped in the image (the container has no .git). States: GREEN measured match, AMBER bytes differ (a difference is not a fault), UNKNOWN labels only, UNKNOWN cannot measure. `.gitattributes` pins `agents/** text eol=lf` so a Windows checkout ships identical bytes.
evidence: docs/CHANGELOG.md 5.07 and "agent-only (bot side, 2026-09-02)"; tests/test_reporter_identity.py; .gitattributes; migration `ALTER TABLE vps_status ADD COLUMN file_sha256`.

### One SELL position opened both directional cards
question: Why did the GOLD chart show BUY — POSITION OPEN and SELL — POSITION OPEN for one SELL?
answer: `chart._bot_state` took `mgmt["positions"][0]` and emitted `stage = "ACTIVE"` (a boolean wearing a string) and `setup = "SELL ACTIVE"` (side only as display text); `market_map.side_cards` did `pos = stage == "ACTIVE"` for both sides. v5.19 added `position-state-v1` normalizing broker positions to NONE / BUY_OPEN / SELL_OPEN / HEDGED / MULTI / SIDE_UNKNOWN from Trade rows only (imports nothing, asserted by test), and four independent bot-state fields (`entry_state`, `position_state`, `management_action`, `signal_state`) rendered in the order broker position > management > entry signal > expired plan. Rule: a field only ever compared to one value is a boolean.
evidence: docs/CHANGELOG.md 5.19; app/services/position_state.py; tests/test_position_direction_519.py (cases A–H).

### One bar, two ages (21m vs 6m)
question: Why did the desk say a bar was 21 minutes old and 6 minutes old at once?
answer: Lanes measured freshness from the bar's OPEN, the session panel from its CLOSE; both true, neither labelled. `bar-clock-v1` computes both once and every consumer prints `bar 22:00–22:15 UTC · 21m since open · 6m since close`; the gate basis deliberately stayed on OPEN because switching anchors would widen every freshness window by a bar (Iron Rule 3). Residual: the session panel judges on the wall clock, the lanes on `market_reference_time`; they differ only over weekends.
evidence: docs/CHANGELOG.md 5.17 (1); app/services/bar_clock.py; tests/test_one_clock_one_price_517.py.

### The lane divided by a price it never named (4.56 vs 4.81 ATR)
question: Why did the Swing lane's entry distance disagree with a hand check?
answer: The lane divides by its own last closed 4h bar because the ATR beside it comes from 4h bars; the header showed the 15m price. Both right. The reference price is now named with its bar and the header-price formula is shown beside it, labelled; the recorded `entry_dist_atr` was not changed because it feeds stored buckets. Rule: recorded evidence is never redefined midway.
evidence: docs/CHANGELOG.md 5.17 (2); docs/HANDOFF_PLATFORM_SESSION.md §6.

### STALE named a symptom and stopped (feed diagnosis)
question: How does the desk now say WHY a feed is behind?
answer: STALE covered a broker break, a dead reporter, a closed market and a young feed. `feed-diag-v1` (v5.16) asks one decidable question from the candle table — is this symbol behind alone or is the whole cohort behind — and answers FEED_WIDE (with the peers that stopped in the same bar) / SYMBOL_ONLY / MARKET_CLOSED / NEVER_POSTED, never inferring retirement from silence; SYMBOL_ONLY is explicitly CANNOT_SEPARATE between a stopped feed and a broker session break. The bar is named by its span (`20:30–20:45 UTC`, 61m since it CLOSED).
evidence: docs/CHANGELOG.md 5.16 (1); app/services/feed_diag.py; tests/test_screen_honesty_516.py.

### One UNKNOWN, two opposite causes (EMA200)
question: Why did the desk print an EMA200 value and call it UNKNOWN?
answer: Under 200 closed bars no EMA200 is computed; with 200+ stale bars a real EMA200 exists but its trend label is withheld. Both ended at "UNKNOWN". v5.16 adds `label_state` = NO_DATA / WITHHELD / TREND beside the unchanged `label`.
evidence: docs/CHANGELOG.md 5.16 (2); app/services/trend_context.py.

### "news LOW" beside "news risk HIGH" (three questions, one word)
question: Why did the chip and the brief disagree about news, and what is the fix?
answer: The platform measures `calendar_risk` (next HIGH-impact event on any asset), `symbol_news` (does it affect THIS symbol, the planner's gate input) and `event_window` (strongest class recorded in ±24h, released events included). Both readings were true. `news-lens-v1` publishes all three by name; the Brief narrator must say which dimension; a test pins `symbol_news` to `build_snapshot` so no threshold moved; a dead calendar stays UNKNOWN on every dimension.
evidence: docs/CHANGELOG.md 5.16 (3); app/services/news_lens.py.

### A brief is a frozen snapshot and now says so
question: Why did a 13:00 brief show "data LIVE" at 21:46?
answer: One brief is written per asset per session block, so it is historical most of its life; the chip described the state at writing in the present tense. v5.16 shows age, `LIVE AT WRITING`, and a HISTORICAL BRIEF band with the brief's price beside the desk's current price; the cutoff reuses the existing candle-freshness window. v5.17 gave outlook cards the same `written at · price at writing · price now · age`, measuring price at writing from stored candles rather than adding a column.
evidence: docs/CHANGELOG.md 5.16 (4), 5.17 (5).

### A 500 on /chart?symbol=NVDA that 652 tests missed
question: Why did the NVDA chart 500 and why did the suite not catch it?
answer: A renamed variable survived inside a block that renders only for single stocks (`tier != 'NOT_APPLICABLE'`), and every page test rendered GOLD, so the block never executed. v5.14 renders /chart and /desk for NVDA in a test and asserts a real tier string. Rule: render the branch, do not grep for the words — testing the function is not testing the page.
evidence: docs/CHANGELOG.md 5.14; tests referenced there; docs/HANDOFF_PLATFORM_SESSION.md §6.

### The alias lands before the feed (NVDA)
question: Why must a broker alias ship BEFORE the reporter's symbol list changes?
answer: Pine alerts arrive as `NASDAQ:NVDA`; the reporter pushes candles under the broker name `NVDA.NAS-24`. Without the alias the instrument grows two lineages, and the v5.03 naming contract refuses to merge lineages after the fact because merging invents history. v5.08 added `NVDA.NAS-24`, `NVDA.NAS`, `NVDAUSD` → `NVDA` first; v5.10 pinned that no old alias was re-pointed. Adding an asset touches three places (aliases, `CORE_UNIVERSE`, reporter list).
evidence: docs/CHANGELOG.md 5.03, 5.08, 5.10, 5.12 "NVDA had a full desk and an empty brief"; app/routers/webhooks.py `SYMBOL_ALIASES`; docs/OPEN_ITEMS.md "ADDING AN ASSET TOUCHES THREE PLACES".

### INC-0002 was two findings wearing one incident
question: Why did the bias-coverage watcher send the bot side hunting for a push that was arriving?
answer: `canonical_symbol()` maps USOIL→OIL and XRPUSD→XRP, so rows stored under the old names can never be written again (UNREACHABLE, pre-alias legacy), while USA500 was a real coverage gap. v5.03 separates UNREACHABLE (named with what it resolves to, no incident) from a coverage gap; the dead rows' fate stayed Shyam's call and he retired them in v5.22.
evidence: docs/CHANGELOG.md 5.03, 5.22; app/services/engineering.py `RETIRED_SYMBOLS`.

### A retired instrument is not a broken feed
question: Why is US10Y not a permanent RED incident?
answer: The broker contract rolled with no successor (12,949 rows, ended 2026-08-27 20:58 UTC); left alone the watcher would hold RED forever and a permanently red board is one nobody reads. `RETIRED_SYMBOLS` records the instrument with date and evidence; retired symbols raise no incident but are still named on every verdict; a guard test asserts no age or count appears near the decision, and an entry missing date or reason retires nothing.
evidence: docs/CHANGELOG.md 5.05; app/services/engineering.py.

### The 404 that named the symptom and hid the cause
question: Why did the bot side's incident POSTs 404?
answer: They sent `incident_id`; the route read only `public_id`, so the lookup ran on '' and replied "no incident ''". v5.04 accepts both keys (an addition, not a rename), returns 400 with the received keys for a missing id, and states that incident ids are stable and never renumbered.
evidence: docs/CHANGELOG.md 5.04; app/routers/webhooks.py `/brain/incident`.

### One broker ticket, two rows (trade twins)
question: Why did the desk manage a ghost GOLD position for two days?
answer: Five reporter processes were running; two posted the same open position 70 ms apart and the heartbeat's read-then-insert had nothing to collide with, so ticket 1900277473 had rows 155 and 156; the close updated 155 and 156 stayed "open". v5.23: `trade-twins-v1` dedupe (keeps the row carrying the close, else the first; writes every removed field to `audit_log` as `trade_twin_removed`; refuses groups disagreeing on symbol/direction), a partial unique index `uq_trade_ticket ON trades (user_id, account_id, ticket) WHERE ticket <> ''`, and the heartbeat adopts the winner's row on collision. The dry run found 8 groups, not 1.
evidence: docs/CHANGELOG.md 5.23 (migration applied 2026-09-03 10:35 UTC); app/services/trade_twins.py; scripts/dedupe_trade_twins.py; tests/test_trade_twins_523.py.

### A stop that did not fire is not a stop (STOP_THROUGH)
question: What does the management panel say when price closed beyond the broker stop?
answer: An orphan position "covered 395% of the distance to the stop" was filed under EXIT_WARNING. v5.21 added `STOP_THROUGH` to mgmt-v1, evaluated before EXIT_WARNING, action EXIT, with the honest reading: either the broker already closed the ticket and the platform was not told, or the stop is not where the row says — verify in MT5, nothing here can.
evidence: docs/CHANGELOG.md 5.21; tests/test_stop_through_521.py.

### A decision the council never saw (fail-soft)
question: How is a Pine-trust trade taken because the council API was DOWN distinguished from a council approval?
answer: The mirror carried `status: approved`, council 0/0 — identical to a routine grade-gate approval. The bot side added `fail_soft`, `fail_soft_reason`, `fail_soft_count`; v5.18 reads them in one place (`services/fail_soft`) and prints "TRADED WITHOUT COUNCIL, fail-soft n/2" on every decision row; absent keys render nothing and are never turned into a "council-verified" badge.
evidence: docs/CHANGELOG.md 5.18; app/services/fail_soft.py; tests/test_fail_soft_518.py.

### The drift banner told the reader to reload for something that could not happen
question: Did the trading logic change when GOLD read "REFERENCE MOVED 2.53 ATR" with every lane blocked?
answer: No — `reference_drift` dates from v4.57 and no threshold changed; a 20-point data-release move landed on a reference from the last closed 15m bar. The banner said "reloads itself; clears when the reference is current" but only the next 15m close can move the reference. v5.24 states WHEN (`the next 15m bar closes at 12:45 UTC`) and names a calendar release inside the window when the data contains one.
evidence: docs/CHANGELOG.md 5.24; app/services/desk.py `reference_drift`.

### The bias gap between the law and the board
question: Why did the desk say INVALID while the engineering board said GREEN for the same silent symbol?
answer: The Freshness Law invalidates bias at 24 hours; `check_bias_coverage` opened incidents only past 5 days. v5.15 names symbols in the gap on the board with the law that invalidates them, deliberately without alarming, and labels recurrences `OCCURRENCE #N`. The recurring SILVER/US100 gap was root-caused bot-side as two faults (XRP structural, SILVER/US100 a silent empty read) and the prediction held (CHANGELOG 5.22).
evidence: docs/CHANGELOG.md 5.15, 5.22; docs/OPEN_ITEMS.md "BIAS PUSH GAPS — ROOT-CAUSED BOT-SIDE, c378012".

### Silence named as evidence, not a screenshot (bias coverage)
question: How is a brain bias coverage gap reported to the bot session?
answer: `scripts/bias_coverage.py` (v4.71) prints per symbol the bias age, council age, spread age and the platform's own candle age side by side and emits the relay paste, with the refusal attached: do not backfill an old opinion with a new timestamp. v4.70 had already put the two-source explanation ("brain silent 4d — candles unaffected" beside "LIVE HH/HL our candles") on the radar page itself.
evidence: docs/CHANGELOG.md 4.70, 4.71; scripts/bias_coverage.py.

### The bridge rejects US100 (broker vocabulary)
question: Why did the live bridge return 400 for US100 and how is the broker name kept out of storage?
answer: The bridge serves USTEC; US100 is a display name. v4.98 added `bridge.BROKER_TICKER`, applied on the outbound request only; canonical US100 stays in storage, pages and statistics. The same release fixed the Brief's fact-checker rejecting narratives that mentioned "US10Y" because it pulled digits out of identifiers.
evidence: docs/CHANGELOG.md 4.98; docs/OPEN_ITEMS.md BOT-BRIDGE-1 (closed 2026-08-31); app/services/bridge.py.

### The v7 heartbeat was arriving under a different kind name
question: Why did /v7 say "no heartbeat" while the log showed 200 OK on artifacts?
answer: v7 posts `kind: "v7_heartbeat"`; the page read two guessed names. v4.15 leads `STATUS_KINDS` with the real name, maps v7's real fields (`balance`, `bridge_ok`, `hard_stopped`, `open_slots`), and keys LIVE/STALE/DOWN off the real ~5-minute push cadence. Rule: read names from the sender's emitter source, never guess a contract.
evidence: docs/CHANGELOG.md 4.15; app/services/v7_view.py.

### The exit gate said 100% while the analysis table read the wrong source
question: Why did the desk show 412/200 resolved and INSUFFICIENT DATA in every bucket at once?
answer: `fill_rate_by_distance` read `decision_records` (~38 auto-lane rounds) while the gate counted `lane_observations`. v4.11 pointed it at the Phase-1 dataset, reported each bucket's engine mix instead of pooling horizons silently, and made the collector prefer the observed bar's own spread (coverage had been 16 of 2,056 rows).
evidence: docs/CHANGELOG.md 4.11.

### Position facts un-happened when price retraced
question: Why did the ETH card say "NEXT: TP1" after TP1 had traded?
answer: Position facts were re-derived from the current price on every render. v4.68 derives persistent `position_events` (ENTRY_FILLED, BREAKEVEN_ELIGIBLE, TP1_REACHED, TP2_REACHED, best/worst excursion) from the closed bars since open — monotone latches that cannot regress — and v4.76 turned the bar walks into SQL aggregates. The shadow SL candidate is checked against the never-widen law before it is printed.
evidence: docs/CHANGELOG.md 4.68, 4.76; app/services/mgmt.py.

### Byte-identical setup stats on two different symbols
question: Why did SILVER and US30 both show "LH/LL-SELL: n=14 · exp -1.00R"?
answer: The setup-class key is structure×direction with no symbol — a deliberate pool — but rendered beside a symbol it read as that symbol's history. v4.78 labels "(ALL symbols pooled)" and prints "this symbol alone" or CANNOT SEPARATE; the same release aged AI rounds past the 12h lifecycle to EXPIRED.
evidence: docs/CHANGELOG.md 4.78.

### The verification code that went nowhere
question: Why did a real signup sit unverified for days, and how is email configured now?
answer: In production with no mail provider, `send_email()` dropped the mail with only a log line while the signup page said "code sent". v4.92 made `issue_otp()` return delivery truth, added admin remedies (re-send with honest result, manual mark-verified) and a loud banner; v4.93 moved email settings into `/admin/email` with the key stored encrypted and never rendered back, after the first attempt ended with an API key pasted into chat; v4.94 fixed the password-type field that autofilled dots and posted an empty key, added a non-secret fingerprint, and verified the key with Brevo on save.
evidence: docs/CHANGELOG.md 4.92, 4.93, 4.94; tests/test_mail_delivery.py.

### The Pine A+ grade agreed with the wrong side
question: Why did the council keep rejecting A/A+ SELLs "against the prevailing trend"?
answer: The A+ rule used the direction-agnostic `htfFullAgree` (daily and H4 both bull OR both bear), so a SELL earned A+ because the HTF stack agreed with the BUY side. v18.9 makes A+ demand daily+H4 agreement with the signal's own direction; payload `htf_full` still reports the raw value (contract unchanged).
evidence: pine/V18.9_RELEASE_NOTES.md "GRADE FIX (07-30, confirmed by two council rejections)".

### Pine read the developing HTF bar live
question: Why did Pine's live decisions differ from its own chart history?
answer: HTF trend, DXY, yields and oil were read from the developing higher-timeframe bar in realtime, then history recalculated to the closed bar, poisoning h1/h4/daily bias, grades, pullback arming and macro. v18.10 P0-1 reads the last closed bar (`[1]` + lookahead_on) and merged 11 securities into 5 tuple calls; the accepted trade-off is a lag of up to one HTF bar. Also rebuilt: CHoCH, which was mathematically dead (`close[1]` can never exceed `highestLen[1]`).
evidence: pine/V18.10_RELEASE_NOTES.md P0-1, P1-9.

### Pullback pending order drifted with ATR (freeze-on-arm)
question: Why did a "pending" pullback entry move every bar?
answer: The arm block re-ran every bar while the setup held, resetting the expiry and recomputing entry/SL/TP with ATR and session. v18.11 E1 arms once (`na(entry)` guard), freezes everything, and only the death paths (tap→fire, expiry, trend flip, gap-through) clear it; expiry is finally a real 90 bars. Same release: per-direction signal ids (`SS-BUY-…` / `SS-SELL-…`) so bot dedup cannot drop the SELL of a double-fire bar.
evidence: pine/V18.11_RELEASE_NOTES.md E1, E5.

### A pullback RR gate would delete a validated engine (refusal with arithmetic)
question: Why was the reviewer's pullback RR ≥ 1.6 gate refused?
answer: PULLBACK's designed TP1 RR is 0.67 (Asia, TP 1.0×ATR / SL 1.5×ATR) and 1.20 (London/NY); a 1.6 gate blocks 100% of fires, deleting an engine validated at PF 1.30–1.44 out-of-sample with exactly those ratios. The council receives the true `rr` per signal and may impose any floor at its own layer.
evidence: pine/V18.11_RELEASE_NOTES.md "REFUSED (with the arithmetic)"; pine/V18.10_RELEASE_NOTES.md triage.

### Three lower-tf DXY calls killed Pine on heavy symbols (v18.13)
question: Why did SILVER and US100 alerts go silent for days while the chart looked fine?
answer: v18.12's three `request.security_lower_tf` calls for the DXY squelch blew TradingView's per-study memory limit on the heaviest 24h symbols; a stopped study draws nothing and never reaches `alert()`. v18.13 (bot/Pine side, 2026-08-31) collapses them to one guarded request, fixes bare "DXY" → "TVC:DXY", stamps `pine_ver:"18.13"` and appends `structure`. Platform side v4.91 keys the sensor banner on `pine_ver` (a case-sensitive grep had missed the real key). The alert ceremony is still required after any Pine save.
evidence: docs/OPEN_ITEMS.md PINE-CALC-1; docs/CHANGELOG.md 4.90, 4.91; tests/test_sensor_version.py.

### The Active-Signal panel showed a finished winner as LIVE for hours
question: Why did Pine's panel show SELL for a day after TP hit?
answer: The panel cleared only on SL-hit, trend flip, or a hardcoded 30-bar timeout — a TP hit never cleared it. v18.12.1 retires the signal on TP2 touch, makes expiry an input (default 16 bars), and shows the retire reason. Display-only; payload untouched.
evidence: pine/V18.12_RELEASE_NOTES.md v18.12.1 addendum (2026-08-01).

### A buy limit displayed above market (Pine)
question: Why could a human have placed an invalid pending order from the Pine panel?
answer: Entries sit ±pipZone off the range anchors; inside that buffer band the displayed limit is on the wrong side of market and the RANGE-BROKEN flag stayed silent. v18.12.3 adds "⚠ LIMIT ABOVE/BELOW MKT" states. The bot was unaffected (PULLBACK already has the close-side gate from v18.10 P0-4).
evidence: pine/V18.12_RELEASE_NOTES.md v18.12.3 (user catch); pine/V18.10_RELEASE_NOTES.md P0-4.

### Reporter environment silently overridden by the NSSM registry
question: Why did adding DXY/US10Y to the reporter's symbol list do nothing?
answer: `BB_PUSH_CANDLES` defaulted off, and machine-level env vars were overridden by the service's registry-level `AppEnvironmentExtra` — accepted config, no error, nothing happening. Fix was config: set `BB_CANDLE_SYMBOLS` (appended, never replaced) at the registry level and restart. The same probe found the v7 bridge mapping DXY→USDX, a symbol the terminal does not list.
evidence: docs/OPEN_ITEMS.md PLAT-MACRO-1 (closed 2026-08-19); agents/mt5_reporter/README.md.

### A weekend aged a closed market
question: Why did SILVER 1d read "STALE — 84h old" on Monday morning?
answer: 48 of those hours were the closed weekend. v4.60 measures bar age on the MARKET clock in `trend_context` (Sat/Sun excluded for non-24/7 symbols; crypto ages on the wall clock); v4.82 froze `market_reference_time` exactly while `market_status` says closed, fixing the false-stale that began two hours before Saturday.
evidence: docs/CHANGELOG.md 4.60, 4.82; app/services/market_time.py.

### Outlook confidence adjectives refused by name
question: Why does the outlook ingest reject `confidence`?
answer: A confidence label with no arithmetic is a probability wearing an adjective. v4.39's `outlooks` table has no confidence column and `/webhooks/brain/outlook` refuses `confidence`/`probability`/`chance` by name, top level and inside scenarios; counted context (N/4 timeframes known, M agree) renders instead; every outlook carries an envelope and EXPIRED renders loudly; an expired outlook with no successor is a GAP, never the house view (v4.53).
evidence: docs/CHANGELOG.md 4.39, 4.53; tests/test_outlook.py (11), tests/test_outlook_scorecard.py (8).

### The service map argued with the machine it described
question: Why did the service map say NSSM was removed while the reporter ran as an NSSM service?
answer: The map carried the 2026-08-08 note ("never reinstall; the Scheduled Task is the way") while the reporter now runs as NSSM service `BrotherBotReporter` on 52834417, the intended launcher. v5.13 corrected it from the box, kept the old lesson dated, recorded 52901228 as NOT EXPECTED by human fact (`REPORTER_COVERAGE`), and updated the test that had been guarding the stale string.
evidence: docs/CHANGELOG.md 5.13; docs/SERVICE_AUDIT_2026-08-08.md Priority 6 (superseded).
