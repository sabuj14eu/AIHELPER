---
title: Brother v18 Brain — Validated Evidence and Verdicts
domain: brain
repo: sabuj14eu/brother-brain-v2
sources: CLAUDE.md, docs/decisions.md, docs/AUDIT_2026-07-31.md, docs/PINE_VS_BOT_MAP.md, docs/OPEN_ITEMS.md, docs/SESSION_PENDING_SPEC.md, brain/src/agents/scout.py, brain/src/agents/quant.py, brain/src/agents/devils_advocate.py, brain/pullback_backtest.py, brain/fib_pullback_backtest.py, brain/truth_layer.py, brain/council_calibration.py, brain/weekly_source_report.py, brain/patch_report_sessioncall.py, brain/src/main.py, brain/src/compute_sltp.py, executor_ic_markets/src/ic_markets/mt5_bridge.py, brain/brain.out, brain/tests/audit/2026-09-05_iso19/test_iso19_execution_payload.py, dashboard/backend/patch_dashboard_botguards.py, dashboard/backend/patch_botguard_margin.py
verified_on: 2026-09-16
classification: INTERNAL
---

# How evidence is graded in the v18 brain

CLAUDE.md's Evidence Law sets the bar: "New rules must pass the backtest harness (train/validate split; the VALIDATE column decides) or accumulate journal evidence (n>=20 minimum; n<20 is luck). Judge nothing before ~100 trades." Every analytics script in `brain/` prints the same honesty rule: `truth_layer.py` flags buckets with `[PROVISIONAL n<20]`; `weekly_source_report.py` ends with "any cell with n<20 behind it is luck until proven"; `pullback_backtest.py` says "the validate column is the only one allowed to convince you"; `council_calibration.py` says "n<20 resolved is PROVISIONAL -- luck, not verdict." The live journal (`logs/decisions.jsonl`) is gitignored, so — as the 2026-07-31 audit states up front — "every data-dependent claim like 'WR 73.6%' is taken from comments, not re-verified" inside this repository.

# CURRENT EVIDENCE block (CLAUDE.md, "change only with new data")

- **PULLBACK trigger validated:** "n=640 backtest, out-of-sample PF 1.30-1.45, stop 1.5xATR (0.8 FAILED validation). Asia is its BEST session (73.6% WR)."
- **Fixed 2R take-profits FAILED validation on structural levels.** "The high-win-rate small-R ladder (session TP 1.0/1.8 ATR) is the validated design."
- **SMART_SCALP grades/scores are ANTI-predictive:** "score<=6 beat 9+; grade B beat A+. Do not hand-reweight; the engine itself is on trial by journal."
- **Counter-trend entries are the #1 documented loss driver** ("SELL bleed -406").
- **GOLD is the weakest asset** ("macro-driven; technicals bleed there"); **SILVER and US100 are the strongest.**
- **FIB-retracement levels: promising challenger** ("validate PF 1.82, n=62") — watch-list only; "builds only at PF~1.5+ with n>=100 validate."

# The PULLBACK backtest in detail (brain/pullback_backtest.py, Roadmap #14b)

The v18 brain's `pullback_backtest.py` replays the session-caller rule over ~50 days of M15/H1 history from the v7 bridge for 7 assets (GOLD, SILVER, BTC, ETH, US100, US30, EURUSD) at three decision hours (01, 09, 15 UTC): H1 trend = EMA20 vs EMA50 with-trend only; entry = 24-bar M15 swing ± FRONT×ATR(14) as a limit; SL = swing ∓ SLM×ATR; TP = 1.0 ATR (Asia, hour < 6) or 1.8 ATR (London/NY); skip when room < 0.4 ATR. Honesty rules baked in: no lookahead, limit must be touched within 12h, same-bar TP+SL counted as SL, 48h resolution, results in R-multiples, 70/30 time split, spread not modeled. The sweep covers FRONT ∈ {0.10, 0.15, 0.25} × SLM ∈ {0.8, 1.0, 1.5}; the live parameters are (0.15, 1.5).

The council prompts carry the measured numbers as the reference class (`scout.py`, `quant.py`, `devils_advocate.py`, dated 07-14/07-18): "633 trades, 75 days, out-of-sample validated: WR 62-74%, PF 1.45-1.69; Asia is its STRONGEST session (73.6% WR)"; "Win rate to TP1: ASIA 73.6% | NY 54.8% | LONDON 52.5% (overall PF 1.45)"; "Breakeven WR for this class: rr 0.61 needs 62.3%; rr 1.09 needs 47.8%"; "Its rr to TP1 is 0.61-1.09 BY DESIGN ... and a TP2 runner exists beyond the reported rr." docs/PINE_VS_BOT_MAP.md calls it "the validated n=640 design" with "validated PF 1.45" and notes session_caller v2 "reimplements exactly this geometry in Python."

Repo inconsistency to be aware of: CLAUDE.md says n=640 and PF 1.30-1.45; the agent prompts say 633 trades and PF 1.45-1.69; PINE_VS_BOT_MAP says n=640, PF 1.45; the audit (P2-6) cites "Validate-column PF 1.30-1.45". These are likely different runs/columns of the same harness, but the repo does not reconcile them — treat the exact PF as UNKNOWN within 1.30–1.69 and n as ~633–640.

The audit's caveat on this harness (P2-6): it "correctly avoids lookahead, requires touch-fills, excludes NO_FILL/OPEN, checks SL before TP on the same bar (pessimistic)", with one optimistic bias — a same-bar TP touch on the fill bar counts as a win at full R, which "at TP 1.0×ATR on M15 inflates WR by a few points."

# The FIB vs STRUCT shootout (brain/fib_pullback_backtest.py, advisor proposal 07-20)

`fib_pullback_backtest.py` tested, "before a single Pine line", three level modes (STRUCT 24-bar swing, FIB 38.2% of the day-so-far impulse with impulse ≥ 1.5 ATR, CONF = FIB only within 0.5 ATR of the swing), two stops (1.2 vs 1.5 ATR) and two targets (LADDER 1.0/1.8 ATR vs fixed 2R) under the same honesty rules; the recorded outcome is the CLAUDE.md line "FIB-retracement levels: promising challenger (validate PF 1.82, n=62)" and the 2R dogma FAILED. The script's own footer: "the winner earns a Pine slot ONLY by beating the live baseline out-of-sample, not by sounding nicer." Whether a Pine slot was ever granted: not in this repo (Sniper-System owns Pine).

# The session caller (paper, 3x daily)

`weekly_source_report.py` compares SMART_SCALP, PULLBACK and SESSION_CALL (live, council-gated) plus the unjudged SESSION paper ledger (`/home/shyam/session_caller/session_calls.json`), and prints the GRADUATION RULE: the caller "earns a (council-gated, NEVER direct) bot connection only if resolved n >= 20 AND its record beats the live arms." `patch_report_sessioncall.py` (07-26) records that by then "the session caller is now council-gated and live" and asks whether "the council improve[d] the caller's 81.3% record, or damage[d] it" — the 81.3% is the paper record as of 07-26; the answer is not in the repo. docs/PINE_VS_BOT_MAP.md adds a tension: "the 08-06 session_caller study found 1.8 [ATR TP] failing for scheduled best-of-7 Ldn/NY calls" while PULLBACK's 1.0/1.8 validated at n=640 — "Not a contradiction — different selection process — but watch both."

# Council calibration (brain/council_calibration.py, Roadmap #14)

`council_calibration.py` grades, against real M15 candles from the v7 bridge, both the original Pine signal and the rejecting agent's teaching proposal (Scout, DevilsAdvocate, Quant; WAIT levels graded in the signal's direction) with NO_FILL / HIT / SL / OPEN, 48h window, same-bar both = SL, and prints a head-to-head. Teaching proposals began 07-04, fresh WAIT levels 07-09. The repo contains the tool but no recorded calibration verdict; the answer to "are the council's teaching levels better?" is UNKNOWN here.

# Truth layer (brain/truth_layer.py)

`truth_layer.py` joins decisions.jsonl with executor `/outcomes` by `ticket_id` (first decision per ticket, manage rows skipped) and buckets WR / pnl / avg win / avg loss by grade, dispatch_mode, symbol, side, zone, killzone, session, vol_regime, trend_day, adx (<20, 20-30, >30), rsi (<35, 35-65, >65), rr (<2, 2-3, >3), score (<=6, 7-8, 9+) and htf_align. Its "rows with signal_raw (full conditions) ... grows from today forward" note dates the verbatim-raw journaling. The CLAUDE.md finding that "score<=6 beat 9+; grade B beat A+" is the kind of output this tool produces; the underlying n is not recorded in the repo.

# Incident-derived evidence (dated, with numbers)

- **The -60R scanner bypass** (CLAUDE.md Iron Rule 1; `pine_trust.py` 07-02): the last council bypass, an MT5 scanner riding pine_trust, lost 60R.
- **Demo bot at brain go-live, 2026-05-20** (decisions.md): "50 trades, 64% win rate, avg_win $14.58, avg_loss -$26.50, expectancy -$0.21/trade. Net-negative EV from R:R imbalance, NOT from bad entries."
- **First journaled council signal, 2026-05-21:** `v18-tradingview_xauusd_buy_20260521_105014_61c4`, Scout veto on tight SL, 3559ms latency, $0.03 estimated cost.
- **Polymarket scanner first cycles, 2026-05-23:** 100 markets fetched, 18 filtered, 3 posted, all Scout-vetoed; cycle 36.8s, ~$0.09.
- **brain/brain.out (committed log, 2026-05-31 to 2026-06-01):** contains 122 "rejected by" lines — Scout 99, Quant 11, DevilsAdvocate 11, RiskManager 1 — consistent with the runbook's expectation that "most rejections from Scout / DevilsAdvocate is healthy."
- **761 provider errors journaled as Scout rejections** before the 07-02 AgentError reclassification (`brain/src/main.py` comment).
- **Ticket 1697829693:** council asked for 0.41 USD of risk; min-lot rounding lost 25.18 USD — the cost basis of the min-lot guard (`mt5_bridge.py`).
- **LIVE-20260713-GHOST:** five days (CLAUDE.md says six) of approvals with dispatch=200 and no tickets; the bot-guards were built from it.
- **LIVE-20260724-STUCKTERMINAL:** the MT5 terminal sat on a LiveUpdate dialog for days; 34 MarginGate "account margin unreachable" rejections; sizing_failed on every order.
- **IPC blip (07-03):** two A-grade signals killed by a single -10001 "IPC send failed" packet at the 15m bar close; one 2.5s retry now outlives the blip.
- **BSv11 webhook failures (07-10):** TradingView showed >70% delivery failures because the Telegram post was synchronous; made non-blocking (<50ms).
- **Fail-soft spent 2/2 on 2026-09-02** (OPEN_ITEMS): two A/A+ signals traded on Pine trust because the council API failed; the mirror now says so.
- **Bridge symbol probe 2026-08-31 (measured on the box):** SILVER, GBPUSD, US30, USTEC, GOLD, BTC served (5 bars, newest 23 min old); US100 returns 400 forever because the broker's name is USTEC; US10Y/TNX/UST10Y/US10YT/ZN1! all 400/404 — the bridge cannot serve a 10-year yield.
- **INC-0001 (US10Y 15m candles, resolved 2026-09-02):** 12,949 rows from 2025-01-08 to 2026-08-27 20:58Z, then a hard stop; both MT5 terminals list no US 10Y contract after the September roll (only ITB10Y_U6, JGB10Y_U6, DXY_U6); verdict "US10Y PRICE CANDLES UNAVAILABLE AT THIS BROKER ... Not a bug."
- **Alert census 2026-08-31:** 5 of 8 active alerts on v18.13; BTCUSD/US30/XAUUSD still on v18.12; US100 had no genuine Pine alert for 32 days (last real 18.8); EURUSD 19 days.
- **Five reporter processes measured 2026-09-02** writing one platform row; after cleanup the final listing showed one reporter (PID 5336) — INC-0003 closed.
- **GOLD ticket 1900277473 (2026-09-03):** two platform trade rows created 70 ms apart by concurrent reporters; the close updated only one; the orphan explained every STOP_THROUGH/ORPHAN row.
- **SILVER/US100 "bias STALE" root cause (2026-09-03 21:00Z):** pushed=15 contained twin rows (XAGUSD fresh + SILVER stale; USTEC + US100); after the canonical dedupe, pushed=14 with no twins, NVDA present, `resp updated=14 refused=[]` — PROVEN at 21:08:41Z.
- **ISO-19 replay (brain/tests/audit/2026-09-05_iso19):** on the 12 real journal rows shipped in compute_sltp's self-test, the number of stops widened by the new code path equals the calculator's own count, pinned as `0 < changed <= 12` (BEHAVIOR CHANGED reported, not judged).

# What is explicitly NOT proven (per the repo)

- **The session caller has no scored edge on record** in this repo; SESSION_PENDING_SPEC says "No edge on paper -> do not build" and the pending-order design stays QUEUED.
- **MiroFish sentiment simulation** was never installed or shown to change outcomes (decisions.md 2026-05-13).
- **Global exposure / correlation caps exist only as prompt text** (audit P2-1, still open): nothing in code counts open positions across symbols or checks correlation; GOLD+SILVER+US100 same-direction is possible.
- **`macro_calendar` is always empty** in the council context (audit P2-2): Pine does not send it, so Scout's "macro event within 30 min" and RiskManager's "reduce 50% near news" rules judge nothing; "news detected ≠ trade blocked."
- **Sessions/DST are delegated to Pine** (audit P2-3); the brain computes none of it.
- **Order acceptance on US30/USTEC** is a separate, human-approved probe still open: "a served candle proves data, never fill" (OPEN_ITEMS 2026-08-31).
- **NVDA phase 1 proofs owed** (OPEN_ITEMS 2026-09-02): first `blocked_shadow` journal row, reporter "PUSH NVDA.NAS-24 ... bars pushed > 0", platform NVDA candles under the canonical name; the NVDA overnight spread is "still unmeasured."
- **The council calibration head-to-head and the truth-layer bucket results** have no recorded verdict in the repo (logs are gitignored).
- **Whether the fail-soft policy should stay at 2/day** is an open human decision; the evidence to decide with is "outcomes of every journal row with trace.agent_error_fallback."
- **Prompt caching pays off** is explicitly "a HYPOTHESIS, not a fact" (`base.py` 08-18); `ai_spend_report.py` settles it from the ledger, and no verdict is recorded.
- **The v18 executor code deployed on the Windows box after 2026-09-15** is UNKNOWN from the repo: the P1 batch release-gate artefact exists (`patch_v18_executor_iso11_13_15_20.py`), but deployment proof lives in the box's `/health` (`guards_flag_present: false`), not here.
