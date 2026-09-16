---
title: Brother Sniper v7 — open items and deferred work
domain: v7
repo: sabuj14eu/brother_sniper_v7
sources: docs/OPEN_ITEMS.md, ROADMAP.md, docs/START_HERE.md, docs/V7_AUTONOMY_PLAN.md, docs/ADAPTIVE_GATES_SPEC.md, docs/AUTONOMY_READINESS_2026-08-30.md, docs/UI_WORK_ORDER_2026-09-02.md, docs/STRATEGY_INTELLIGENCE.md, docs/V7_AUDIT_2026-08-01.md, docs/A2_NGINX_MIRROR_SECRET.md, CLAUDE.md, learning/platform_mirror.py
verified_on: 2026-09-16
classification: INTERNAL
---

# How the v7 open-items file works

`docs/OPEN_ITEMS.md` is the ledger of deferred work for the bot side, kept as
dated ROUND sections with item codes from the platform/audit work orders.
"An item deferred in conversation is an item forgotten — if it is not in that
file, it does not exist. Delete an entry only when it is done and verified,
and say where the proof is." Statuses below are as the repo carries them on
2026-09-16; anything the repo cannot verify (box crontabs, live logs, the
platform's board) is marked UNKNOWN.

# Work order 2026-09-01 (rounds 1-3) — item status

- META 0.1 — FALSE ALARM: commit 6063676 exists; the auditor diffed the
  default branch. The referenced `docs/AUDIT_2026-09-01_BOT_SIDE.md` exists
  on NO branch; its "STEP 7 P1" list must be re-issued before it can be
  worked. Status: OPEN (list never pushed).
- A1 — DONE: truth guards (shape + 10-cycle unverified close) and the bridge
  503 (deployed Windows 2026-09-02). Note: the order wanted "retry forever";
  shipped 10 cycles then a loud unverified close. Status: DONE, wording
  choice recorded.
- A2 — PARTIAL BY DESIGN: XFF trusted only from loopback (shipped); header
  secret accepted (shipped dark). Remaining: Shyam's nginx
  `proxy_set_header X-Webhook-Secret` line on the brain box, then verify
  `[A2] secret from header` in bot.log for >= 1 day, then remove the
  auto-injection (own anchor-safe patch) and ROTATE WEBHOOK_SECRET (the
  08-01 hygiene note still owes that rotation; deferred by explicit decision
  while everything is DEMO). Status: OPEN, blocked on the nginx step.
- C1 — DONE (round 2): symbol-prefixed dedupe key.
- C2 — DONE: htf_align read; historical htf_agree=False untrustworthy.
- C3 — DONE bot-side: mirror forwards pine_ver, payload_schema, fired_at,
  session, tf, score; platform normalizer (D12) shipped in platform v5.00.
- C4 — RECORDED: PULLBACK stays v18-only on purpose; "Friday revisit".
  Status: decision card open.
- A6 — DONE (message truth only); real DD limits await Shyam's numbers.
- B3, B5, B2, B7 — DONE in the brain repo (polymarket secret, two-witness
  /candles, backfill lock, push_bias nesting).
- B4 — dashboard AI-mode toggle: platform session, code lives in
  brother-brain-v2/dashboard/backend. Status: OPEN elsewhere.
- Round 3 item 4 — readiness cron `45 21 * * 0 ... post_readiness.py`:
  "Verify on the box with crontab -l; add the line if absent." Status: UNKNOWN.
- Round 3 item 6 — BRANCH DIVERGENCE: mirror branch (41 commits: resolver,
  /symbolspec, BRIDGE_KEY gate, evidence reports) vs deploy branch (34
  commits). Contabo converged on main 2026-09-15; whether the mirror-branch
  files (`setup_edge.py`, `v7_counterfactual.py`, `probe_symbol_specs.py`,
  `push_doc.py`, resolver bridge) were merged into main is NOT visible in this
  checkout — they are absent at f7cacfd. The deploy-branch `sniper_executor.py`
  must never be copied over the box's. Status: OPEN (bridge convergence).

# Windows / v18 leftovers recorded on the bot side

- The v18 executor box repo's remote `brother-executor-v18.git` is DEAD; the
  snapshot 1baa72a lives only on the box. Decide (Shyam): a real GitHub repo
  for the v18 executor or fold it into brother-brain-v2. Status: OPEN.
- Windows updater `update.ps1` — blocked until the platform serves
  `sniper_executor.py` at `/downloads` with its hash. Status: OPEN.
- Reporter V18 key file on Windows. Status: OPEN (decision, not code).
- One-launcher rule for the reporter: measure whether the Scheduled Task
  still exists, disable it, keep NSSM, correct the platform map. Status:
  UNKNOWN whether done.

# Round 4 (2026-09-03) leftovers

- Reconciliation layer: `core/reconcile` stays on the trade-desk branch
  ("next port"); the heartbeat posts `reconciliation: None`. Status: OPEN.
- Forked contract: decisions under the raw Pine id (/decision), closes under
  `v7-<id>` (/signal). ONE namespace is a convergence decision. Status: OPEN.
- BOT-P0-2 (docs/START_HERE.md): Pine's `signal_id` as the single canonical
  id across both arms; `FALLBACK_ID` still appears on /funnel. Status: OPEN.

# Dual-MT5 isolation audit (2026-09-04 .. 2026-09-15)

- ISO-01 RESOLVED on the box (2026-09-05). ISO-02, ISO-03, ISO-05, ISO-16,
  ISO-24 deployed (2026-09-05). ISO-06 deployed on the Windows bridge via the
  box variant; ISO-07/08 deployed on Contabo via git (2026-09-15). The Job 3
  entry says: delete it only when each P0 record is `resolved` with its
  golden fixture named — the brother-developer memory records are the proof
  location. Status: code DONE; ledger closure per record lives in
  brother-developer (`docs/audits/P1_CLOSURE_2026-09-15.md`).
- Still open decisions, not code (2026-09-15): ISO-19 shadow soak n >= 20;
  v18 resting pending-order expiry policy; weekly AI budget; `closed_at`
  clock; USA500 in BIAS_CORE_SYMBOLS; `USE_DEMO=false` label (P2, trade_mode
  is measured); reporter V18 key file. Real money stays NO-GO.

# START_HERE open work (bot side, 2026-08-21) — updated status

1. `entry_dist_atr` into v7 telemetry — DONE (patch_entry_dist_atr.py,
   2026-08-21; on the repo bot.py).
2. BOT-P0-2 canonical `signal_id` across both arms — OPEN.
3. Windows updater — OPEN (blocked on platform /downloads).
4. Convergence — Contabo DONE 2026-09-15; Windows bridge and mirror-branch
   scripts OPEN.
Open questions to keep honest: Do Pine grades predict? UNKNOWN. Does entry
distance kill edge? One population. Which assets bleed? Measured (GOLD, ETH),
actionable only by choosing to change one organ. Candle-timestamp incident:
BTC rebuild pending at handover; current state UNKNOWN from this repo.

# Autonomy plan queue (docs/V7_AUTONOMY_PLAN.md) — organs in order

- Freshness gate v1: SHADOW (live). Enforce decision pending shadow n >= 20.
- Freshness v2 (material move vs live tick via BRIDGE_KEY plumbing): the
  module accepts the inputs; "only the wire is missing". OPEN.
- Position-management rules beyond BE/partial (SL-modify, TP continuation,
  trailing): harness first, per organ; `mgmt_replay.py` NOT RUN as a report;
  TP1/trail/runner/news-aware UNKNOWN (need the price path). OPEN.
- Pending-order TTL organ (cancel/re-evaluate pending orders older than N
  bars), shadow-then-enforce. OPEN.
- Session-specific SL/TP (Asia/London/NY): strategy change -> backtest
  harness first. OPEN.
- News-window unblocking ("don't block high-impact time"): HELD; now being
  measured through NEWS01 observe mode (2026-09-16). OPEN, collecting.
- ICT features (FVG, OB, CISD, rejection blocks, opening gaps): platform
  research layer, dark, log-only. OPEN platform-side.
- Weekly/monthly outlook feed: post_outlook.py + auto-weekly exist; OPEN as a habit.
- Server cleanup / app speed: platform-side fixes (cache read models, add
  uvicorn workers, bound queries, 1m retention). OPEN platform-side.
- Path to DEMO auto-exec for auto_live: (a) >= 1 week clean dry log with
  v7's real gate replies, (b) US30/USTEC probe (settled 2026-08-31 per
  probe_symbols.py commit), (c) run the mgmt-state audit, (d) explicit
  `AUTO_LIVE_ARM=1` by Shyam. Status: SHADOW; arming UNKNOWN from repo.
- Review questions (2026-08-29): auto-v1's own cost-discounted verdict per
  engine; the agreement cut (Pine better when auto-v1 agrees?). Agreement
  becomes measurable via `pine_structure`. OPEN, collecting.
- Adaptive gates: shadow wiring of `profile_verdict` at the decision site
  (anchor-safe patch, `[ADAPTIVE SHADOW]`), then first CAUTION mapping via
  ASSET_GATE_SIZE where a negative cell is measured and both populations
  agree; news PRE/EVENT/POST modes; event profiles. OPEN (week-2+).
- Adaptive-gates spec week-2 follow-up: "mirror_v7_close does not send
  mae/mfe" — the current `learning/platform_mirror.py` DOES send mae/mfe in
  the outcome dict, so this appears DONE in code; the spec entry was not
  updated.

# NVDA queued organ (asked by Shyam 2026-09-02)

Phase 0 PROBE — DONE (spec + US-session quote measured; overnight spread
UNMEASURED). Phase 1 COLLECT — live (four collectors; platform 5.08 rows
recorded; join-key fix shipped). Phase 2 ANALYZE — in ~4 weeks (>= 100
shadow signals or 4 weeks, whichever later): session cut, earnings-window
cut, gap-open behaviour, spread per ATR, with-trend vs counter. Phase 3
ENGINE nvda-v1 — not started. Design facts to confirm: earnings gaps,
overnight CFD spread multiple, NVDA and US100 as ONE exposure
(PLAT-EXPOSURE-1 is Shyam's decision).

# Bot side OWES the platform (docs/UI_WORK_ORDER_2026-09-02.md)

1. MAJOR_EARNINGS rows in the calendar feed (new organ, harness first;
   the FF feed is macro-econ only). OPEN.
2. Branch convergence (mirror vs deploy; box bridge = mirror + A1). PARTIAL.
3. A2 step 3 after Shyam's nginx line: remove auto-injection, rotate secret. OPEN.
4. DXY_U6 roll watch, mid-September 2026 (first "symbol not known" line). OPEN.
5. NVDA phase 2 in ~4 weeks: three shadow populations, one key (NVDA). OPEN.
Also D13: B4 dashboard work belongs in brother-brain-v2 (bot side). OPEN.
Shyam's buttons: RESOLVE on INC-0001 and INC-0003; C11 dead rows
USOIL/XRP/USA500 (merge/delete/keep-named). UNKNOWN whether pressed.

# Audit 2026-08-01 leftovers still open

- G-1: `core/sl_engine.py` `round(sl_raw, 2)` on the institutional path
  (5-digit forex). Not fixed (needs its own reviewed diff). OPEN.
- G-2: the `max(0.003, ...)` effective-risk floor re-inflates the 0.25x/0.5x
  cluster scale. Listed, not changed (risk change = human decision). OPEN.
- H-3: adopted trades' direction from the bridge `type` field — the repo
  bridge sends "BUY"/"SELL", so the risk is mitigated; not separately closed.
- H-4/decision card 2: DD guard at 99%. OPEN (Shyam's numbers).
- H-5: 345 KB `signal_memory_backup_20260430.json` committed. Noted, kept.
- Rotate WEBHOOK_SECRET (H-0). OPEN (deferred, DEMO).
- Re-run the MAE study at n >= 100; if deepseek's anti-signal persists at
  n >= 40 it is evidence to ignore its blocks. OPEN (data).
- Strategy Intelligence stages 4-7: nightly report polish, dashboard
  heatmaps (platform), out-of-sample train/validate + stability check before
  any weight promotion, then the +/-10% live weight governor with cooldown
  and rollback-on-drawdown. OPEN ("not time-sensitive").

# Constitution-level queued work (CLAUDE.md)

- CMS Phase 1 per CMS_MASTERPLAN.md (login, account registry, per-account
  health + ON/OFF); CMS manages accounts/routing, NEVER signals. OPEN.
- `usd_lag_backtest.py` (DXY_U6 vs gold lag rule) — harness first. OPEN.
- v18.9 dark flags SB_PENDING, BIAS_INFO, ASSET_PULSE, BREAKOUT await
  harness validation. OPEN.

# ROADMAP (Shyam, 2026-06-06) — priority order, one at a time

1. Signal database — every signal stored with full metadata (signal_memory,
   telemetry, platform mirror exist; status: largely built).
2. Performance dashboard — WR by grade, asset, R-multiple (scorecard,
   nightly_edge, platform pages; status: built and growing).
3. Stable MT5 execution — finish Task 9 async webhook (status: UNKNOWN; the
   webhook is synchronous with a 15 s bridge timeout and RECONCILE fallback).
4. Risk manager — news, spread, confidence gates (news: NEWS01; spread: not
   modelled in v7 sizing, only logged; status: PARTIAL).
5. AI chart detection — ONLY after 1-4, as a vote not boss; 100+ recorded
   signals before the layer is added (analyst_eye is log-only; status: shadow).
