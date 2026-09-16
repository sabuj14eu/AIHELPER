---
title: Brother v18 Brain — Validated Solutions
domain: brain
repo: sabuj14eu/brother-brain-v2
sources: docs/decisions.md, docs/AUDIT_2026-07-31.md, docs/EXECUTOR_DEPLOY_2026-07-31.md, docs/OPEN_ITEMS.md, docs/PINE_VS_BOT_MAP.md, docs/SESSION_COORDINATION.md, brain/src/main.py, brain/src/agents/council.py, brain/src/agents/base.py, brain/src/agents/researcher.py, brain/src/pine_trust.py, brain/src/utils/decision_journal.py, brain/src/platform_mirror.py, brain/src/market_vision.py, brain/src/position_check.py, brain/src/shadow_gate.py, brain/src/signals/dispatcher.py, brain/src/notify.py, brain/mirror_outcomes.py, brain/remirror_decisions.py, brain/reconstruct_decisions.py, brain/backfill_journal_outcomes.py, brain/push_bias.py, brain/push_news.py, brain/patch_*.py, brain/tools/check_pine_ver.py, brain/src/agents/PINE_SOURCE.md, dashboard/backend/patch_*.py, executor_ic_markets/src/main.py, executor_ic_markets/src/ic_markets/mt5_bridge.py, executor_ic_markets/src/utils/state.py, executor_ic_markets/src/utils/global_stop.py, executor_ic_markets/src/clock_witness.py, executor_ic_markets/patch_*.py, shared/src/protocol/envelope.py, tests/*.py, tests/audit/**, brain/tests/*.py, brain/tests/audit/**, git log
verified_on: 2026-09-16
classification: INTERNAL
---

# Validated solutions in the v18 brain repository

Each entry below is a problem that was actually diagnosed and fixed in this repository's history, with the proof location. Dates are those recorded in the source comment, doc or commit.

### TradingView webhooks time out at 3 seconds while the council takes 5–90 seconds
question: Why does /webhook/v18 answer TradingView before the council has decided?
answer: TradingView documentation (verified 2026-05-21) says webhooks time out at 3 seconds; the 6-agent council deliberates for 5–90 seconds, so a handler that waited would make every real alert show as failed in TradingView even when the brain processed it. The fix made `/webhook/v18` parse, authenticate, dedupe and return `{"accepted": true, "signal_id": ...}` immediately, then run `_run_v18_council` as an `asyncio.create_task` background task, journaling from the task. The same fire-and-forget pattern was applied to `/webhook/polymarket`.
evidence: docs/decisions.md "2026-05-21 morning — TradingView 3s timeout discovered"; brain/src/main.py `v18_webhook` and `_run_v18_council`

### Anthropic Tier 1 rate limit broke the council mid-round
question: Why did the first end-to-end council run fail with a 429 and what was decided?
answer: On 2026-05-21 the first real council round died at the Researcher's retry with `anthropic.RateLimitError 429`: the account was Tier 1 (30,000 input tokens/min) and a council round needs roughly 60K tokens across six agents, so a parse-failure retry could never complete. The decision was to move to Tier 2 by adding credit (auto-promotion on spend). The Researcher parse bug was left as a separate item; its `max_tokens` had already been raised from 4000 to 8000 as a workaround.
evidence: docs/decisions.md "2026-05-21 — Rate-limit blocker discovered (Anthropic Tier 1)"; brain/src/agents/researcher.py `run(..., max_tokens=8000)`

### Emergency HALT drill exposed a missing nginx allowlist entry
question: What did the first emergency halt drill find and why is drilling a rule?
answer: On 2026-05-26 the watchdog's `halt_all.py polymarket` failed twice silently before the third attempt showed HTTP 403 at nginx: the Frankfurt executor's geo allowlist did not include the Amsterdam watchdog IP, so an emergency halt would have been impossible in a real incident. The fix added the watchdog IP to the executor's nginx geo block; the drill then tripped `kill_switch`, confirmed on `/health`, and was reset by editing state.json plus a restart. Lesson recorded: "test BEFORE you need it."
evidence: docs/decisions.md "2026-05-26 — Emergency HALT drilled successfully (first time)"; watchdog/src/halt_all.py

### Polymarket order placement is geoblocked from Germany
question: Why was the Polymarket executor to be moved to Dublin instead of using a proxy?
answer: On 2026-05-30 the V2 CLOB returned 403 on POST /order from the Frankfurt droplet; per Polymarket's geoblock docs DE/NL are fully blocked and PL is close-only, while read endpoints work. Everything else (V2 auth, market discovery, order construction, four on-chain approvals) had already been verified from Frankfurt. The decision was to migrate the executor to DigitalOcean Dublin and to reject proxy circumvention because the TOS forbids it, a wallet ban is permanent, a proxy costs more than a droplet, and it changes nothing about Polish law. The executor was later decommissioned entirely.
evidence: docs/decisions.md "2026-05-30 — Geoblock discovered, Dublin migration planned"; dashboard/backend/patch_dashboard_remove_pm.py

### Polymarket reconciler stub replaced by a three-layer real wiring
question: How did the Polymarket executor reconcile positions before any live funds?
answer: The reconciler originally returned `{}` for on-chain positions (a blocking open item from 2026-05-22). On 2026-05-27 it was replaced by three layers that degrade gracefully: a local `PositionsLedger` JSON, a `CLOBPositionsView` summing buys minus sells from `get_trades()` when the CLOB is authenticated, and an `OnchainPositionsView` via `balanceOfBatch` on the Conditional Tokens contract when a wallet address is set; the active mode is surfaced in `/health.positions`. With no wallet configured the system runs correctly degraded in stub mode.
evidence: docs/decisions.md "2026-05-27 — Reconciler real-wiring deployed (3-layer)"

### Duplicate signals after a brain state wipe
question: What stops the same Pine alert being posted twice within minutes?
answer: The 06-12 incident (a state wipe led to a double post) added a 300-second in-memory dedupe keyed on `symbol|side|entry|sl|origin` in `/webhook/v18`. On 07-02 a second bug was found: the body carries `signal`/`direction`, not `side`, so every key had `side=None` and an opposite-direction signal at a similar entry could be swallowed as a duplicate; the key now reads `side` or `direction` or `signal`. The executor's per-symbol slot guard and the later per-signal_id store remain the backstops because a brain restart clears the in-memory window.
evidence: brain/src/main.py `_DEDUPE_WINDOW_S`, `_dedupe_key` (comments 06-12 and 07-02 FIX)

### Council cost control by grade gate and margin pre-check
question: Why does the council only run for A/A+ and one in three B signals?
answer: To control API spend (06-12) the brain sends only A/A+ and a random one-third of B signals to the 6-agent council; the rest approve from Pine trust at zero cost or are grade-rejected. On 06-15 a margin pre-check was added so the council never spends money on unaffordable trades: it reads `/positions.account` from the executor and skips when `margin_free < max(10% balance, $100)`. The audit of 2026-07-31 lists this grade gate as a documented, by-design council bypass.
evidence: brain/src/main.py "GRADE GATE (cost control, 06-12)" and "MARGIN PRE-CHECK (06-15)"; docs/AUDIT_2026-07-31.md §1

### MT5 IPC blip at bar close killed A-grade signals
question: Why does the margin gate retry once after 2.5 seconds?
answer: Signals land at 15-minute bar closes, MT5's busiest instant, and the terminal's IPC briefly refused calls (-10001 "IPC send failed", seen in the executor reconciler at the same second as a 12:15 failure). Two A-grade signals were killed by that single-packet fragility. The fix (07-03) retries the account-margin fetch once after 2.5 seconds and still fails closed if the second attempt returns nothing — "never trade blind on margin."
evidence: brain/src/main.py comment "07-03 IPC-BLIP RETRY"

### Market vision fetched fake HTF data because query params were ignored
question: Why did the council's H1/H4 trends look identical to M15?
answer: `market_vision.py` originally called the executor `/candles` with `timeframe` and `count`, but the endpoint's signature is `(symbol, tf, n)`, so the parameters were silently ignored and every request returned default M15 data; the council's HTF trends were fake copies. Verified live on 06-30 (`?timeframe=M15&count=3` returned count 200; `?tf=M15&n=3` was respected). The fix uses `tf`/`n` and discards any response whose echoed `tf` differs from the request ("better blind than wrong").
evidence: brain/src/market_vision.py `_candles` comment "06-30 FIX"

### A blocking order_send froze the executor's HTTP endpoints
question: Why does the executor route every MT5 call through one worker thread?
answer: MetaTrader5 is a single non-thread-safe session; a blocking `mt5.order_send()` on the FastAPI event loop froze `/health`, `/positions` and the next signal for up to ~15 seconds (v18 timeout fix 2026-06-29). The executor now runs all blocking MT5 calls on a `ThreadPoolExecutor(max_workers=1)` via `_mt5_call`, so the loop never blocks and MT5 access serializes; the reconciler submits its reads to the same worker. `max_workers` must stay 1.
evidence: executor_ic_markets/src/main.py "Single-worker MT5 serialization (v18 timeout fix 2026-06-29)"

### 761 provider errors were counted as Scout rejections
question: How are API failures kept out of the approval statistics?
answer: For weeks, wallet/529/500 errors from the model provider were journaled as "Scout" rejections, poisoning approval stats (761 rows). Since 07-02 any result whose reason starts with "agent failed" is reclassified as `rejected_by="AgentError"`; for A/A+ entry signals the brain falls back to Pine trust (fail-soft) so a provider hiccup cannot kill a top-grade signal, while MANAGE results are exempt because approving a fresh OPEN on an occupied slot is unsafe.
evidence: brain/src/main.py "07-02: API/AGENT FAILURES ARE NOT TRADING DECISIONS"

### Scanner signals are barred from the pine_trust auto-approve path
question: How is the -60R scanner bypass prevented in code, not just remembered?
answer: The MT5 scanner's proposals once rode the pine_trust auto-approve path and lost 60R, which is the origin of Iron Rule 1. `approve_from_pine` now refuses any opportunity with `origin == "mt5_scanner"` ("scanner proposals have no Pine gates behind them and must ALWAYS face the council"), and the scanner itself is DRY-RUN unless a `POST_ENABLED` file exists. The audit lists this among the "good / correctly implemented" items: "the -60R lesson is enforced in code, not just remembered."
evidence: brain/src/pine_trust.py (07-02 comment); scanner_mt5/scanner_mt5.py; docs/AUDIT_2026-07-31.md "Good"

### BSv11 LITE alerts burned council money and then broke TradingView delivery
question: What happens to a BSv11 payload at the brain?
answer: An early patch sent BSv11 (LITE, 15-minute) alerts to the full council, which burned API money on every alert — "wrong design, reverted." On 07-09 Shyam ordered that v18 never judges or trades v11: the brain posts a provider-style Telegram message and returns, while the nginx mirror delivers the raw alert to v7, the only bot trading v11. On 07-10 TradingView showed more than 70% webhook delivery failures because the Telegram post was synchronous (up to 10s); it now runs on a daemon thread and the webhook answers in under 50ms.
evidence: brain/patch_brain_v11_telegram_only.py, brain/patch_brain_v11_nonblocking.py, brain/src/main.py BSv11 branch

### The dashboard's teaching line contradicted the verdict
question: Why did a card say "REJECTED - Quant: no edge" while the teaching line showed Scout's plan?
answer: The council teaching line always showed Scout's proposal (then Devil's) even when Quant or Devil was the rejecter, so the lesson contradicted the verdict. The 07-10 fix makes `council_says` prefer the rejecting agent's proposal, falling back Devil → Scout → Quant; approved trades keep Scout-first. Display-only, no bot or journal touched.
evidence: dashboard/backend/patch_dashboard_council_v2.py

### Service wall with candle freshness catches "process alive, MT5 stale"
question: How does the dashboard detect a v7 bridge that answers /health but serves stale candles?
answer: On 07-09 the v7 bridge process was alive while MT5 was stale. The 07-10 service wall added systemd unit states for six Contabo units, the Windows v18 executor `/health`, and for the v7 bridge the newest GOLD M15 candle age: stale beyond 12h turns the tile RED even when `/health` says ok (weekend-aware). One glance answers "is anything silently dead?"
evidence: dashboard/backend/patch_dashboard_svcwall.py; dashboard/backend/main.py `_bridge_freshness`, `/api/services`

### LIVE-20260713-GHOST: approvals journaled, nothing placed, all tiles green
question: What was the ghost incident and what three fixes came out of it?
answer: For five days the v18 arm journaled approvals with dispatch status 200 while placing nothing, and every health tile stayed green. Three fixes on 07-19: the journal now records the dispatcher's real return (`status`, `nonce`, `response`, `error`) instead of three keys the dispatcher never emitted, so the executor's ticket or rejection reason is no longer discarded; the dashboard gained bot-guards that read executor `/outcomes` tickets and turn RED on "approvals in 24h with zero tickets"; and the executor's daily counters roll over on a new UTC day inside `/signal`. This is the incident behind Iron Rule 6.
evidence: brain/patch_journal_dispatch_truth.py; dashboard/backend/patch_dashboard_botguards.py; executor_ic_markets/src/main.py `_state.roll_if_new_day()` comment "07-19 [LIVE-20260713-GHOST]"

### Pine's new fields never reached the journal (append-tolerant listener)
question: Why was pine_ver absent from every journal row before 07-20?
answer: `_build_v18_opportunity` lifted alert fields into the snapshot from a fixed whitelist, so every v18.8 observability append (pine_ver, payload_schema, fired_at, trend_age, level_src, rr2, dist_ideal, vwap_side) was dropped at the door; grep confirmed pine_ver had never reached the journal. The fix passes through every remaining scalar key of the body into `market_snapshot`, so future Pine appends flow to council and journal automatically. It produced the rule that the listener must be append-tolerant, matching Iron Rule 2.
evidence: brain/patch_brain_passthrough.py; brain/src/main.py "07-20 [APPEND-TOLERANT LISTENER]"

### Min-lot rounding multiplied risk 60x on a small account
question: Why does the executor skip trades whose correct size is below 0.4x the minimum lot?
answer: Ticket 1697829693 asked for 0.41 USD of risk; rounding up to the broker's minimum lot lost 25.18 USD. `_compute_lots` now computes the inflation and skips (with a Telegram note) when `raw_lots < volume_min * 0.4`; DECISION-A (07-20, demo phase) tolerates up to 2.5x inflation at the minimum lot (was 2x) because "a starving arm buys no data" while 60x-class disasters stay blocked. A read-only `/cansize` probe exposes the same math to the session caller's affordability pre-filter.
evidence: executor_ic_markets/src/ic_markets/mt5_bridge.py `_compute_lots` "MIN-LOT RISK GUARD", `sizing_probe`; docs/AUDIT_2026-07-31.md addendum P1-4

### LIVE-20260724-STUCKTERMINAL: a LiveUpdate dialog blocked MT5 for days
question: How does the wall show that a human must click OK on the MT5 terminal?
answer: The MT5 terminal sat on a LiveUpdate dialog for days; HTTP stayed green, the council kept approving, and every trade died with `sizing_failed` (no balance) and MarginGate "account margin unreachable" (34 fail-closed rejections). Nothing on the wall said so. The 07-26 fix counts "margin unreachable" rejections in the last 24h; three or more is the stuck-terminal signature and turns the bot_v18 tile RED with an actionable message.
evidence: dashboard/backend/patch_botguard_margin.py (also mirrored at brain/patch_botguard_margin.py)

### A dropped MT5 link served 200s with an empty account for days
question: What does `_ensure_connected` fix in the executor bridge?
answer: A logged-out or bounced MT5 terminal left the executor serving HTTP 200s with an empty account while the brain fail-closed for days — "Iron Rule 6 made flesh." `_ensure_connected` probes `account_info()` on every read and, if dead, attempts one re-initialize throttled by `MT5_RECONNECT_COOLDOWN` (5s), turning a drop into a seconds-long blip. Since ISO-09 every probe also re-asserts the login.
evidence: executor_ic_markets/src/ic_markets/mt5_bridge.py `_ensure_connected`

### Audit P0-1: the executor in git was not the executor that trades
question: Why could the 2026-07-31 audit not certify the executor, and how was it resolved?
answer: The brain called `GET /positions`, `GET /candles`, `GET /outcomes` and dispatched MODIFY/CLOSE_ONE, none of which existed in the repo executor: production had been patched live on the Windows box and never synced, so "a disaster-recovery rebuild from this repo would produce a system where every brain signal fail-closes." The same evening the deployed snapshot (branch `live-snapshot-20260731`) was byte-synced into `executor_ic_markets/` and the live brain was verified byte-identical to `main`.
evidence: docs/AUDIT_2026-07-31.md P0-1 and Addendum; docs/EXECUTOR_DEPLOY_2026-07-31.md "The repo executor is now byte-synced"

### Audit P0-2: the daily loss cap could never fire
question: Why was MAX_DAILY_LOSS_PCT decoration and what feeds it now?
answer: `pnl_pct_today` was initialized, reset and read but never written, so the 2% daily loss cap was "not enforced anywhere in this repo" and confirmed dead in production too. The fix wires the reconciler's close-tracker to `on_close(pnl, close_epoch)`, which calls `ExecutorState.add_realized_pnl(pnl, balance)` (net P/L ÷ balance) for today's closes only and trips the kill switch with a Telegram alert at the cap, both at close time and in `/signal`.
evidence: docs/AUDIT_2026-07-31.md P0-2 and Addendum; executor_ic_markets/src/main.py `_on_trade_closed`; tests/test_executor_state.py

### Audit P0-3: LLM-generated prices reached MT5 unchecked
question: What does _validate_prep_payload assert before a council payload is signed?
answer: On the council path the final payload was assembled by the ExecutorPrep LLM and the only checks were "has action" and "no error" — one hallucinated digit or transposed SL/TP would reach the broker. The fail-closed gate added on 07-31 asserts action OPEN, symbol and side equal to the signal, entry within 5% of the Pine entry, correct SL/TP geometry per side, SL/TP within 20% of entry, and `0 < risk_pct <= 2.0`, returning `rejected_by="PrepValidation"` otherwise. ISO-19 later removed the LLM from price authorship entirely; the validator remains as a belt.
evidence: brain/src/agents/council.py `_validate_prep_payload`; tests/test_prep_validation.py (12 tests)

### Audit P1-1: the council could be bypassed on failure without limit
question: How is the fail-soft policy bounded?
answer: An API failure on an A/A+ entry fell back to Pine trust without limit, so a provider outage silently converted the system to "Pine A/A+ auto-trades all day"; a Devil failure silently skipped the veto stage. The fix keeps fail-soft as a documented policy but budgets it: after `FAILSOFT_MAX_PER_DAY` (default 2) fail-soft approvals per UTC day the brain fails closed and posts a Telegram warning; the Devil is retried once and a second failure is tagged `failed: true` so calibration and the mirror can exclude it.
evidence: brain/src/main.py `_failsoft_state`, `FAILSOFT_MAX_PER_DAY`; brain/src/agents/council.py Stage 4 comment "07-31 [AUDIT P1-1]"

### Audit P1-2b: a restart reset the daily trade budget
question: Why is cap_day a persisted ExecutorState field?
answer: The midnight rollover had been fixed live on 07-19 but `cap_day` was set as a dynamic attribute, so `asdict()` never persisted it and every service restart made the first OPEN reset `trades_today` to 0 — a mid-day restart doubled the daily budget. `cap_day` became a dataclass field written to `state.json`, and `roll_if_new_day()` resets counters only when the UTC day actually changes.
evidence: executor_ic_markets/src/utils/state.py comment "07-31 [AUDIT P1-2b]"; tests/test_executor_state.py

### Audit P1-3: no per-signal idempotency at the executor
question: How does the executor refuse the same logical signal dispatched twice?
answer: The envelope nonce is unique per dispatch, so it cannot catch one logical signal dispatched twice (brain restart inside the dedupe window, same-symbol burst). The brain now appends `signal_id` to the dispatched payload (append-only), the executor keeps a 6-hour `NonceStore` of seen signal ids and rejects `duplicate_signal_id`, and the ticket registry records `signal_id` per ticket. Since ISO-13 the store key carries the asserted login.
evidence: brain/src/main.py "07-31 [AUDIT P1-3]"; executor_ic_markets/src/main.py `_signal_ids`; docs/EXECUTOR_DEPLOY_2026-07-31.md item 3

### Market orders were priced at the stale Pine entry
question: Why do market orders use the live tick and not the signal's entry?
answer: The repo executor once sent `TRADE_ACTION_DEAL` with `price = entry_price` (seconds-to-minutes old) and `deviation 10`, so any move beyond 10 raw points was a silent requote loss with wildly different tolerances across symbols. The deployed executor already used `symbol_info_tick()` ask/bid for market orders and validated pendings against the market side; that behavior is now in the repo, and ISO-14 later removed the stale-pending market conversion.
evidence: docs/AUDIT_2026-07-31.md P1-5 and Addendum; executor_ic_markets/src/ic_markets/mt5_bridge.py "market order: always use LIVE price"

### AI spend: weekly hard cap, real-usage ledger, caching and model tiering
question: How does the brain stop council spend before the network call?
answer: On 08-17 the agent base class gained `_budget_guard` (refuse the call when the week's recorded spend reaches `BRAIN_AI_WEEKLY_BUDGET_USD`, raising AgentError which the council handles fail-closed), `_record_spend` (a JSONL ledger of real token usage per response at env-tunable prices), prompt caching of the identical system prompt (`cache_control: ephemeral`), and per-agent model tiering (`ANTHROPIC_MODEL_<AGENT>`). Parse retries are recorded because each doubles a call's spend. `push_bias.py` reports `council_paused: "ai_budget"` to the platform so a budget pause is distinguishable from a quiet market.
evidence: brain/src/agents/base.py (08-17 COST comments); brain/ai_spend_report.py; brain/push_bias.py `post_brain_status`

### The Researcher bypassed the budget guard for a week
question: What structural test prevents an agent from calling the API unmetered?
answer: The Researcher overrode `run()` to add the web_search tool and in doing so bypassed `_budget_guard` and `_record_spend` on the most expensive agent for a week (08-18). The override now calls both, and an AST-based test asserts that any agent overriding `run()` is allow-listed and still calls the guard and ledger, and that `messages.create()` appears only inside `run()`/`_retry()` — "so the next special-needs agent fails CI instead of quietly spending money unmetered."
evidence: brain/src/agents/researcher.py "[08-18 COST]"; brain/tests/test_agent_outbound_path.py

### BOT-P0-1: journal outcome fields were never filled
question: How do council decisions get their WIN/LOSS outcome in the journal?
answer: `write_decision` always wrote `outcome/pnl_net/exit_reason/closed_at` as None "filled later by Piece B" and nothing ever filled them, so every decision was unjudgeable. `backfill_journal_outcomes.py` joins the executor's `/outcomes` close-tracker rows by ticket, rewrites the journal atomically with a timestamped backup, requires an identical line count, aborts if any non-outcome field would change, and is idempotent. On 2026-09-02 (B2) the writer and the backfill were put under one fcntl lock because a live append between the backfill's read and `os.replace` was silently destroyed.
evidence: brain/backfill_journal_outcomes.py; brain/tests/test_backfill_race.py; brain/src/utils/decision_journal.py "[B2 2026-09-02]"

### BOT-P0-2: the brain minted its own signal_id instead of adopting Pine's
question: Why did the executor's duplicate guard never catch a real Pine duplicate?
answer: The brain minted a fresh id per alert, so two identical Pine alerts arrived at the executor as two different ids and the guard keyed on the dispatched id could not refuse the second. Since 2026-08-21 `canonical_signal_id` adopts Pine's `signal_id` verbatim and mints only when the payload carries no usable id; the source (`pine` or `minted_fallback`) is journaled and mirrored, and the platform's acceptance test is the FALLBACK_ID share on /funnel falling toward zero.
evidence: brain/src/utils/decision_journal.py `canonical_signal_id`; tests/test_signal_id_canonical.py; git 0f8f49d (test: pine_signal_id is the opportunity's own id)

### Economic calendar relay defeated by Cloudflare's User-Agent check
question: Why does push_news fetch with requests and fall back to a custom User-Agent?
answer: `push_news.py` (2026-08-26) posts the same ForexFactory weekly JSON the v7 news gate blocks on, all impacts, so the platform can say LOW honestly instead of UNKNOWN. On the first live run Cloudflare returned 403 to the default urllib User-Agent; `requests` (the library the bot itself uses) passes, and urllib with an explicit UA is the fallback. Rows missing title or date are dropped, never guessed.
evidence: brain/push_news.py `_fetch_feed`; tests/test_push_news.py

### Radar showed STALE bias merely because a chart was quiet
question: How does push_bias keep badges honest without repainting?
answer: The bias poster had died around 07-25 and quiet charts went STALE from silence alone. The 08-14 heartbeat pushes every symbol with a decision inside `BIAS_MAX_AGE_H` on every 30-minute cycle, and every item carries `as_of` (the decision's true timestamp) so the platform derives real age — "a re-posted 5-day-old bias is 5 days old and says so." A fresh EMA20/50/200 + ATR market read from the v7 bridge became the primary source; journal rows are the fallback with their own old `as_of`.
evidence: brain/push_bias.py docstring and `derive_bias`, `market_bias`, `merged_items`

### Macro bias fallback read the wrong nesting level
question: Why was the DXY/US10Y journal fallback permanently empty until 08-31?
answer: `macro_items` read `dxy_dir`, `yield_dir` and `oil_spike` at the top level of `signal_raw`, but the append-tolerant listener lands pass-through Pine keys inside `context.market_snapshot`, so the fallback never matched a row (the journal half of BOT-BIAS-1). The fix reads both levels, top level first.
evidence: brain/push_bias.py `macro_items` "[08-31 NESTING FIX]"

### Bias gaps for SILVER/US100 were silent for a week
question: Why does push_bias now log a reason for every symbol with no fresh row?
answer: `market_bias` returned None silently for "< 210 bars" and "ema/atr invalid", so the platform's SILVER/US100 gaps looked like a recovering mystery. Every None now logs `[bias] SYM: NO fresh row — <reason>` plus a per-cycle summary, and `BIAS_GAP_LOG` is test-visible. The first hypothesis (bridge returning < 210 bars) was later retracted when the real cause proved to be twin rows — but the reason line is what made that diagnosis possible.
evidence: brain/push_bias.py `gap_reason`, `_log_gap`; brain/tests/test_bias_gap_reasons.py; docs/OPEN_ITEMS.md "BIAS PUSH GAPS"

### SILVER/US100 "bias STALE" was a canonical-name twin
question: What was the actual root cause of the week-long SILVER and US100 stale badges?
answer: The pushed list carried two rows per instrument: the fresh market read under the broker name (XAGUSD, USTEC) and the stale journal opinion under Pine's name (SILVER, US100). `merged_items` deduped by raw name, the platform canonicalized both to one symbol, and the stale row landed last every 30 minutes. GOLD escaped because Pine's XAUUSD equals the broker's. `dedupe_canonical` now keeps one row per canonical name (newest `as_of` wins, the other's council opinion rides along as `council_as_of`) on everything that leaves the script. Proven 2026-09-03 21:08:41Z: pushed=14, no twins, NVDA present.
evidence: brain/push_bias.py `_CANON`, `canon`, `dedupe_canonical`; git cfc52e9, d440187; docs/OPEN_ITEMS.md "THE ACTUAL ROOT CAUSE"

### BIAS_* settings in .env did nothing
question: Why did adding NVDA to BIAS_CORE_SYMBOLS in .env have no effect?
answer: push_bias read `BIAS_*` from the process environment only, so `.env` lines for NVDA and the retired US10Y aliases did nothing (measured 2026-09-03: NVDA absent from both lists). `_cfg()` now has three honest states — process env (even empty), then `.env` (even empty), then the default — and `BIAS_CORE_SYMBOLS` accepts `CANON=BROKER` pairs so NVDA publishes under its canonical name while the bridge is asked for `NVDA.NAS-24`.
evidence: brain/push_bias.py `_cfg`, `core_symbols`; brain/tests/test_bias_gap_reasons.py `test_cfg_reads_dotenv_and_honours_explicit_empty`

### US10Y could not be served by the bridge: measured, not assumed
question: Why is US10Y honestly UNKNOWN whenever Pine is silent?
answer: US10Y had exactly two sources: a fresh bridge read through aliases (US10Y, TNX, UST10Y, US10YT, ZN1!) and a journal fallback from Pine's `yield_dir`. A probe run on the bot box on 2026-08-31 returned 404/400 for every alias — the fresh path never existed — and the journal path dried up with the Pine memory-limit bug. The decision was to build no feed on a guess: a Pine-independent yield source is a new organ needing a harness, and until then US10Y stays UNKNOWN with that fact stated on the card. DXY is not at the same risk because its alias list carries successor contracts.
evidence: docs/OPEN_ITEMS.md "BOT-BIAS-1 ROOT CAUSE" and "PROBE RESULT (2026-08-31)"

### US100 candles returned 400 from the bridge — never a bug
question: Why does asking the bridge for "US100" fail forever?
answer: The broker's name for that index is USTEC; US100 is a display name only, so any caller asking the bridge for "US100" gets a 400 forever. The brain was already correct (CORE uses USTEC); the alias must be resolved caller-side. US100's bias silence was therefore the Pine death alone. Closed on the 2026-08-31 probe.
evidence: docs/OPEN_ITEMS.md "BRIDGE SYMBOL PROBE — 2026-08-31"

### INC-0001: US10Y candles stopped because the broker delisted the contract
question: Why did the platform's US10Y 15m series end on 2026-08-27 20:58Z?
answer: The platform's US10Y candles came from the reporter under the dated broker name UST10Y_U6; the reporter had a static symbol list with no front-contract resolver, so when the September contract retired it kept asking for a dead name and pushed 0 bars with a WARNING nobody read. Both MT5 terminals were then listed: no US 10Y contract exists at this broker after the roll (only ITB10Y_U6, JGB10Y_U6, DXY_U6). Verdict: "US10Y PRICE CANDLES UNAVAILABLE AT THIS BROKER ... Not a bug." Yield direction still arrives from Pine's TVC:US10Y. A finding for the platform: US10Y is two inverse quantities under one name (yield from Pine, note price from the reporter).
evidence: docs/OPEN_ITEMS.md "ROUND 3 (2026-09-02)" and "INC-0001 — RESOLVED"; git 37e363b, f243a81

### INC-0003: five reporter processes wrote one platform row
question: Why did the board read "reporter-1.1.0 / mt5_running=false" while the service ran 1.6.0?
answer: A Windows process listing on 2026-09-02 showed five `mt5_reporter.py` processes: the NSSM service started 21 August plus four orphans from 8 August (two of them hung "backfill" runs alive for 25 days) holding the old 1.1.0 code in memory and overwriting the service's honest row every minute. The fix was to stop exactly the four orphan PIDs, never the service, then deploy reporter 1.7.0 with identity fields; the final listing showed one reporter. Standing rule: ONE reporter process per box, and every manual run ends with the process list checked. The CRLF hash mismatch on Windows was foreseen and fixed with `.gitattributes` in the platform repo.
evidence: docs/OPEN_ITEMS.md "MEASURED 2026-09-02 ... FIVE reporters" and "INC-0003 — CLOSED"

### GOLD ticket 1900277473 stayed "open" on the platform after it closed
question: Why did one MT5 position produce two platform trade rows?
answer: MT5 deals showed position 1900277473 opened 15:00:12Z and closed at TP 18:38:40Z, but the platform held two rows for (user 4, account 3, ticket) created 70 ms apart, both open: two reporter processes posted the same open at the same instant and the platform's read-then-insert upsert had no uniqueness on (user, account, ticket). The close updated only the first row; the orphan spawned every STOP_THROUGH/ORPHAN row. Bot side closed the recurrence by removing the concurrent writers; the platform was asked to dedupe and add a unique index.
evidence: docs/OPEN_ITEMS.md "GOLD SELL still open (ticket 1900277473) — ROOT CAUSE, measured 2026-09-03"; git 9cfb7b7

### A pinned broker UTC offset would have killed every feed on 2026-10-25
question: What was the dated landmine found in the reporter startup log?
answer: The reporter ran with `BB_BROKER_UTC_OFFSET=+3h` pinned (for the old 1.1.0 that had no detection) while `validate_broker_tz()` refuses to run when the tz calendar disagrees with the offset in use. On 2026-10-25 Europe/Athens becomes +2, the service would exit at start, NSSM would restart it every 5 seconds forever, and every feed would stop silently on a Sunday. The pin was removed on 2026-09-02 18:48; the start log then showed the offset DETECTED as +3h agreed by 18 fresh witnesses including NVDA.NAS-24.
evidence: docs/OPEN_ITEMS.md "DATED LANDMINE" and "2026-09-02 18:48 — pin removed"; git cd884a1, dad7eed

### The executor's /candles endpoint assumed a clock with one witness
question: Why does /candles return 503 "clock unverifiable" instead of guessing?
answer: The broker-epoch-to-UTC conversion used one witness and fell back to offset 0 with a false `utc_normalized`. B5 (2026-09-02) requires at least two fresh (within 6h) 24/7 witness ticks (default BTCUSD, ETHUSD) whose offsets, rounded to 30 minutes, agree; otherwise the endpoint refuses with a 503 and the reason. `clock_witness.py` is its own module so a non-git box can receive one whole file.
evidence: executor_ic_markets/src/clock_witness.py; executor_ic_markets/tests/test_clock_offset.py; executor_ic_markets/src/main.py `/candles` "[B5 2026-09-02]"

### NVDA phase 1: judged, journaled, mirrored, never dispatched
question: How can the council evaluate NVDA without any risk of an order?
answer: Without a gate, an approved NVDA signal would reach the executor whose symbol map passes unknown names through verbatim, and MT5 would reject "NVDA" — an order attempt failing, not a decision; and the day someone mapped NVDA to NVDA.NAS-24 the instrument would go live unnoticed. `shadow_gate.py` (2026-09-02) journals a shadow symbol's full council trace with `dispatch_mode blocked_shadow`, mirrors it as `rejected_by ShadowGate` with the verdict in the reason, and returns before `dispatcher.dispatch`; a structural test pins that ordering. Going live means removing it from `SHADOW_SYMBOLS`, a logged human decision.
evidence: brain/src/shadow_gate.py; brain/tests/test_shadow_gate.py; docs/OPEN_ITEMS.md "NVDA PHASE 1"

### Fail-soft approvals were invisible to the platform
question: How does the board know a trade was taken without the council?
answer: On 2026-09-02 the council API failed twice on A/A+ signals and both traded on Pine trust under the 2/day fail-soft, but the mirror sent "approved, council 0/0", indistinguishable from a routine grade-gate approval. The mirror payload now always carries `fail_soft` (bool), `fail_soft_reason`, `fail_soft_count` and `fail_soft_max` (so no page hardcodes "/2"), and main.py forces the trace marker to land even when the trust result has no trace.
evidence: brain/src/platform_mirror.py `_fail_soft`; brain/src/main.py "[2026-09-03] the marker must ALWAYS land"; brain/tests/test_mirror_failsoft.py; git e77378b, 78576f3

### ISO-09: the v18 bridge attached to whatever account the terminal held
question: How does the executor prove it is on MT5 account 52901228?
answer: With `MT5_LOGIN` empty the bridge called `mt5.initialize(path=...)` and adopted whatever account answered; with it set, the login was logged but never compared. On a box with two terminals that meant the account was UNKNOWN by construction. Since 2026-09-05 all of `MT5_LOGIN`/`MT5_PASSWORD`/`MT5_SERVER` are required (missing or non-numeric = NOT RUNNABLE), `account_info().login` must equal `MT5_LOGIN` after every attach and on every probe (a mismatch shuts the link down with CRITICAL "WRONG ACCOUNT"), and `/health` reports `account_login` and `trade_mode`.
evidence: executor_ic_markets/src/ic_markets/mt5_bridge.py `_do_initialize`, `_identity_ok`; tests/audit/2026-09-04_job3/test_v18_bridge_identity.py; tests/audit/2026-09-05_iso09/; executor_ic_markets/patch_iso09_login_assertion.py

### ISO-10: the signed envelope carried no account
question: Why does the envelope include account_id inside the signed bytes?
answer: At 84263f9 an envelope named no account, so an unknown account could execute a valid signature. Now `SignalEnvelope.account_id` is inside the canonical signed bytes; the dispatcher signs `EXECUTOR_IC_MARKETS_ACCOUNT` into every envelope and refuses live dispatch without one (`no_account_id`, nothing posted); the executor rejects `no_account_id` and `account_mismatch` against its asserted login before any order, and a stray account_id inside the signal body is not an identity. Print mode still prints without an account.
evidence: shared/src/protocol/envelope.py; brain/src/signals/dispatcher.py; brain/tests/audit/2026-09-05_iso10/; tests/audit/2026-09-04_job3/test_v18_signal_route.py ISO10b-e

### ISO-12: a loss seen with an unreadable balance was dropped
question: What happens to a closed loss when the executor cannot read the balance?
answer: `add_realized_pnl` used `balance or 0.0`, so a close seen while the terminal was dead contributed nothing to the daily loss counter. The loss is now parked in `pending_pnl_money` with `pnl_unknown_since`, persisted across restarts, and new OPENs are refused (`pnl_unknown_pending`) until it is applied on the next measured balance; if applying it crosses the cap the kill switch trips.
evidence: executor_ic_markets/src/utils/state.py "[ISO-12 2026-09-05]"; executor_ic_markets/src/main.py `_on_trade_closed`, `/signal` OPEN branch

### ISO-14: an invalidated pending order was converted to a market order
question: What does the executor do with a LIMIT whose price is already through the market?
answer: The old branch tolerated drift and converted an invalid LIMIT/STOP to a MARKET order (within a fraction of risk). ADR-006 (2026-09-05) rules that a pending already through the market "is a different trade, not this one, whatever the drift": the order is rejected with `pending_price_stale` and a Telegram note; valid pendings still go out as `TRADE_ACTION_PENDING`; market orders are unaffected.
evidence: executor_ic_markets/src/ic_markets/mt5_bridge.py "[ISO-14 2026-09-05, ADR-006]"; tests/audit/2026-09-04_job3/test_v18_bridge_identity.py ISO14 tests

### ISO-16: no global kill reached both arms
question: How does one emergency stop cover both the v18 executor and the v7 bridge?
answer: Each arm had its own kill switch; nothing halted both. `utils/global_stop.py` (ADR-008) defines one witness file (default `C:\brotherbot\GLOBAL_STOP`): present = STOP, absent = CLEAR, unreadable = UNKNOWN treated as STOP; every OPEN on the v18 executor checks it (not bypassable by GUARDS_DISABLED), the admin halt engages it, `/health` reports it, and the v7 bridge carries an identical inline copy. Clearing is a human deleting the file.
evidence: executor_ic_markets/src/utils/global_stop.py; executor_ic_markets/src/main.py `_on_admin_halt`; tests/audit/2026-09-04_job3/test_v18_signal_route.py ISO16 tests

### ISO-19: the council dispatched the LLM's own entry/SL/TP/risk
question: Who computes the execution payload on the AI-on path?
answer: Job 9 found the AI-on path dispatched ExecutorPrep's JSON — a model authored entry_price, stop_loss, take_profit and risk_pct after only a range check, and the council path never called `compute_sltp`. ADR-005 (2026-09-05): `build_execution_payload` computes the payload in code from the signal's own prices with the same calculator pine_trust uses; the RiskManager may only choose bounded `sltp_params` and lower `risk_pct` below the 0.5 base; a calculator failure is a rejection; ExecutorPrep is removed from the pipeline. A replay on 12 real rows reports BEHAVIOR CHANGED per widened stop.
evidence: brain/src/agents/council.py `build_execution_payload`; brain/tests/audit/2026-09-05_iso19/; brain/tests/audit/2026-09-05_job9/; git 21f6f31

### ISO-20 and ISO-21: no default risk and no raw-stop fallback
question: What changed on 2026-09-15 for missing risk_pct and calculator failures?
answer: The executor sized a missing `risk_pct` at the 0.5 default (`s.get("risk_pct", 0.5)`) — "a number the sender did not say is a fabricated number"; it now refuses `no_risk_pct` for a missing, non-numeric or non-positive value and still caps a present value at `MAX_RISK_PCT_PER_TRADE`. On the brain side pine_trust fell back to Pine's raw SL/TP when `compute_sltp` raised; it now rejects with `compute_sltp error ... (fail-closed, no raw-stop fallback)`.
evidence: executor_ic_markets/src/main.py "[ISO-20 2026-09-15]"; brain/src/pine_trust.py "[ISO-21 2026-09-15]"; brain/tests/audit/2026-09-05_job9/ (prefix fixture pine_trust_prefix_1686bdb.py)

### ISO-11, ISO-13, ISO-15: margin fail-closed, account-scoped state, no GUARDS_DISABLED bypass
question: What did the P1 executor batch of 2026-09-15 change?
answer: ISO-11: the margin-level floor wrapped its check in `except Exception: allowing trade`, so an account object whose fields raised skipped the floor exactly when the terminal was under stress; an unreadable margin now refuses `margin_unknown` while measured levels behave as before. ISO-13: the signal-id dedupe key is `"<asserted_login>:<signal_id>"` and `ExecutorState.account` is stamped from `MT5_LOGIN`; a state file naming another account trips the kill switch with counters kept. ISO-15: the GUARDS_DISABLED file no longer lifts the kill switch or daily caps (`_bypass` deleted); it is only reported on `/health` as `guards_flag_present`. Proposals were written and golden-tested on copies before the live files changed.
evidence: tests/audit/2026-09-05_iso11/PROPOSAL_ISO11.md; tests/audit/2026-09-05_iso15/PROPOSAL_ISO15.md; git 2b9460c; executor_ic_markets/patch_v18_executor_iso11_13_15_20.py

### A weak repro test passed whether or not the cap was reached
question: Why does the ISO-15 repro pin cap_day?
answer: While writing the ISO-15 tests it was found that `roll_if_new_day()` zeroes `trades_today` whenever `cap_day` is not today, and a fresh test state has `cap_day == ""`, so the Job 3 repro that set `trades_today` without pinning `cap_day` passed regardless of whether the bypass existed — a weak witness. The repro now pins `cap_day` and still reproduces, "the honest proof that the bypass exists."
evidence: tests/audit/2026-09-05_iso15/PROPOSAL_ISO15.md "Fixture note"; git 9b33825

### Release-gate patch artefacts proven byte-identical to the repo fix
question: How is a Windows deploy of the ISO fixes verified before it touches the box?
answer: Because the Windows executor is not a git clone, each batch ships as an anchor-safe script (`patch_iso09_login_assertion.py`, `patch_v18_executor_iso10_12_14_16.py`, `patch_v18_executor_iso11_13_15_20.py`) with golden tests that apply it to a pre-patch fixture tree and assert the output equals the repo files at the named commit, that a second run reports "Already patched", that an ambiguous anchor or a foreign new file writes nothing anywhere, and (for ISO-10) that the patched envelope signs the account. Proposal hunk modules got unique names (`proposal_hunks_isoNN`) so two proposal directories collect in one pytest run.
evidence: tests/audit/2026-09-05_deploy_v18_executor/test_deploy_v18_executor_golden.py; tests/audit/2026-09-15_p1_executor/; tests/audit/2026-09-05_iso09/test_iso09_patch_golden.py; git 91f70fd

### Mirror attribution: executor ticket and account on every decision
question: How is a broker row joined back to a council decision on the platform?
answer: Since 2026-09-05 the decision mirror carries `ticket` (extracted from the executor's `/signal` response) and `executor_account` (from `EXECUTOR_IC_MARKETS_ACCOUNT`), both append-only and None when not dispatched or refused. On 2026-09-11 `executor_status`/`executor_reason` were added so an approved decision the executor refused (kill_switch, slot_held, pending_price_stale, caps) stops reading as a plain approval.
evidence: brain/src/platform_mirror.py; brain/tests/test_mirror_ticket.py; git b86c0ba, 6ccd7c8

### INC-0004: the journal writer raised on every write for five days
question: Why did the journal, the platform mirror and Telegram all go dark from 2026-09-01 17:30Z?
answer: Commit ac8808e (2026-09-01 13:11Z) introduced a cross-process lock with `path + ".lock"` where `path` was a `PosixPath`, raising `TypeError` on every write; the `except OSError` did not catch it, so the exception escaped into `_run_v18_council` and took the platform mirror and the Telegram notice down with it. Fixed on 2026-09-05: `path.with_name(path.name + ".lock")`, and the writer catches every exception into a log line — "a journal failure must never reach the decision path." A pre-fix copy and a repro test that expects the TypeError are kept.
evidence: brain/src/utils/decision_journal.py "[INC-0004 2026-09-06]"; brain/tests/audit/2026-09-06_inc0004/; git 513a690

### Reconstructing the decisions the journal lost
question: How were the 1–6 September v18 decisions rebuilt for the platform?
answer: `reconstruct_decisions.py` (2026-09-11) rebuilds each decision from three witnesses: the brain's journalctl lines (`v18 [SIGNAL_ID] message`, with rules mapping messages to GradeGate/SlotGate/MarginGate/CostGate/agent rejections/pine_trust/council approvals), the v7 journal (symbol, direction, grade, receipt time), and the executor's event files (signal_verified/rejected, gzip supported). Each row is clock-checked against the Pine bar time in the id (0..70 min) or the v7 receipt (10 min), marked `backfill`, `reconstructed`, `witnesses`, and only resolved rows with a symbol are posted. Follow-up fixes added `--already-posted` (repeatable) after nine UNKNOWN-symbol rows were posted twice on 2026-09-15, and write the row file after the UNKNOWN mutation so re-runs never re-send.
evidence: brain/reconstruct_decisions.py; brain/tests/test_reconstruct_decisions.py; git b288968, 1686bdb, ddfe51a, 657e149

### Refusals read "unstated" on the platform
question: Why did six v18 refusals of 10–11 September show no reason on the board?
answer: Two causes: a council agent can veto with no reasoning text (the model's JSON had none), and the platform's decision ingest reads `payload.reason` while the mirror sent only `rejection_reason`. The mirror now says "<Agent> refused without reasoning text" when the text is empty and sends the same value under both `rejection_reason` and the append-only alias `reason`; `remirror_decisions.py` re-posts affected rows with today's payload and the original `ts_decided` inside the platform's 48h idempotency window.
evidence: brain/src/platform_mirror.py; brain/remirror_decisions.py; brain/tests/test_mirror_outcomes.py `test_remirror_...`; git 6ccd7c8, 325f209

### The executor's own witness for v18 fills, posted once with receipts
question: How does the platform learn that a v18 trade closed, and how is double-posting prevented?
answer: The platform has no broker-side reporter on the v18 terminal, so `mirror_outcomes.py` (2026-09-11) posts each closed outcome from executor `/outcomes` once to `/webhooks/brain/decision` as `status executed / executor_status closed / witness executor`, joined to `signal_id` by ticket, `closed_at` verbatim; state `logs/outcomes_mirrored.json` keyed by deal ticket prevents re-posts and a failed post is retried next run. Since platform v5.38 the ingest answers with `stored`/`skipped` counts; the tool reads them back, treats missing counts as UNKNOWN, and exits 1 on COUNT MISMATCH — "a push is not delivered until the receiver says what it stored."
evidence: brain/mirror_outcomes.py; brain/tests/test_mirror_outcomes.py; git 17a8a9f, ee19ffc

### exec_sl / exec_tp: the stops the executor actually sent
question: What are the exec_* keys and why are they absent rather than zero?
answer: Platform asks 3(b) and 5 (2026-09-15) wanted the SL/TP the executor SENT to MT5, not the brain's intent or the broker's fill. The executor's `/signal` response is journaled verbatim under `dispatch.response.result.summary`; `mirror_outcomes` appends `exec_sl`, `exec_tp`, `exec_entry_req`, `exec_lots`, `exec_order_type`, `exec_levels_source: executor_response_at_placement` to the close row, and the decision mirror carries the same keys on the executed decision row at placement so an OPEN position can be compared against `exec_sl` before any close exists. When no summary exists (refusals, dispatcher failures, older rows) the keys are omitted: "an absent key is UNKNOWN, never 0." `--exec-update` re-posts already-mirrored closes once with `exec_update: true`.
evidence: brain/mirror_outcomes.py `_placement_summary`, `build_outcome_payload`; brain/src/platform_mirror.py `_placement_levels`; git ee19ffc, c67f511, e795478

### Telegram notices showed "Grade —" and a logging bug hid exceptions
question: Why were two small notification bugs worth fixing?
answer: `fmt_approved` read grade from the opportunity top level, but v18 opportunities carry it in `context.market_snapshot`, so every approval post said "Grade —"; a fallback was added. In the BSv11 Telegram path loguru formats with `{}` not `%s`, so the old `%s`-style call logged the literal "%s" and dropped the exception name entirely; fixed to an f-string. Both are visibility fixes so the operator sees the truth.
evidence: brain/src/notify.py `fmt_approved` comment; brain/src/main.py `_post_telegram_v11` comment

### Dashboard health checks for a decommissioned Polymarket executor
question: Why did the dashboard show ERR for executor-pm and what was done?
answer: The Polymarket executor (May build) was decommissioned and its server deleted, but the dashboard still probed `executor-pm.signalmesh.dev/health` and its TLS cert, showing a permanent ERR. `patch_dashboard_remove_pm.py` removed the `SERVICES["executor_pm"]` entry and the `CERT_HOSTS` entry; the scanner tile is labeled "RETIRED — project closed".
evidence: dashboard/backend/patch_dashboard_remove_pm.py; dashboard/backend/main.py `/api/services`

### Stale Pine copy in the brain repo misled two sessions
question: Why was the Pine file deleted from brain/src/agents on 2026-08-19?
answer: A v18.7-era copy of the Pine script sat in the brain repo and two sessions mapped the system from it, drawing conclusions about code that had already been superseded (v18.12 changed pullback grading, the trend-trap veto, A+ direction awareness and more). It was removed with a pointer file naming the canonical source in `Sniper-System/pine/`, noting that `sabuj14eu/pinev18.6` is an empty repo, and that only the journal's `pine_ver` proves what is running.
evidence: brain/src/agents/PINE_SOURCE.md; docs/PINE_VS_BOT_MAP.md addendum

### Counting paper calls as Pine alerts produced two wrong readings
question: Why does check_pine_ver exclude session_caller rows by default?
answer: Two earlier alert-census readings ("US100 silent 70h", "GOLD silent 109h") were wrong because they counted session_caller paper rows, which wear a `pine_ver` field, as Pine alerts; the real figures were US100 with no genuine alert for 32 days and OANDA:XAUUSD 141.5h. `brain/tools/check_pine_ver.py` (2026-08-31) reads the schema from the code (pass-through keys land in `signal_raw.context.market_snapshot`), lists versions arriving, real Pine alerts per ticker with session_caller excluded, and silent tickers; `--all-sources` widens it. The retracted US10Y/US100 correlation is recorded as "a coincidence dressed as a cause."
evidence: brain/tools/check_pine_ver.py; docs/OPEN_ITEMS.md "ALERT CENSUS — 2026-08-31"

### Polymarket webhook needed auth because every hit spends council budget
question: How is /webhook/polymarket protected?
answer: Every accepted Polymarket hit spends council AI budget, so on 08-31 an env-gated header check was added (`PM_WEBHOOK_SECRET` → `X-PM-Secret`), backwards compatible when unset; on 2026-09-01 (B3) the same body-secret scheme as `/webhook/v18` was applied: a wrong secret is always 401 and a missing one is 401 when `BRAIN_REQUIRE_SECRET` is on.
evidence: brain/src/main.py `polymarket_webhook` comments "[08-31]" and "[B3 2026-09-01]"

### Executor /candles served the live, repainting bar
question: Why does /candles start at position 1?
answer: The scanner and market vision consumed candles from `copy_rates_from_pos(..., 0, n)`, which includes the still-forming bar that repaints. BOT-P0-3 changed the start to 1 so only CLOSED bars are served, and the response says `closed_only: true`. This matches the research law in the platform repo that research uses closed candles only.
evidence: executor_ic_markets/src/main.py `/candles` "[AUDIT BOT-P0-3] start=1: CLOSED bars only"

### Brain heartbeat and Git-to-Production identity
question: How can the platform tell whether the running code matches git?
answer: On 2026-09-01/02 the executor `/health` and the bias pusher's `brain_status` artifact gained `git_commit` (`git rev-parse --short HEAD`, or "untracked" — "an honest answer") and `service_version`, plus `pnl_pct_today` from MT5 deal history that is None on any doubt "so UNKNOWN stays None and is never faked to 0." The platform uses these for its Git<->Production MATCH light.
evidence: executor_ic_markets/src/main.py `_deploy_commit`, `_pnl_pct_today`; brain/push_bias.py `_deploy_commit`, `post_brain_status`; git c98e100
