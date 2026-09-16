---
title: Brother Sniper v7 — validated solutions from the repo history
domain: v7
repo: sabuj14eu/brother_sniper_v7
sources: patch_v7_atr_floor.py, patch_v7_bsv11.py, patch_entry_dist_atr.py, patch_freshness_gate.py, patch_mirror_close.py, patch_pine_structure.py, patch_truth_guards.py, patch_unverified_not_loss.py, patch_executor_positions.py, patch_webhook_header_secret.py, patch_dedup_symbol.py, patch_obs_identity.py, patch_v7_status_hooks.py, patch_iso01_identity.py, patch_iso02_balance_unknown.py, patch_v7_bot_iso03_24_heartbeat.py, patch_v7_bridge_iso03_05_16.py, patch_v7_bridge_iso06.py, patch_v7_bridge_iso06_box.py, patch_v7_bot_iso07_08.py, patch_v7_bot_attribution.py, deploy_windows.py, task8_patch.py, task8b_patch.py, bot.py, sniper_executor.py, core/ic_markets.py, core/sl_engine.py, core/v7_status.py, core/signal_memory.py, filters/ai_filter.py, filters/news_gate.py, risk/equity_guard.py, learning/trade_memory.py, learning/telemetry.py, learning/platform_mirror.py, auto_live.py, post_incident.py, docs/V7_AUDIT_2026-08-01.md, docs/OPEN_ITEMS.md, docs/STRATEGY_INTELLIGENCE.md, docs/PINE_UPDATE_NOTE.md, docs/SESSION_COORDINATION.md, docs/START_HERE.md, tests/audit/2026-09-05_iso02/PATCH_PROPOSAL_ISO02.md, tests/audit/2026-09-05_iso06/PROPOSAL_ISO06.md, git log
verified_on: 2026-09-16
classification: INTERNAL
---

### v7 rejected essentially every v18 scalp signal because of a legacy SL floor
question: Why did the v7 arm stop trading v18 signals in July 2026, and what fixed it?
answer: The trust-mode SL floor came from a legacy percent-of-price rule (~1.5%) designed for swing trades, while Pine v18.6 sends structural scalp stops already floored at 0.7 ATR. On SILVER the floor was 0.908 versus Pine's 0.3696 (4.7x live ATR), so the 1.6x widen-ratio guard rejected at 2.46x and the mechanical arm produced no evidence. Fix F9 (2026-07-10): in trust mode the floor is 1.2 x live M15 ATR (the ATR v7 fetches from the bridge), falling back to the legacy engine floor only when ATR is unavailable; the 1.6x widen-ratio guard is kept. SILVER example: floor 0.908 -> 0.231, Pine's stop passes verbatim.
evidence: patch_v7_atr_floor.py docstring; bot.py trust-mode block "[F9 2026-07-10]".

### Widened stops collapsed R:R into 0.63R live trades
question: Why is MIN_RR 1.0 and what is the widen-ratio guard?
answer: When the institutional engine widened Pine's stop for noise survival, TP stayed structural, so R:R collapsed and the bot was live-trading 0.63R setups that need a 61% win rate to break even. Fix F2 (2026-07-02): MIN_RR raised from 0.5 to 1.0 and a widen-ratio guard added — if the noise floor exceeds 1.6x Pine's stop, the setup Pine graded no longer exists at that stop and the signal is rejected instead of traded. TP inflation (rebuilding TP from Pine's ratio) had already been removed on 2026-06-25.
evidence: bot.py MIN_RR comment "[F2 2026-07-02]"; bot.py "[SL] widen-reject" branch; "TP-INFLATION REMOVED 2026-06-25".

### round(x, 2) corrupted 5-digit forex stops
question: Why does bot.py have _PX_DIGITS and round_px?
answer: Stops and breakeven prices were rounded to two decimals everywhere, so a EURUSD SL of 1.17345 became 1.17 (moved ~35 pips) in the trust+floor, regime-pad and breakeven paths. Fix F3 (2026-07-02): a per-symbol digits table (GOLD 2, SILVER 3, USDJPY 3, forex majors 5, indices 1) and round_px() used at every SL/BE computation in bot.py. Known residue G-1: core/sl_engine.py still does sl_final=round(sl_raw,2) on the institutional (non-trust) path, deliberately unfixed pending its own reviewed diff.
evidence: bot.py _PX_DIGITS comment "[F3 2026-07-02]"; docs/V7_AUDIT_2026-08-01.md Task 2 G-1.

### Indices were sized with GOLD's tick math
question: Why were US30/USTEC lot sizes arbitrary before July 2026?
answer: SAFE_SPECS and the client's spec table had no entry for US30/USTEC, so get_spec fell back to GOLD's tickSize/tickValue and lot sizing for indices was wrong; the generic 0.10 lot cap masked it. Fix F4 (2026-07-02): explicit index specs (US30 tickSize 1.0, USTEC 0.1, lotMin 0.10), DEMO_MAX_LOT entries and MIN_LOT 0.10 for index CFDs, and unknown symbols now return {} so the fallback is explicit. The $1/point/lot assumption is still marked VERIFY against the MT5 specification window.
evidence: bot.py SAFE_SPECS "[F4 2026-07-02]"; core/ic_markets.py fetch_symbol_spec and open_trade caps.

### The shadow-vote pipeline silently never saw v9 signals
question: Why was _grade defined before the BSv17/18 branch?
answer: `_grade` was only assigned inside the BSv17/BSv18 branch, so the later signal_bus emit raised a NameError for every v9 signal; the exception was swallowed and the shadow-vote pipeline silently recorded nothing for them. Fix F5 (2026-07-02): `_grade` is defined for ALL systems before the branch. The lesson is the "failed without an error" family the handover names.
evidence: bot.py comment "[F5 2026-07-02] defined for ALL systems".

### An LLM vote could override a news-flagged block
question: Can the AI eye ever rescue a trade blocked for news?
answer: No. F6 (2026-07-02) forbade the tiebreaker on news-flagged blocks because "trading into a high-impact window on LLM confidence is how soft filter becomes no filter". ISO-24 (2026-09-05) went further: the model vote is asked on any other rule block only so the journal can grade it, is recorded in breakdown["deepseek"] with shadow_only=True, and can never turn passed from False to True.
evidence: filters/ai_filter.py comments "[F6 2026-07-02]" and "[ISO-24 2026-09-05]"; tests/audit/2026-09-05_job9/test_job9_llm_override.py.

### Auto-fabricated stops were risk-sized on an invention
question: What happens when a Pine payload has no SL?
answer: Old behaviour invented a 1.5% (metals) / 3% (other) stop and then risk-sized the lot on that invention — "a fabricated plan, not a trade plan". Fix F7 (2026-07-02): a signal without SL is rejected with `signal carries no SL — auto-SL fabrication removed (F7)`; v18 Pine always sends a structural SL, so a signal without one is noise. A missing TP is still auto-filled at 3R.
evidence: bot.py "[GATE-SL]" block with the F7 comment.

### Counter-trend trades kept ~90% of their filter score
question: What is the F8 counter-trend penalty and the F8_CT_50 dial?
answer: The 10-point trend factor let a confirmed counter-trend signal keep about 90% of its AI-filter score, which arithmetically produced the SELL-side disease (SELL PF 0.54, WR ~19%). F8 (2026-07-02) multiplies the final score by 0.65 for confirmed counter-trend signals; aligned/range/unknown are untouched. An evidence-gated dial F8_CT_50=true (default off, 2026-08-01) tightens it to 0.50 once counter-trend trades since F8 still show PF < 0.9 at n >= 20.
evidence: filters/ai_filter.py F8 block; tests/test_v7_units.py::test_f8_dial_off_by_default / test_f8_dial_on.

### Sessions were mislabeled all summer by a static UTC table
question: How does v7 determine the trading session?
answer: The old session table was static UTC ("new_york" starting 16:00 UTC = noon in NY all summer), which mislabeled sessions, cluster keys and the Asia-bleed analysis. Fix F9 (2026-07-02): _get_session uses exchange time zones — LSE 08:00-16:30 Europe/London, NYSE 09:30-16:00 America/New_York, Tokyo 09:00-18:00 Asia/Tokyo — yielding overlap/london/new_york/asian/dead; the hour argument is kept for call compatibility but ignored. The platform later corrected NVDA tiers to America/New_York for the same reason.
evidence: filters/ai_filter.py _get_session; docs/UI_WORK_ORDER_2026-09-02.md platform reply A2.

### Trusted Pine stops were noise-tight and died on gold
question: Why is a trusted Pine SL floored at all?
answer: Trust mode originally accepted Pine's raw SL verbatim, producing noise-tight stops ("gold 2.5pt deaths"). Patch P0 (2026-06-18) floors the trusted stop at the engine's computed minimum and, at first, widened TP by the same ratio; TP scaling was then removed on 2026-06-25 because the real R:R must be measured by validate_rr and sub-MIN_RR trades correctly dropped. The metals MIN_SL_PCT floors were raised to 1.0% on 2026-06-26 on journal evidence (<1% stops bled -432 at 17% WR vs >1% +280 at 80% WR).
evidence: bot.py "Patch P0" comment; core/sl_engine.py MIN_SL_PCT comment.

### The webhook secret leaked into bot.log and git history
question: What was the H-0 secret leak and what changed?
answer: bot.py logged the raw payload AFTER injecting the secret, so WEBHOOK_SECRET went into bot.log and journalctl on every signal, and a committed journalctl dump carried it into git history. Fix (2026-08-01): the [WEBHOOK RAW] log line redacts `secret` as `***`, the dump file was deleted, and the rule became: ROTATE WEBHOOK_SECRET in .env, the TradingView alert JSON and the bridge env. The rotation remains an open item deferred while everything is DEMO.
evidence: docs/V7_AUDIT_2026-08-01.md H-0; bot.py "[HYGIENE 08-01] redact" comment; docs/OPEN_ITEMS.md A2.

### The repo could not run from a clean clone
question: Why was learning/*.py missing from git?
answer: `.gitignore` excluded `learning/` as a directory, which dropped the CODE modules (trade_memory, weight_engine, regime_detector, cluster_engine, signal_bus) along with the data, so every bot.py import failed on a fresh clone — the same class as the v18 P0-1 finding. Fix H-1 (2026-08-01): the 13 learning code modules were force-added; `*.jsonl` and state stay ignored.
evidence: docs/V7_AUDIT_2026-08-01.md H-1 and addendum "H-1 CLOSED"; git ls-files learning/*.py.

### The Windows bridge lived only on one machine
question: How did sniper_executor.py get into git?
answer: The v7 bridge (NSSM SniperExecutorV7) existed in no repository, so the Task-1 question about `price_current` could not be answered from code and the bridge could not be reviewed, diffed or restored. The audit ordered a one-file snapshot (copy to the box, `git add -f sniper_executor.py`); the repo now carries the bridge and every later fix (telemetry fields, A1, ISO-01/03/05/06/16) is applied to it, with pre-patch copies kept as evidence fixtures.
evidence: docs/V7_AUDIT_2026-08-01.md H-2; docs/STRATEGY_INTELLIGENCE.md "BLOCKER"; tests/audit/2026-09-04_job3/fixtures.

### "Breakeven fired: 0" while the log showed 33 breakeven lines
question: Why did the scorecard report zero breakevens?
answer: The monitor set tracked["be_done"] on the open slot, but mem_close never received it and clear_open_trade discarded it, so scorecard.py counted a field no producer emitted. The data verdict (2026-08-01): 23 of 47 studyable trades reached +1R and `grep -c "[BE]" logs/bot.log*` found 33 lines — detection worked, the journal did not. Fix: close_trade() accepts and writes be_done/partial_done (append-only) and both bot.py call sites pass them, proven by a round-trip test. Partial-close 0 remains by design (the `if False` [BE-ONLY] branch, disabled at 0.01 lots).
evidence: learning/trade_memory.py close_trade comment "[TASK-1 FIX]"; docs/V7_AUDIT_2026-08-01.md addendum.

### Widening stops does not rescue losing trades
question: Should v7 widen stops to reduce stop-outs?
answer: The MAE study (n=47) replayed closed trades at 1.0/1.2/1.5/2.0 x ATR: survival rose from 31.9% to 55.3% but decided-case average R stayed about -0.89 at every width and net R stayed deeply negative (-29R to -20R). Verdict: tight stops lose because they are attached to bad trades, so the levers are trade SELECTION (asset gate, counter-trend penalty), not stop width. Re-run at n >= 100.
evidence: docs/V7_AUDIT_2026-08-01.md addendum "MAE STUDY VERDICT"; mae_study.py.

### An asset can be benched or sized down without a code edit
question: How would GOLD be sized down or benched?
answer: utils/asset_gate.py (2026-08-01) reads ASSET_GATE_ENABLED / ASSET_GATE_DISABLE / ASSET_GATE_SIZE from .env; while disabled it always answers (False, 1.0). The multiplier is clamped <= 1.0 so it can never raise size (Iron Rule 7) and is applied AFTER the 0.3% effective-risk floor so a 0.5x dial actually halves risk. Evidence to flip: size-down GOLD:0.5 if GOLD PF < 0.9 at n >= 30 lifetime and last-30d net negative; bench if PF < 0.7 at n >= 30.
evidence: utils/asset_gate.py; bot.py "[ASSET-GATE 08-01]" hooks; tests/test_v7_units.py::test_asset_gate_*.

### entry_dist_atr was dropped on the floor
question: Why could setup_edge not cut by entry distance for v7?
answer: Pine v18.12 already emitted entry_dist_atr on every scalp payload but learning/telemetry.py had no such column, so v7 discarded it and the platform's paper lanes were the only population for the >3 ATR question. Fix (2026-08-21, anchor-safe patch): the column joined the market schema group and is captured verbatim on the open path and in capture_reject. Forward-only: the n >= 20-30 per-bucket clock started when it landed.
evidence: patch_entry_dist_atr.py; learning/telemetry.py schema comment; tests/test_entry_dist_atr.py.

### Opens and rejects reached the platform but closes never did
question: Why did /chart keep drawing a closed v7 trade's levels?
answer: The box's learning/platform_mirror.py already defined mirror_v7_close, but the box's bot.py never called it, so closes were never mirrored and the platform held levels until the 12 h TTL. Fix (2026-08-22): patch_mirror_close.py inserts the fire-and-forget call right after equity_guard.record_trade in the monitor close path, guarded so a failure cannot touch the close bookkeeping. Later append-only extensions: mae/mfe, and (2026-09-15) sl/tp1/raw_sl so the platform's hit-check can replay v7 prints.
evidence: patch_mirror_close.py; learning/platform_mirror.py mirror_v7_close; tests/test_mirror_close_levels.py; commit 634f381.

### Signal age was measured but never gated
question: What does the freshness gate do and why is it shadow?
answer: The autonomy order's stage 2 found that signal_age_seconds_v was measured at the decision site but nothing gated it. filters/freshness_gate.py (2026-08-22) introduces the state DECISION BLOCKED — DATA FRESHNESS (signal older than 900 s, or in v2 a material move > 1.5 ATR from the evaluated entry) and is wired immediately before Execute. Default mode is shadow (logs [FRESH-GATE SHADOW] and telemetry rejects tagged freshness_shadow, blocks nothing); V7_FRESHNESS_GATE=enforce is an explicit human decision after n >= 20 shadow reads. UNKNOWN inputs do not block in v1 by documented choice.
evidence: filters/freshness_gate.py; patch_freshness_gate.py; bot.py "[08-22 FRESHNESS GATE v1]"; tests/test_freshness_gate.py.

### The irrecoverable execution data was never being logged
question: Where do v7's spread, slippage and latency numbers come from?
answer: Stage 2 of Strategy Intelligence (2026-08-01) recognised that fill facts cannot be backfilled — every unlogged day is gone. The bridge now times the broker round-trip and returns requested_price, fill_price, slippage (positive = filled worse), bid, ask, spread, latency_ms and retcode in the /execute response; core/ic_markets.py passes them through returnData (it dropped them before); bot.py's guarded telemetry call records them into learning/telemetry.jsonl. The order request and order_send call stayed byte-identical.
evidence: docs/STRATEGY_INTELLIGENCE.md "Stage 2 COMPLETE"; sniper_executor.py "[TELEMETRY 08-01]"; core/ic_markets.py returnData loop.

### Every non-traded signal is now an observation
question: How are rejected signals captured and classified?
answer: Stage 3 (2026-08-01) added telemetry.capture_reject at the single /webhook choke point for every rejected/blocked/filtered/skipped/paused result, with the reason and the market context, so the nightly report can ask which rejection rules actually improve expectancy. Stage 8 added learning/strategy_dna.classify, tagging every signal S1 trend_continuation, S2 pullback_sniper, S3 breakout, S4 mean_reversion, S5 news_reaction or S0 unclassified from fields Pine already sends. Rejected signals were later also stamped with pine_ver (2026-08-29) after the audit found them unstamped.
evidence: bot.py "[REJECT-TELEMETRY 08-01]"; learning/strategy_dna.py; docs/PINE_UPDATE_NOTE.md "BOT-SIDE WORK"; tests/test_strategy_dna.py.

### An executor error reply parsed as "no open positions"
question: What is the positions-shape truth guard?
answer: A 500 JSON or any body without a `positions` key used to parse as an empty position list, so every tracked trade looked closed. Since 2026-08-31 the monitor skips the cycle with "positions UNKNOWN (HTTP <code>) — closed!=unreachable" whenever the status is not 200 or the key is absent. UNKNOWN is not FLAT.
evidence: patch_truth_guards.py item 1; bot.py monitor "[MON] positions UNKNOWN".

### A ticket missing from history was journaled as a $0 loss
question: What happens when a position vanishes from /positions and is not in /history?
answer: Previously it was journaled as a $0 close at entry, which fed the consecutive-loss pause while the real position stayed open at the broker. Since 2026-08-31 the slot is held for 10 monitor cycles ("holding slot, not closing"); only then a LOUD UNVERIFIED fallback close fires with a Telegram "VERIFY AT BROKER". Round 2 (2026-09-02) fixed the remainder: the UNVERIFIED close counts neither as a loss nor a streak increment (tag "UNVERIFIED"), because an UNKNOWN outcome must never feed the loss streak. The order asked for "retry forever"; the shipped guard retries 10 cycles then closes loudly, on purpose.
evidence: patch_truth_guards.py item 2; patch_unverified_not_loss.py; tests/test_round2_guards.py::test_a1_unverified_close_increments_no_loss; docs/OPEN_ITEMS.md A1.

### X-Forwarded-For was trusted from anyone
question: How does the webhook IP allowlist treat proxies?
answer: The before_request guard read X-Forwarded-For first, so any client could spoof a TradingView address. Since 2026-08-31 the header is honoured only when the connection itself comes from loopback (our own nginx); direct hits are judged by their real address. The secret auto-injection for Pine systems therefore now sits behind a real IP check; deleting the injection outright would cut off every mirrored Pine alert (round-1 refusal, correct).
evidence: patch_truth_guards.py item 3; bot.py _guard "[TRUTH-GUARD 08-31]"; docs/OPEN_ITEMS.md A2.

### The bridge answered count:0 with HTTP 200 while MT5 was disconnected
question: Why does /positions return 503 now?
answer: ensure_mt5()'s result was ignored and a disconnected MT5 made positions_get() return None, which was served as {"count":0} with HTTP 200 — the bot mistook every tracked trade for closed and produced fake $0 losses and self-pauses. Fix A1 (2026-08-31, Windows): /positions answers 503 "mt5 disconnected" or "positions_get None (mt5 not ready)". Deployed 2026-09-02 via deploy_windows.py with backup .bak.<timestamp>; acceptance is the next MT5 hiccup showing "positions UNKNOWN (HTTP 503)" in the v7 log.
evidence: patch_executor_positions.py; deploy_windows.py; sniper_executor.py /positions; docs/OPEN_ITEMS.md "WINDOWS DEPLOY — COMPLETED 2026-09-02".

### The nginx mirror cannot put the secret in the body
question: What is the A2 header-carried secret?
answer: A mirrored request body cannot be rewritten, which is why bot.py auto-injects WEBHOOK_SECRET for trusted Pine systems — and why anything on loopback could post a Pine-shaped body and be trusted. Round 3 (2026-09-02) taught /webhook to fill a MISSING payload secret from the X-Webhook-Secret header (never overriding a body secret; handle_signal remains the single check point), shipped dark. Step 1 is one nginx line on the brain box (proxy_set_header X-Webhook-Secret); step 3, after a day of "[A2] secret from header" lines, removes the auto-injection and rotates the secret.
evidence: patch_webhook_header_secret.py; bot.py _header_secret; docs/A2_NGINX_MIRROR_SECRET.md; tests/test_round3_a2_incident.py::test_a2_*.

### Two symbols on the same bar collided on one Pine id
question: What is the v7 dedupe key and why does it carry the symbol?
answer: The auditor claimed GOLD and SILVER firing the same bar collided; the first reply refuted it from a truncated read (the sha256 fallback contains the symbol) and missed bot.py:285, where a payload's raw Pine signal_id is used directly — and Pine ids like SS-BUY-<ts> carry no symbol. Fixed test-first (C1, 2026-09-02): the key is `symbol:signal_id`; two symbols with the same id both trade, a same-symbol duplicate is still refused, the fallback is unchanged. Lesson recorded: never refute from a partial read.
evidence: patch_dedup_symbol.py; bot.py _make_sid "[C1 2026-09-02]"; tests/test_round2_guards.py::test_c1_two_symbols_same_pine_id_both_trade; docs/OPEN_ITEMS.md ROUND 2 item 1.

### Every historical htf_agree=False was untrustworthy
question: Which field carries Pine's higher-timeframe alignment?
answer: Pine emits htf_align (verified in v18.13 source; htf_agree appears nowhere), but core/signal_memory.py read htf_agree, so the stored value was always False. Fix C2 (2026-09-01, test-first): read htf_align with an htf_agree fallback. Analytics must treat every historical htf_agree=False as unknown, not as a counter-trend fact.
evidence: core/signal_memory.py "[C2 2026-09-01]"; tests/test_signal_memory_htf.py; docs/OPEN_ITEMS.md C2.

### The DD guard claimed 20% while configured at 99%
question: Why does the equity guard warn "DD guard effectively OFF"?
answer: risk/equity_guard.py sets daily/weekly/total DD limits to 0.99 (99% of balance), but the block comment still said "Total DD 20pct" and the block message printed the wrong number. A6 (2026-09-01) fixed the message truth only: the block reason prints the real limit and a loud startup line records "DD guard effectively OFF (99%) — demo decision". No number changed; real limits ship only on Shyam's explicit words (decision card 2).
evidence: risk/equity_guard.py "[A6 2026-09-01]"; docs/OPEN_ITEMS.md A6; docs/V7_AUTONOMY_PLAN.md decision cards.

### Pine's v18.13 structure field would have been discarded
question: What is pine_structure and why was it added before the Pine release?
answer: Pine v18.13 appends "structure" ("HH/HL" | "LH/LL" | "MIXED"), the same three words auto-live-v1 emits, which makes the Pine/bot agreement cut a direct join instead of an inference (it was CANNOT SEPARATE at n=7/14). Without a column v7 would receive and throw the value away, leaving the cut unmeasurable forever. Fix (2026-08-29): a pine_structure telemetry column captured verbatim on the open path (patch_pine_structure.py) and the reject path; log-only, the trade is already placed when it runs.
evidence: patch_pine_structure.py; learning/telemetry.py structure group; docs/PINE_UPDATE_NOTE.md.

### Asking Pine for pine_version would have created two version keys
question: Which key stamps the Pine version on a payload?
answer: The bot side asked for a new pine_version field from grepping v7's reader instead of the payload; the Pine session corrected it: the key is pine_ver, present since v18.8, and v7 has stored payload.get("pine_ver") into the telemetry column pine_version all along. A second version key was refused because two version keys eventually disagree and then neither can be trusted. Analytics group by pine_ver; only pre-v18.8 signals are genuinely unstamped.
evidence: docs/PINE_UPDATE_NOTE.md "CORRECTION ACCEPTED (2026-08-31)"; bot.py telemetry pine_version=payload.get("pine_ver").

### "v7 DOWN 79880s" was a missing organ, not a dead bot
question: Why did the platform show v7 down while it was trading?
answer: The box ran the trade-desk branch (which carries core/v7_status.py with the heartbeat and decision hooks) until 2026-09-01; moving it onto the deploy branch and restarting dropped both emitters, so the platform's last heartbeat was the restart moment while the bot kept trading (W86/L95). Fix (round 4, 2026-09-03): core/v7_status.py and its tests ported verbatim, _push accepts either env pair, and patch_v7_status_hooks.py restored the two guarded hooks — update_heartbeat after the SLOT-RECON sweep and record_decision after reject telemetry. Proof: platform card "last heartbeat <300s ago" and no "[V7-STATUS] ... skipped" in bot.log.
evidence: patch_v7_status_hooks.py; commit c1618f5; tests/test_v7_status.py, tests/test_v7_status_hooks.py; docs/OPEN_ITEMS.md ROUND 4.

### Two v7 emitters post under two id namespaces
question: Why can a live v7 trade look "missing" on the platform?
answer: core/v7_status.record_decision posts the RAW Pine id to /webhooks/brain/decision, while learning/platform_mirror posts `v7-<id>` to /webhooks/brain/signal; the signals table's v7- rows came from a backfill. A query for one namespace can "prove" a live trade is missing when it sits under the other — exactly what two "never arrived" ids looked like. Standing rule: search BOTH namespaces (signal_id LIKE '%<id>%'), and at convergence pick ONE emitter and ONE namespace (recommended v7-<pine_signal_id>) — never fix it by adding the second emitter.
evidence: docs/SESSION_COORDINATION.md "FORKED CONTRACT"; docs/OPEN_ITEMS.md ROUND 4 NOTE.

### Live state files kept the box off origin/main
question: Why are state.json and signal_memory.json untracked?
answer: Tracking live mutable state (state.json, signal_memory.json, governance/discipline_state.json) meant a git pull would overwrite live memory, so the box could never sit on origin/main and the platform's Git<->Production light stayed honest-red forever. Fix (2026-09-01, commit f76ba28): those files are untracked and gitignored; the repo keeps only the static backup snapshot signal_memory_backup_20260430.json.
evidence: .gitignore "[MATCH 2026-09-02]" block; git log f76ba28.

### The platform could not tell what commit a box was running
question: What are git_commit and service_version in /health?
answer: Both the bot and the bridge read `git rev-parse --short HEAD` once at start and expose git_commit plus service_version ("v7-bot", "sniper-executor-v7") in /health, powering the platform's Git<->Production MATCH light. For the bridge, which runs as a loose copy in C:\Users\Administrator, "untracked" is the HONEST reading until the service is repointed at the clone.
evidence: patch_obs_identity.py; bot.py _deploy_commit; sniper_executor.py "[OBS 2026-09-02]".

### A bare "-> 200" hid a platform refusal
question: How does post_incident.py handle the platform's status contract?
answer: The platform (contract v5.04) lets an agent report only INVESTIGATING or PATCH_PROPOSED; RESOLVED is refused with a reason while the fields still save, so "posted INC-0001 -> 200 (--status resolved)" saved evidence but did not resolve anything. The poster now normalizes to the contract, refuses "resolved" at argparse, sends BOTH incident_id and public_id (works on platform <5.04 and >=5.04), and prints the board's status plus any refusal.
evidence: post_incident.py STATUS_MAP and report_reply; tests/test_round3_a2_incident.py::test_incident_*; docs/OPEN_ITEMS.md ROUND 3 item 2.

### The bridge attached to whatever account the terminal held
question: What is ISO-01 and how does the bridge assert its account?
answer: sniper_executor.py initialised MT5 by terminal PATH with no login and no identity check, so a terminal logged into 52901228 (the v18 account) would take v7 orders. Fix ISO-01 (2026-09-04/05): V7_MT5_LOGIN is the one account the bridge may touch; ensure_mt5() returns False when it is unset or the terminal holds another login, and then every order route and /health answer 503. Deployed on the box (backup .bak.20260905_000815), /health 200 on the asserted account; missing env = NOT RUNNABLE, never a default.
evidence: patch_iso01_identity.py; sniper_executor.py _identity_ok; tests/audit/2026-09-04_job3/test_v7_iso01_patch_golden.py; docs/OPEN_ITEMS.md 2026-09-05.

### An unreadable balance became 1000.0 and sized a lot
question: What is ISO-02 and what does get_balance return when the bridge is down?
answer: core/ic_markets.py returned float(r.json().get("balance", 1000.0)) regardless of status and ACCOUNT_BALANCE (6000.0 on the box) on any exception, and bot.py had five `except: bal=1000.0` sites; the fabricated number passed the margin gate, moved the equity guard's peak and fed calc_lot (which is linear in balance). Fix ISO-02 (2026-09-05, 15 hunks over 3 files): get_balance returns None unless 200 with a balance field; EquityGuard.check(None) blocks BEFORE update_balance touches state (W2-02 ordering); update_balance(None) is a no-op; /health is degraded/503 with balance_state UNKNOWN; /recalibrate 503; calibration skips; Telegram says UNKNOWN. ACCOUNT_BALANCE is dead config.
evidence: patch_iso02_balance_unknown.py; tests/audit/2026-09-05_iso02/PATCH_PROPOSAL_ISO02.md; core/ic_markets.py get_balance; risk/equity_guard.py check.

### Orders carried no account and no magic
question: What do ISO-03 and ISO-05 enforce on the bridge?
answer: /execute had no account field and orders carried magic 0, so the reconciler, the platform and /close /modify could not tell v7's positions from anyone else's, and /close and /modify acted on any ticket. Fix (2026-09-05): the bot sends account_id=V7_MT5_LOGIN with every order (empty env -> the bridge answers 400 no_account_id, fail closed); the bridge refuses a mismatch with 403 account_mismatch and stamps magic V7_MAGIC_NUMBER (70007); /close and /modify refuse positions that are not v7's (403 not_ours), where "ours" is magic 70007 or a legacy BS_ comment so pre-ISO positions stay manageable.
evidence: patch_v7_bot_iso03_24_heartbeat.py; patch_v7_bridge_iso03_05_16.py; sniper_executor.py _is_ours and /execute; tests/audit/2026-09-05_iso03.

### The same signal POSTed twice was two fills
question: What is ISO-06 bridge idempotency?
answer: /execute had no memory of what it had placed; dedupe existed only in the bot process, so an nginx retry, a bot restart mid-request or a replayed webhook meant two fills. Fix ISO-06 (2026-09-15, ADR-004): an (account_id, signal_id) JSON store (V7_SEEN_FILE, TTL 6 h) marked immediately BEFORE order_send — duplicate 409 duplicate_signal, definitive broker rejection frees the id, None result kept as ambiguous, no signal_id 400, unreadable store 503; the accepted path is byte-identical. The generic script aborted on the box's A1-patched import line and wrote nothing, so a box variant anchored on the box shape was shipped and deployed (backup .bak.20260915_171729).
evidence: tests/audit/2026-09-05_iso06/PROPOSAL_ISO06.md; patch_v7_bridge_iso06.py; patch_v7_bridge_iso06_box.py; tests/audit/2026-09-15_p1_v7/test_deploy_p1_v7_golden.py.

### The equity state and dedupe memory carried no account
question: What are ISO-07 and ISO-08?
answer: A state.json carried to another account could hide or unblock a signal there, and a persisted EquityState could describe another arm's day. Fix (2026-09-15): EquityState.account is stamped from V7_MT5_LOGIN and a persisted state naming another account hard-stops the guard with counters kept (never reset = never widened); the persisted dedupe key becomes "<V7_MT5_LOGIN>:<symbol:signal_id>" while _make_sid is unchanged. Known one-time effect: keys already in state.json keep their old shape, so a signal seen in the last SIGNAL_DEDUP_MIN minutes before the restart is not recognised once. Deployed on Contabo by git, not patch script.
evidence: patch_v7_bot_iso07_08.py; risk/equity_guard.py "[ISO-07]"; bot.py _seen_key "[ISO-08]"; tests/audit/2026-09-04_job3/test_v7_guards_per_process.py.

### There was no way to stop both executors at once
question: What is the ISO-16 global stop?
answer: ONE shared witness file (GLOBAL_STOP_FILE, default C:\brotherbot\GLOBAL_STOP) is read by both executors before every new order: present = STOP, absent = CLEAR, unreadable = UNKNOWN treated as STOP. POST /admin/halt with X-Admin-Token == ADMIN_HALT_TOKEN engages it (appends a timestamped reason line); /admin/status and /health report it; closes are NOT blocked by the stop. Identical logic lives in the v18 executor (ADR-008).
evidence: sniper_executor.py _global_stop_*; tests/audit/2026-09-05_iso16/test_iso16_global_stop_v7.py; commit f8aaf5f.

### The heartbeat said which account it was CONFIGURED for, not measured
question: How does the v7 heartbeat prove its account and demo mode?
answer: The platform (v5.25.4) required account_login and trade_mode in the v7 heartbeat, measured, or it labels the account CONFIGURED LABEL. Fix (2026-09-05): the bridge /health gained trade_mode (MT5 account_info().trade_mode: 0 demo, 1 contest, 2 real); ICMarketsClient.get_account() reads login/trade_mode/balance from /health, returning None on 503, missing account or exception; build_heartbeat carries both keys and drops them when UNKNOWN. Append-only, display-only, no risk number.
evidence: core/ic_markets.py get_account; core/v7_status.py build_heartbeat; tests/audit/2026-09-05_heartbeat/test_heartbeat_identity_fields.py; commit 193906c.

### A broker row could not be joined to its decision
question: What is broker_comment and decision_id?
answer: The bot's tracked comment is "BS_<full signal_id>", but the bridge stamps the MT5 order comment "BS_" + md5(signal_id)[:8], a different string the platform's reporter actually sees; the slot's "comment" carried the wrong one under that name. Fix V7ATTR01 (2026-09-05/15): every open slot in the heartbeat carries signal_id and broker_comment computed by the bridge formula (None when there is no signal_id, never a hash of "None"); decision records carry broker_comment at placement and a deterministic decision_id = sha256(account:signal_id:status:msg:ts)[:16] — same evaluation re-posted keeps its id, a second evaluation gets a new one. A test pins the bridge source to the same formula.
evidence: core/v7_status.py broker_comment and build_decision; patch_v7_bot_attribution.py; tests/test_broker_comment.py.

### A dead news feed read as "clear"
question: How does NEWS01 stop a missing calendar from passing trades?
answer: The old fetch_news returned the cache on any failure and the cache starts empty, so a dead feed, a 429, DNS failure or the first signal after a restart all read as clear. NEWS01 (2026-09-15) makes the gate three-state with two witnesses: v7's own ForexFactory reading (UNKNOWN if never fetched, empty week, or older than its max age) combined with the platform's GET /api/v1/news/state (asked every signal, expiry honoured); CLEAR only when both are CLEAR, BLOCK if either, else UNKNOWN which blocks. Every blocking message contains "News" so classify_gate files it under GATE-NEWS; the 30/45-minute window rule is unchanged.
evidence: filters/news_gate.py; bot.py is_news_blocking; commit 2229753; tests/test_news_gate.py (24+ tests).

### A refetch TTL was mistaken for a max age
question: How long may v7's own last-good calendar reading stand?
answer: The first NEWS01 cut used the 600 s refetch interval as the own-reading max age, but 600 s was only how often the feed is re-asked (the old gate had no max age at all). Fix (2026-09-15, commit e349749): a last-good reading that a failed re-ask leaves standing is valid for at most 3 h — the platform's FEED_MAX_AGE_H for the same calendar — so both witnesses judge staleness under one law; V7_NEWS_OWN_MAX_AGE_S overrides as an explicit human decision. Tests pin the boundary and the override.
evidence: filters/news_gate.py OWN_MAX_AGE_S; commit e349749; tests/test_news_gate.py::test_wiring_a_failed_refetch_keeps_the_last_good_reading_until_it_ages_out.

### The news gate blocks nothing in observe mode but measures everything
question: What does V7_NEWS_GATE=observe do?
answer: Shyam's decision on 2026-09-16 ("the bot should be intelligent, not a sleeper"): v7 trades through high-impact news on the DEMO account so its behaviour there can be measured. In observe mode is_news_blocking still computes the three-state, two-witness verdict on every signal; the call site logs [NEWS OBSERVE] and lets the trade proceed while writing the verdict to telemetry as news_observe, joined to the outcome by signal_id, so after n >= 20 news-window trades the gate can be judged by numbers. The AI filter still scores news minutes; enforce/shadow are unchanged; the code default stays enforce.
evidence: bot.py Priority 2 observe branch; filters/news_gate.py MODES; commit f7cacfd; tests/test_news_gate.py::test_call_site_observe_branch_trades_through_and_records_the_verdict.

### Armed auto_live payloads were rejected by v7's own webhook
question: Why does auto_live add the secret only at POST time?
answer: During verification (not in the external review) auto_live's armed payloads were found to be rejected because they carried no secret and AUTOLIVE is not in the auto-inject trust list. Fix (2026-09-01): the secret is added at POST time only, and a test pins that it never reaches the dry-run log.
evidence: auto_live.py; tests/test_auto_live.py::test_secret_never_reaches_the_dry_log; docs/V7_AUTONOMY_PLAN.md external review table.

### auto_live keyed NVDA records by the broker name
question: How does auto_live handle a symbol whose broker name differs from its canonical name?
answer: The single NVDA dry run keyed its own journal by the broker name NVDA.NAS-24, which would have split the population when compared with the platform's canonical NVDA rows. Fix (2026-09-02, commit aa16bca): AUTO_LIVE_SYMBOLS accepts "CANON=BROKER" (e.g. NVDA=NVDA.NAS-24); the canonical name keys every record and signal_id, the broker name goes on the wire only and is kept as broker_symbol (append-only). Rows written before the fix stay as they are, dated, and are excluded by key when populations are compared.
evidence: auto_live.py split_symbol_spec; tests/test_auto_live.py::test_records_key_by_canonical_and_wire_by_broker; docs/OPEN_ITEMS.md NVDA PHASE 1.

### NVDA must stay shadow-only in v7
question: How is it guaranteed that v7 cannot trade NVDA yet?
answer: NVDA is deliberately absent from bot.py SYMBOL_MAP, so a mirrored NVDA alert reaches the `unsupported` gate before any trading logic; a test pins both facts (NVDA not a v7 symbol; the unsupported gate precedes trading). Phase 1 collection therefore runs through four collectors (Pine alert in the brain's ShadowGate, reporter candles aliased at the platform door, platform paper lanes, auto_live in shadow) with nothing able to trade it.
evidence: tests/test_shadow_symbols.py; docs/OPEN_ITEMS.md "QUEUED ORGAN — NVDA".

### BSv11 (LITE v11) alerts were not trusted
question: How was BSv11 added as a trusted system?
answer: Two two-string edits with no logic change: "BSv11" added to the secret auto-inject list and "BSV11" to the trust-mode list, so v7 accepts BSv11 alerts (direct or via relay) and honours Pine's own laddered SL in trust mode instead of rebuilding it. Inert until a payload with system=="BSv11" arrives; the patch backs up bot.py and aborts on any anchor mismatch.
evidence: patch_v7_bsv11.py; bot.py trust list ("BSV17","BSV18","BSV11").

### One open trade at a time became four asset-class slots
question: How does v7 hold concurrent positions?
answer: Task 8 refactored state["open_trade"] (single) into state["open_trades"], a dict keyed by asset class — metals / crypto / forex / other — with migration of existing state.json on first load, and updated the monitor loop, orphan recovery, signal gate, close handler and /health. It also added journal fields (asset_class, breakout_prob/strength/dir, hold_time_seconds, spread_at_entry, dxy_value, usdjpy_direction, signal_age_bars, regime, mae, mfe); Task 8B wired breakout fields, regime and signal age into TradeRecord and fixed the _shutdown_event typo in gunicorn.conf.py. The patch scripts were atomic: syntax-validated before writing, with a rollback command printed.
evidence: task8_patch.py; task8b_patch.py; bot.py ASSET_SLOTS and asset_class().

### A placement timeout is not a failed order
question: What is the RECONCILE branch and SLOT-RECON adoption?
answer: An exception during open_trade (e.g. a 15 s timeout) does not mean the order failed ("timeout-lies"). The RECONCILE branch sleeps 2 s, reads /positions, and if a position with comment BS_<sid> exists it adopts it into the free slot (Telegram "RECOVERED — order had landed"), flags extras as RECOVERY_CONFLICT, or alerts ORDER STATUS UNKNOWN if the check itself fails. Independently, the monitor's [SLOT-RECON] sweep adopts any untracked BS_ position into a free slot as ADOPTED_<ticket> every cycle. Finding H-3 noted adopted direction comes from the bridge's `type` field, which the repo bridge sends as "BUY"/"SELL".
evidence: bot.py RECONCILE and [SLOT-RECON] blocks; sniper_executor.py /positions type mapping.

### Pine template applied to the wrong chart
question: What is the GATE-PRICE entry sanity check?
answer: A Gold alert template firing on a GBPUSD chart sends a forex-priced entry under the GOLD symbol. Patch G rejects any entry outside a per-symbol plausible range (GOLD 1000-10000, SILVER 5-500, BITCOIN 1000-1000000, USDJPY 50-500, EURUSD 0.5-3.0, US30 20000-60000, USTEC 10000-50000, ...) with "likely Pine template applied to wrong chart". A sibling check DIR-FLIP rejects a BUY whose SL is above entry or TP below it (and the SELL mirror) as a Pine bug rather than auto-flipping.
evidence: bot.py _PRICE_RANGES "[GATE-PRICE]" and "[DIR-FLIP]" blocks.

### The margin gate runs before the AI filter to avoid spending on dead signals
question: Why is GATE-MARGIN placed before score_signal?
answer: A signal that cannot be traded (balance unreadable or below MARGIN_FLOOR 500.0) should not spend an LLM call or any scoring. The gate is fail-closed: `_bal_gate is None or < 500` skips the signal before Priority 1, and the measured value is reused by the equity guard and sizing instead of being re-fetched (ISO-02 removed the re-fetch-and-default).
evidence: bot.py "GATE-MARGIN (fail-closed)" block; tests/audit/2026-09-04_job3/test_v7_fabricated_balance.py::test_golden_ISO02c_unknown_balance_stops_at_the_margin_gate.

### SILVER and US100 went silent because Pine threw a calculation error
question: Why did SILVER stay silent 3 days and US100 5 days in late August 2026?
answer: The Market Radar showed the silence; Shyam then saw a CALCULATION ERROR on the SILVER/US100/GOLD charts. A Pine script that throws a runtime error stops executing on that symbol and never reaches alert(), so nothing was sent and the bot-side bias push was never broken. Root cause (Pine session): three request.security_lower_tf calls from the v18.12 F3 DXY squelch blew the per-study memory limit on the heaviest 24h symbols. Fix the error first, then the alert ceremony; every other Pine change is secondary.
evidence: docs/PINE_UPDATE_NOTE.md; docs/V7_AUTONOMY_PLAN.md "Findings from the first radar read".

### The Windows VPS had no git, so a script carried the fixes
question: How were A1 and B5 deployed to a box without a repository?
answer: Test-Path .git was False for both service folders, so the git-pull ceremony could not apply. deploy_windows.py carries both fixes itself — A1 (v7 /positions 503 when MT5 is down) and B5 (the v18 /candles two-witness clock with clock_witness.py) — and applies each with backup -> unique anchor or ABORT -> edit -> compile -> restore on fail; idempotent (second run says ALREADY), --dry-run supported. Before touching anything, the v18 executor's four locally-modified files were snapshot-committed as 1baa72a so the box's unique work is rollbackable; that snapshot still has no off-box copy.
evidence: deploy_windows.py; docs/OPEN_ITEMS.md "WINDOWS DEPLOY — COMPLETED 2026-09-02".

### An alias pointed at a symbol the terminal does not list
question: What is the "probe before trusting an alias" lesson?
answer: The bridge alias DXY -> USDX pointed at a name the MT5 terminal does not list, so every read failed invisibly — the same shape as RIPPLE dying at MT5. The rule: an alias is a claim about a name existing somewhere else and nothing checks it until something tries; probe end to end (probe_symbols.py for candles, symbol_info on the terminal for specs) before enabling. The US30/USTEC bridge-400 item was settled the same way, and the ruling for the platform is to request USTEC for bridge reads since the bridge map has no US100 entry.
evidence: docs/START_HERE.md lesson 1; probe_symbols.py; docs/V7_AUTONOMY_PLAN.md "Bot-side rulings".

### The candle reporter was believed unversioned
question: Is the MT5 reporter in git?
answer: The 08-19 note said the reporter existed in no repository and every change to it was a deploy with no rollback; that was true when written. Corrected 2026-09-02 (measured in git): the reporter IS versioned at Sniper-System/agents/mt5_reporter/mt5_reporter.py (REPORTER_VERSION 1.6.0, committed 2026-08-22). What remains unversioned is whatever C:\brotherbot\mt5_reporter.py runs if it differs — Get-FileHash both before trusting either. A partial read caused the wrong warning, the same lesson as C1.
evidence: docs/SESSION_COORDINATION.md "CORRECTION 2026-09-02".

### Two launchers spawned two reporter writers
question: Why must the Windows reporter have exactly one launcher?
answer: The platform's service map said the reporter's NSSM service was removed on 08-08 and a Scheduled Task launches it, while the box showed BrotherBotReporter as an NSSM service that attaches fine; the four August orphan processes were most likely the Scheduled Task's instances, and the next reboot would spawn a second writer of the heartbeat row again. Rule (round 4): measure, disable the task, keep NSSM, correct the map; "two writers, one row" is a fault of its own.
evidence: docs/OPEN_ITEMS.md ROUND 4 "PERMANENT ONE-LAUNCHER RULE"; docs/UI_WORK_ORDER_2026-09-02.md B9.

### Proposal test modules collided across audit directories
question: Why are proposal hunk modules named proposal_hunks_isoNN?
answer: Two proposal directories each shipped a module named the same way, so pytest could not collect both in one run. Commit 0d1a2a5 gave each a unique name (proposal_hunks_iso06 etc.), and FakeMT5 in the audit fixtures gained shutdown() and honour_login so the cross-arm ISO-09 golden test in brother-developer could reuse it.
evidence: git log 0d1a2a5, eef7c1b; tests/audit/2026-09-05_iso06/proposal_hunks_iso06.py.
