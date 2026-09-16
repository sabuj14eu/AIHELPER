---
title: Brother Sniper v7 — glossary
domain: v7
repo: sabuj14eu/brother_sniper_v7
sources: CLAUDE.md, docs/START_HERE.md, docs/OPEN_ITEMS.md, docs/SESSION_COORDINATION.md, docs/V7_AUTONOMY_PLAN.md, docs/ADAPTIVE_GATES_SPEC.md, docs/AUTONOMY_READINESS_2026-08-30.md, docs/STRATEGY_INTELLIGENCE.md, docs/PINE_UPDATE_NOTE.md, bot.py, sniper_executor.py, core/v7_status.py, core/sl_engine.py, filters/news_gate.py, filters/freshness_gate.py, filters/ai_filter.py, risk/equity_guard.py, learning/cluster_engine.py, learning/conditional_profile.py, learning/strategy_dna.py, learning/telemetry.py, nightly_edge.py, auto_live.py, utils/asset_gate.py
verified_on: 2026-09-16
classification: INTERNAL
---

# Glossary of v7 terms

**A1 / A2 / A6 / B5 / C1 / C2 / C3 / C4** — Item codes from the 2026-09-01
audit work order carried in docs/OPEN_ITEMS.md: A1 executor truth (503 +
unverified-close guard), A2 webhook secret auto-injection retirement, A6
honest DD message, B5 two-witness /candles clock (brain), C1 dedupe key,
C2 htf_align, C3 mirror fields, C4 PULLBACK routing decision.

**Adaptive gate** — An evidence-driven, conditional gate with four states
(ALLOW / CAUTION / WAIT / BLOCK) that may only tighten or size down; opposed
to hard safety gates, which learning can never override (docs/ADAPTIVE_GATES_SPEC.md).

**ADR-004 / ADR-008** — brother-developer architecture decisions: uniqueness
is `(account_id, signal_id)`; one shared global emergency-stop file per box.

**Alert ceremony** — Deleting and recreating ALL TradingView alerts ("Any
alert() function call") after every Pine save, because an alert freezes the
script version at creation (Iron Rule 3).

**Anchor-safe patch** — A `patch_*.py` script that edits a live file only
where a unique anchor string matches exactly once, with backup, py_compile,
restore on failure and idempotency; aborts untouched on any ambiguity.

**Arm** — One of the two execution paths that judge the same Pine signal:
the v18 brain (council) and the v7 bot (mechanical). "The mechanical arm" = v7.

**Asset class slot** — v7's concurrency unit: one open trade per class among
metals / crypto / forex / other (`ASSET_SLOTS`, Task 8).

**Asset gate** — `utils/asset_gate.py`: per-symbol bench (`ASSET_GATE_DISABLE`)
or size multiplier (`ASSET_GATE_SIZE`, clamped <= 1.0), off by default.

**ATR floor (trust mode)** — The minimum SL distance applied to a trusted
Pine stop: 1.2 x live M15 ATR (F9), with a reject if the floor exceeds 1.6 x
Pine's stop (widen-ratio guard).

**AUTO_LIVE_ARM** — The env flag that turns `auto_live.py` from dry-run
(logs only) into posting real candidates to v7's webhook; a human act.

**auto-live-v1 / auto_live.py** — v7's Pine-independent engine: the
platform's auto-v1 structure math ported verbatim, firing on a closed 15m
bar touching a structural level with structure intact, through v7's full
gate chain. Shadow-deployed 2026-08-30.

**Bridge** — `sniper_executor.py`, the Flask service on the Windows VPS
(:5001, NSSM `SniperExecutorV7`) that places, closes, modifies and reports
MT5 positions for v7; the last thing before the broker.

**broker_comment** — `"BS_" + md5(signal_id)[:8]`, the MT5 order comment the
bridge stamps and the reporter sees; carried on heartbeat slots and decision
records so a broker row joins its decision.

**BS_<sid>** — The bot's own comment/`signal_id` sent to the bridge for an
order; tracked as `comment` in the slot; also the marker SLOT-RECON uses to
recognise v7's orphan positions.

**BSv16 / BSv17 / BSv18 / BSv11** — Pine `system` values the bot trusts
(secret auto-injection and trust mode). BSv18 = the current ULTIMATE v18.x.

**Cluster** — A bucket `symbol_session_regime_vol` with measured expectancy;
usable at 8 trades, trusted at confidence 0.60; drives the EV gate and the
learning-phase sizing scale (0.25x / 0.5x / 1.0x).

**Council** — The v18 brain's 6-agent AI council that judges signals for the
v18 arm; v7 never consults it, and nothing bypasses it on the v18 path.

**CANNOT SEPARATE** — The honest verdict when the deciding cell is under the
evidence floor after confounder cuts; a first-class outcome like NO ROBUST STRATEGY.

**Decision card** — A change that only Shyam may decide (risk numbers,
enabling a signal class), written up with options and evidence, never
applied silently.

**decision_id** — `sha256(account:signal_id:status:msg:ts)[:16]` on every
v7_decision record; stable for one evaluation, different for a second one.

**Dedupe key (bot)** — `symbol:signal_id` when Pine sends an id, else
`sha256(symbol-direction-entry)[:16]`; persisted as `<V7_MT5_LOGIN>:<key>`
for `SIGNAL_DEDUP_MIN = 10` minutes.

**Deploy ceremony** — backup -> compile -> restart -> verify in logs/journal
(Iron Rule 4). Contabo today: `git pull --ff-only origin main` + restart +
witness; Windows: patch script + NSSM restart + `/health`.

**Deploy branch / mirror branch / trade-desk branch** — The three diverged
session branches (evidence-integrity-audit-35rlfa, brain-platform-mirror-fcacwl,
trade-desk-architecture-review-hp9xnb) before convergence on `main`.

**Developer agent** — `brother-developer`, the read-everywhere,
write-in-sandbox engineering intelligence that audits both arms and produces
ISO findings, ADRs, memory records and release-gate artefacts.

**DECISION BLOCKED — DATA FRESHNESS** — The freshness-gate state meaning the
old evaluation is no longer authoritative: NO ACTION; only a completely new
evaluation may act.

**EV gate** — Discipline governor check refusing a cluster whose expectancy
is below `MIN_EV_FLOOR = -0.5`.

**EV_lcb** — Lower-confidence-bound expectancy (mean R minus one standard
error) used by nightly_edge and the asset-bleed re-derivation.

**Evidence Law** — Iron Rule 5: no live logic change without data; n >= 20
minimum (n < 20 is luck), ~100 to judge, validate column decides, one organ
per week.

**Executor** — Generic name for either Windows MT5 service; for v7 it is the
bridge (`SniperExecutorV7`), for v18 `SniperExecutorV18` (:8080).

**F2 … F9** — The 2026-07-02/07-10 fix series in bot.py/filters: F2 MIN_RR
1.0 + widen guard, F3 symbol digits, F4 index specs, F5 `_grade` for all
systems, F6 no AI override of news blocks, F7 no auto-SL, F8 counter-trend
penalty, F9 DST sessions (07-02) and the ATR floor (07-10).

**Freshness Law** — Stale data must never become a valid positive signal;
missing news is UNKNOWN, not low risk; every number carries source,
timestamp, freshness, authority, meaning, expiry.

**Freshness gate** — `filters/freshness_gate.py`: signal age > 900 s (v1) or
material move > 1.5 ATR (v2) -> DECISION BLOCKED; modes off / shadow
(default) / enforce.

**GATE-xxx** — The gate tags v7 logs and `core/v7_status.classify_gate`
assigns to verdicts (GATE-NEWS, GATE-EV, GATE-SLOT, GATE-DEDUP, GATE-RR,
GATE-SL-FLOOR, GATE-AI-FILTER, ...), so the desk and the log agree.

**Global stop (ISO-16)** — One file (`C:\brotherbot\GLOBAL_STOP`) both
executors read before every new order; present = STOP, unreadable = STOP.

**Golden test** — A test proving a fix or patch script holds (byte-identical
output, refusal behaviour); contrasted with `test_repro_*` (gap still present)
and `test_holds_*` (invariant).

**Harness** — The backtest harness with a train/validate split whose
VALIDATE column decides whether a rule may go live (brain side).

**Heartbeat** — The `v7_heartbeat` record built every monitor cycle (~60 s)
and pushed to the platform at most every 240 s, so "v7 quiet" is
distinguishable from "v7 down".

**ISO-xx** — Findings of the dual-MT5 isolation audit (Job 3, 2026-09-04):
ISO-01 bridge identity, ISO-02 fabricated balance, ISO-03 account_id +
magic, ISO-05 cross-arm close/modify, ISO-06 bridge idempotency, ISO-07
equity state account, ISO-08 dedupe key account, ISO-16 global stop, ISO-19
shadow soak, ISO-24 LLM override of a rule block.

**Journal** — The measured record: for v7, `learning/trades.jsonl`
(open/close), `learning/telemetry.jsonl`, `learning/decisions.jsonl`,
`logs/bot.log`; for the brain, `logs/decisions.jsonl`. "History is measured,
not remembered."

**Magic number** — MT5 order tag `V7_MAGIC_NUMBER` (default 70007) stamped on
every v7 order since ISO-03; a tag, not a risk number.

**MAE / MFE** — Maximum adverse / favourable excursion, accumulated by the
monitor from `price_current` every ~60 s (so both are understated).

**Mirror (nginx)** — The nginx `mirror` directive copying every
`/webhook/v18` request to v7's `/webhook`; the mirrored body carries no secret.

**Mirror (platform)** — `learning/platform_mirror.py`: read-only,
fire-and-forget posts of v7 decisions/closes to the platform under `v7-<id>`.

**NEWS01** — The three-state (CLEAR / BLOCK / UNKNOWN), two-witness (own
ForexFactory reading + platform `/api/v1/news/state`) news gate of
2026-09-15; UNKNOWN blocks; modes enforce / shadow / observe.

**NO ROBUST STRATEGY / NO ROBUST EDGE** — A successful, first-class outcome
of the lab and of any evidence review.

**Observe mode** — `V7_NEWS_GATE=observe` (Shyam, 2026-09-16): the news
verdict is computed and recorded as `news_observe` telemetry but blocks
nothing, so the gate can be judged by its own numbers.

**One organ per week** — Only one live rule/gate/engine changes per week;
arming auto_live is itself the organ of its week.

**Organ** — One self-contained live behaviour (a gate, an engine, a sizing
rule); new organs ship dark/shadow and are versioned rather than edited in place.

**Outlook** — A weekly/monthly thesis with above/below level scenarios posted
to the platform board via `post_outlook.py`; never carries confidence words;
a changed mind is a new post.

**Panel Law** — A blank Pine panel means the chart display died, not the
trade; position truth lives in the journal and broker tickets.

**Paper lanes** — The platform's lane_observations population (limits placed
and resolved under lane-resolve-v1, no spread/slippage costs); a hypothesis
generator, never a gate authority for v7.

**PF** — Profit factor (gross wins / gross losses). CLAUDE.md evidence quotes
PF 1.30–1.45 (PULLBACK), 1.82 (FIB challenger), 0.54 (SELL side).

**Pine / Pine v6 / v18.12 / v18.13** — The TradingView BrotherSniperULTIMATE
indicator that emits alerts; frozen sensor; v18.13 added `structure`.

**pine_ver** — The payload key (since v18.8) that stamps the Pine version;
stored in the telemetry column `pine_version`.

**PROVISIONAL** — Label on any bucket with n < 20 in the scorecards and
nightly edge ("likely luck").

**R (R-multiple)** — Profit expressed in units of planned risk:
`net_profit / (balance_at_open * risk_pct)` (canonical, cluster_analyzer).

**Readiness (Autonomy Readiness)** — The weekend report answering whether v7
can decide without Pine; rendered by the platform from
`docs/AUTONOMY_READINESS_*.md` via `post_readiness.py`; UNKNOWN never PASS.

**RECONCILE / SLOT-RECON** — Recovery paths that adopt a live broker
position v7 is not tracking (after a placement exception, or during the
monitor sweep) rather than believing a timeout.

**Regime** — TREND / RANGE / VOLATILE / UNKNOWN from `learning/regime_detector`;
sets `atr_multiplier`, `risk_scale` and (unused, pilot mode) score threshold.

**Session ladder** — The validated small-R take-profit design (session TP
1.0 / 1.8 ATR) versus the failed fixed 2R TP (CLAUDE.md).

**Shadow** — A mode or module that evaluates and logs but never changes a
trade: freshness gate shadow, eye votes, analyst eye, auto_live dry run,
strategy DNA, adaptive verdicts.

**Shrinkage** — Empirical-Bayes pull of a bucket's win rate toward the global
mean with `PRIOR_K = 6` virtual trades (nightly_edge): a 3/3 "100%" reports ~65%.

**signal_id (Pine)** — Pine's own alert id (e.g. `SS-BUY-20260819104500`);
the agreed join key between arms; carries no symbol.

**Strategy DNA** — `learning/strategy_dna.classify`: S1 trend_continuation,
S2 pullback_sniper, S3 breakout, S4 mean_reversion, S5 news_reaction, S0 unclassified.

**Telemetry** — `learning/telemetry.jsonl`, the log-only per-trade and
per-reject feature row (market, structure, ai, timing, execution groups) that
joins to the journal by signal_id (`load_unified`).

**Ticket** — The MT5 position id (`order_id` in v7 state); "only tickets tell
the truth" (Iron Rule 6).

**Trust mode** — Accepting Pine's structural SL (BSv17/BSv18/BSv11, or v9 with
score >= 7) instead of rebuilding it, subject to sanity band, ATR floor and
widen-ratio guard.

**Truth guards** — The 2026-08-31 bot.py guards: positions-shape (UNKNOWN is
not FLAT), unverified-close (UNKNOWN is not a loss), XFF from loopback only.

**Two witnesses** — Any inferred fact (clock offset, news state) needs two
independent fresh sources; one alone is a note. Applied to `/candles` (brain)
and NEWS01 (v7).

**UNKNOWN** — The explicit state for a missing measurement; never rendered
as 0, clear, flat, loss, default balance or default account.

**Validate column** — The out-of-sample half of the harness split; the only
column that may justify a live rule.

**v7_decision / v7_heartbeat** — The two record kinds `core/v7_status.py`
emits to the platform (schema `v7-status-1`).

**WR** — Win rate. CLAUDE.md quotes Asia 73.6% WR for PULLBACK; the demo
exit rule needs 55%+ WR over 100 trades (INTENT_v5).

**XFF** — `X-Forwarded-For`; honoured by v7 only when the connection comes
from loopback (our own nginx).
