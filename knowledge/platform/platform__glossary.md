---
title: Sniper-System platform glossary
domain: platform
repo: sabuj14eu/Sniper-System
sources: CLAUDE.md, README.md, docs/HANDOFF_PLATFORM_SESSION.md, docs/OPEN_ITEMS.md, docs/V7_SELF_DEPENDENCE_PLAN.md, docs/HANDOVER_V7_DESK.md, docs/CHANGELOG.md, docs/SERVICE_AUDIT_2026-08-08.md, pine/V18.9_RELEASE_NOTES.md, pine/V18.12_RELEASE_NOTES.md, app/routers/webhooks.py, app/services/freshness.py, app/services/engineering.py
verified_on: 2026-09-16
classification: INTERNAL
---

# Sniper-System platform — glossary

Terms as the Sniper-System repository uses them. Each entry is one or two sentences; where a term is defined by a specific file the file is named.

**Shyam** — the owner and operator of the whole Brother Sniper system and of this platform (GitHub `sabuj14eu`); he pastes commands into a terminal, relays messages between the platform session and the bot/brain session, and makes every risk, retirement and security decision himself (docs/HANDOFF_PLATFORM_SESSION.md).

**Brother Bot Platform / Sniper-System** — this repository: the multi-tenant SaaS platform (public site, dashboard, admin, Trade Desk, evidence tables, Model Lab, Pine workspace) that observes and manages but never trades.

**Bot box / Contabo box** — the Linux server (Contabo VPS) that runs the v18 brain (`/home/shyam/brain-v2`), the v7 bot (`/home/shyam/brother_sniper_v7`) and, at `/srv/brotherbot`, this platform; the machine name used in commands is `vmi3221804`. "Bot box" in the docs usually means the brain/v7 side owned by the other session.

**Windows VPS** — the Windows machine running the two MT5 terminals, the two executors (ports 8080 and 5001) and the MT5 reporter as NSSM service `BrotherBotReporter`.

**v18 brain / council** — the Contabo-side AI system where a 6-agent council judges every Pine signal and, on approval, sends an Ed25519-signed dispatch to the v18 executor (MT5 52901228). "Nothing bypasses the council" is its Iron Rule 1; the platform only mirrors its decisions.

**v7 / v7 bot** — the mechanical trading arm (`brother_sniper_v7`) with its own filters, gates and telemetry; it posts to the v7 executor/bridge on port 5001 (MT5 52834417) and mirrors decisions one-way to the platform (docs/INTEGRATION_V7.md).

**Executor** — a Windows-side service that actually places MT5 orders (SniperExecutorV18 on 8080, SniperExecutorV7 / `sniper_executor.py` on 5001). The platform never talks to one.

**Bridge / live bridge** — the v7 executor's HTTP `/candles` (and `/spread`, `/symbolspec`) endpoint on port 5001, proxied by `app/services/bridge.py` for the HTTPS chart; read-only and display-only, nothing fetched is stored.

**Reporter / MT5 reporter** — `agents/mt5_reporter/mt5_reporter.py`, the read-only Windows agent that posts account/VPS/trade heartbeats and closed candles to the platform API with an API key; version 1.7.0 at HEAD.

**Mirror / signal mirror** — the one-way read-only copy of brain and v7 decisions POSTed to `/webhooks/brain/*` and stored verbatim in `Signal.raw_payload` / `DecisionEvent`; the platform's only source of signals.

**Payload contract** — the append-only JSON field set Pine emits and every reader depends on (system, signal, direction, signal_id, symbol, tf, entry, sl, tp, tp1, tp2, rr, grade, plus appended fields such as pine_ver, struct, entry_dist_atr, trades_today). Fields are added, never renamed or removed.

**Pine / BrotherSniperULTIMATE** — the TradingView Pine v6 indicator (`pine/BrotherSniperULTIMATE_v18_FINAL_v6.pine`, v18.12.x in the repo, v18.13 reported live) that fires the alerts; it is the SENSOR and stays frozen because every save needs the alert ceremony.

**Alert ceremony** — after any Pine save: delete and recreate every TradingView alert ("Any alert() function call"), same ingress URL, verify `pine_ver` in the brain log, confirm the v7 mirror. Alerts freeze the script version at creation time.

**pine_ver** — the version stamp inside every Pine payload since v18.8 (e.g. "18.12", "18.13"); the only proof of which Pine is actually live, and the key the platform's sensor banner reads (v4.91).

**Asset Pulse / Asset Map** — `pine/BrotherSniper_AssetPulse_v1.pine`, a separate Pine script (own token budget, no alerts) that ranks assets per session; it plans, v18 confirms, the council decides.

**Token budget / token ceiling** — TradingView's ~80,000 compiled-token limit per Pine study; v18.8 sat at ~79,950, so every addition needs a removal (pine/PINE_v18.9_SPEC.md).

**DARK / FEATURE_* flag** — a strategy organ shipped in Pine or the platform visible and measured but not wired to money (default-off input), flipped only when the journal or harness validates it.

**Harness** — the backtest/validation apparatus (train/validate split; the VALIDATE column decides) that any new trading rule must pass before it touches Pine or a live gate; "evidence before Pine".

**tf** — timeframe. Canonical platform vocabulary: `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`; Pine's raw "15"/"60"/"240"/"1440" are folded by `normalize_tf()`.

**rr** — the risk:reward ratio Pine reports per signal (TP1 distance ÷ SL distance); `rr_in_grade` records whether the sender's grade consulted it (None = unstated → UNKNOWN).

**grade** — Pine's A+/A/B quality label for a signal; on trial by the journal because grades were found anti-predictive, and never hand-reweighted.

**Session** — a trading session block (ASIA / LONDON / NEWYORK) used to key briefs, lanes and statistics; Pine uses DST-aware session clocks since v18.12.

**Trade Desk / desk** — `/desk`, the deterministic page that answers "what are the nearest levels for this asset now" in four horizons from stored closed candles; paper research only, never a production plan (`app/services/desk.py`).

**Lane** — one deterministic candidate engine run on the desk: auto-v1 (15m/40), scalp-v1 (15m/12), session-v1 (1h/24), swing-v1 (4h/40). Each lane's candidates are recorded as lane observations. "Three-Lane" (`/three-lane`) is a different use: Pine/bot vs autonomous bot vs blind AI competing per round.

**Lane observation** — one immutable row in `lane_observations` per (symbol, engine, closed bar), WAITs included, carrying birth context and the resolved outcome; the Phase-1 dataset.

**Evidence tables / Evidence Lab** — the append-only memory tables (`lane_observations`, `decision_records`, `session_candidates`, `market_snapshots`, `event_reactions`, `desk_messages`, `outlooks`) and the `/evidence` page that renders their aggregations (moved off `/desk` in v5.11).

**entry_dist_atr** — how many ATRs the candidate's entry sits from the reference price at birth; recorded on every observation (platform) and, since v18.12, emitted by Pine and captured by v7 — the two populations behind the far-bucket question.

**Far bucket / >3 ATR** — the distance bucket whose negative expectancy is the standing observation; it can only become a rule when both populations agree with the with-trend cell over the floor.

**_resolve / lane-resolve-v1** — the frozen outcome rule (`ai_analyst._resolve`): trigger first, same-bar SL first, R units, NO-FILL ≠ loss, TIMEOUT mark-to-market, NO_DATA after 5 days; pinned identical for every lane.

**R** — outcome measured in multiples of the initial risk (entry to SL distance); expectancy is reported in R.

**Evidence Law / Evidence ladder** — n<20 is luck, ~100 to judge; EARLY EVIDENCE → NO EDGE DEMONSTRATED → REQUIRES CONFIRMATION → PROMISING → ROBUST EDGE (`stats.evidence_status`).

**CANNOT SEPARATE** — the first-class verdict when the deciding cell of a split sample is under the Evidence-Law floor (or two facts look identical in the data); refusing to conclude is a successful outcome.

**NO ROBUST STRATEGY / NO ROBUST MODEL** — the Strategy Factory's and Model Lab's first-class successful verdict when no out-of-sample edge survives.

**Holdout / FINAL HOLDOUT** — the newest 20% of a dataset, untouched during search and spent exactly once per experiment to confirm or kill a champion; never re-armed (Quant Lab Law; PLAT-HOLDOUT-1 is the known breach).

**Strategy Factory / Model Lab** — `/factory` (predefined variant families, walk-forward, Monte Carlo, champion/challenger) and `/modellab` (P(close higher after H bars) logistic models); research artifacts that cannot emit a signal.

**Witness** — an independent fresh source used to establish a fact; the reporter needs two fresh tick witnesses (one 24/7) to infer the broker clock, and the market map needs two fresh witnesses for a MARKET VIEW.

**Broker offset / broker tz** — the MT5 server's clock relative to UTC (EET/EEST, `BB_BROKER_TZ` Europe/Athens); converted per bar, never as a scalar.

**Off-grid row / shifted twin** — candle-audit evidence of a timestamp shift: a 4h/1d bar whose `ts` residue differs from its series' grid, or the same OHLC stored twice an hour apart.

**Season check / SEASON_AWARE** — the audit test that a multi-year series shows two daily grids one DST hour apart; a single tidy grid across seasons is SCALAR_SUSPECTED.

**Depth probe** — `python mt5_reporter.py depth`, which records how many bars MT5 will actually serve per series (`feed_depth_probes`); required before any wipe.

**Twin (trade twin)** — two `trades` rows for one broker ticket created by racing reporter processes; removed by `trade-twins-v1` with every field written to `audit_log` first (v5.23).

**Ghost / orphan** — a ghost is a stale "open" row the broker had already closed; an ORPHAN is a real broker position with no signal joined (a manual trade), first-class in the management panel, badged `ORPHAN · manual`.

**Freshness states** — LIVE (inside its window), STALE (exists, too old, INVALID for decisions), UNKNOWN (no data, proves nothing), INVALID (present but failed validation) (`app/services/freshness.py`); plus NEVER_POSTED, UNREACHABLE, NOT_EXPECTED, RETIRED as separate facts.

**RETIRED** — a symbol whose writer ended by human decision or instrument end, recorded in `RETIRED_SYMBOLS` with date and reason; never inferred from silence.

**Bias / MarketBias** — the v18 council's pushed per-symbol opinion (trend, strength, council counts, `as_of`); INVALID past 24 market-clock hours (`BIAS_MAX_AGE_H`).

**Zone / Regime** — derived from bias and structure on the radar; both read STALE when the bias is stale, never a direction.

**Structure (HH/HL, LH/LL, MIXED)** — swing-point classification from closed candles; UP = HH+HL, DOWN = LH+LL, else TRANSITION/MIXED; UNKNOWN means not enough confirmed swing points.

**Outlook / outlook board** — a weekly or monthly thesis with a scenario map posted by an author (bot box `post_outlook.py`, auto-weekly Sunday 21:30 UTC) to `/webhooks/brain/outlook`; rendered with envelope (written at, valid_until), ACTIVE/EXPIRED/ABSENT, scenarios measured against closed prices, graded by the scorecard after expiry; no confidence field exists.

**Scenario map** — the outlook's list of level + side + reading ("above 4500 → bullish acceptance"); the platform adds only whether each condition is TRUE against the last closed price.

**Daily Market Brief** — one per asset per session block, deterministic scenarios from stored levels with an optional fact-checked AI narration through the single metered door; context, never permission.

**Market map** — `market-map-v1` (v4.73): event playbook phases, cross-asset pressure, MARKET VIEW ≠ TRADE DECISION, why-not-now checklist, scenarios, next thing to watch — zero LLM.

**Playbook** — the event regime state machine for MACRO_RELEASE (PCE/CPI/NFP/FOMC) and MAJOR_EARNINGS (Nvidia → US100): PRE_EVENT → INITIAL_MOVE → WAIT_15M_STRUCTURE → WAIT_RETEST → NORMAL_EVALUATION.

**mgmt-v1 / management envelope** — the position-management engine on /chart (HOLD/PROTECT/MOVE_SL/TP1/TRAIL/EXIT_WARNING/EXIT/STOP_THROUGH), every judgement journaled `UNVALIDATED` in `desk_messages`; SUGGESTION ONLY, no path to MT5.

**V7_FACT vs DESK_DERIVED** — provenance labels: a level straight from the mirror/reporter (e.g. the broker stop) versus one the desk computed from its level ladder.

**Never-widen law** — BUY: new_SL ≥ old_SL; SELL: new_SL ≤ old_SL; a shadow candidate that would widen a stop is refused before it is printed.

**Runner** — the post-TP1 trend-continuation classifier (v4.86–v4.89: RUNNER ACTIVE/PROTECT/EXIT) with its counterfactual replay on /v7; frozen at the v4.88 baseline pending the RUNNER FINAL GATE.

**Shadow** — a decision or action recorded beside the live one and never sent (shadow SL, shadow gate, Phase-4 shadow lane).

**FALLBACK_ID** — the label on /funnel for an opportunity joined by symbol + direction + entry within 30 minutes because the payload carried no `pine_signal_id`; its share is the acceptance test for the brain adopting Pine's id.

**SC- id** — the bot box's minted pre-council candidate id (`SC-SELL-…`), the exact join key for `session_candidates`.

**Opportunity (SignalOpportunity)** — the analytical grouping that counts one Pine signal ONCE across the v18 and v7 arms (`services/opportunity.py`).

**Arm** — v18 or v7 as responders to the same Pine signal; an "arm disagreement" is v18 approved / v7 rejected or vice versa.

**Blind AI lane / AI round** — the research lane where an LLM receives only meta/freshness/market/news and answers with a call, metered by `ai_ledger`; never in the decision path.

**Sweeper** — the in-app 60-second background loop (one elected worker) that collects, resolves, journals, briefs, prunes and runs the watchers.

**Watchers / engineering desk** — the seven deterministic checks on `/admin/engineering` (candle_freshness, bias_coverage, heartbeats, fallback_id, signal_volume, git_production_match, payload_contract) that open/update/resolve INC-nnnn incidents.

**Incident (INC-nnnn)** — an append-only fault record opened by a watcher; ids allocated once, never renumbered; the bot side may post progress but never APPROVE/REJECT/RESOLVE.

**Brain View** — `/brain-view`, one page per symbol assembling existing read models with SOURCE → TIMESTAMP → FRESHNESS and adding no intelligence (guard test).

**Fail-soft** — the brain's bounded exception to "nothing bypasses the council": approve on Pine trust when the council API errors on an A/A+, at most 2 per UTC day, then fail closed; rendered by `services/fail_soft`.

**Canonical symbol** — the platform's own name for an instrument (GOLD, SILVER, US100, OIL, BTC, ETH, XRP, DXY, US10Y, NVDA …) produced by `canonical_symbol()` from broker/TradingView aliases; the naming contract is append-only.

**Lineage** — the stored history under one symbol name; two names for one instrument create two lineages that are never merged after the fact.

**tracked_symbols** — `SELECT DISTINCT symbol FROM candles`; what /desk, /chart, /brain-view and the collector iterate. `/radar` lists MarketBias symbols instead.

**CORE_UNIVERSE** — the hardcoded symbol list in `routers/scanner_page.py` that gets an automatic Daily Brief and blind AI round (AI spend grows per symbol).

**Sensor version / UNSTAMPED** — the Pine version population of stored signals read from `pine_ver`; rows without it are UNSTAMPED.

**Reference drift** — `desk.reference_drift` (ref-drift-v1): the snapshot's reference close has moved ≥ `BB_REFRESH_DRIFT_ATR` (default 1.0) ATR from the newest bar; a freshness banner, not a trading rule.

**bar-clock-v1** — the one module computing a bar's age from open and from close; the gate uses the open anchor.

**feed-diag-v1** — FEED_WIDE / SYMBOL_ONLY / MARKET_CLOSED / NEVER_POSTED diagnosis of why the newest closed bar is old.

**news-lens-v1** — `calendar_risk`, `symbol_news`, `event_window`: three named news measurements.

**position-state-v1** — NONE / BUY_OPEN / SELL_OPEN / HEDGED / MULTI / SIDE_UNKNOWN from broker rows only.

**Service Map / Data Health** — `/admin/services` (who runs where, monitored or NOT MONITORED) and `/admin/data` (per-feed candle freshness, research readiness, stream liveness).

**Readiness page** — `/readiness`, rendering the bot box's weekly AUTONOMY_READINESS doc artifact; ⛔ OVERDUE at 8 days.

**Brother Developer** — the separate engineering-intelligence agent repo that reads all three codebases, writes only in a sandbox worktree and never trades or deploys.

**Handoff** — `docs/HANDOFF_PLATFORM_SESSION.md`, the living document a new platform window reads after CLAUDE.md and before OPEN_ITEMS.

**One organ per week** — the change cadence for anything touching trading logic: one validated change at a time, judged on its own ~100 trades.

**Anchor-safe edit** — a code edit applied only where the surrounding text uniquely matches; abort on ambiguous anchors (deploy ceremony rule).

**Version chip** — the `VERSION` string printed on every page (v4.33) so "is it deployed?" is a glance.
