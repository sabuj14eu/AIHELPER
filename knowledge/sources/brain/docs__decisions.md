---
title: v18 brain decisions log
domain: brain
repo: sabuj14eu/brother-brain-v2
sources: docs/decisions.md
verified_on: 2026-09-16
commit: 0f8f49d
classification: INTERNAL
---

# Brother v18 — Architecture Decisions

## 2026-05-13 — Sandbox: Monte Carlo, not MiroFish

**Decision:** v18 uses the in-process Monte Carlo sandbox
(`src/sandbox/mirofish.py::_monte_carlo_fallback`) as the canonical
pre-trade simulation. MiroFish-Offline is NOT installed.

**Why:**
- Brain server is 11 GiB RAM, 0 GB swap, no GPU. Cannot host
  Ollama running qwen2.5:14b/32b without OOM-killing the Brain.
- MiroFish was designed for slow qualitative sentiment simulation
  (hours per run, document-driven). Pre-trade risk needs sub-second
  probability distributions. Monte Carlo over Quant's CI is the
  right primitive for that.
- Adding MiroFish before v18 has proven profitable is premature
  optimization.

**Revisit when:**
- v18 has 3+ months live PnL data and we can show MiroFish-style
  sentiment would have changed outcomes, OR
- We provision a separate GPU box for sentiment and call it as a
  remote service from Brain.

**Code state:**
- `_run_mirofish()` is preserved in `mirofish.py` for future re-enabling
- `MIROFISH_PATH` is blanked in `.env`
- `MIROFISH_NUM_AGENTS / RUNS / CONFIDENCE_THRESHOLD` env vars are
  dead config; harmless, can be deleted in cleanup.

## 2026-05-13 evening — Brain as systemd service

**Decision:** Brain runs as a systemd unit (`brother-brain.service`), not a
manually-launched foreground process.

**Config:**
- Unit file: `/etc/systemd/system/brother-brain.service`
- Restart policy: on-failure, 10s delay, max 5 restarts per 5min window
- Hardening: NoNewPrivileges, ProtectSystem=strict, ProtectHome=read-only,
  ReadWritePaths limited to logs/ and /tmp
- Auto-starts on boot (WantedBy=multi-user.target)

**Operator commands:**
- Status:  `sudo systemctl status brother-brain`
- Restart: `sudo systemctl restart brother-brain` (use after code changes)
- Stop:    `sudo systemctl stop brother-brain`
- Logs:    `sudo journalctl -u brother-brain -f` (follow live)

**Known weakness — Researcher retry uses same max_tokens that just failed.**
Bumped default from 4000 to 8000 as workaround. Real fix is to retry with
1.5x tokens, or split Researcher into search-pass + format-pass. Deferred.

## Open items for next session

1. nginx + Let's Encrypt TLS for public HTTPS endpoint
2. Confirm/acquire domain name pointing to Contabo public IP
3. TradingView IP allowlist on the public endpoint (firewall)
4. Re-route v18 Pine alerts from old demo bot → Brain
5. Decision-journal log format (structured JSON per signal evaluated)
6. Positive-edge fixture to exercise DevilsAdvocate → RiskManager → Executor

## 2026-05-20 evening — Public HTTPS endpoint live

**Domain:** `signalmesh.dev` (Cloudflare Registrar, auto-renew on, WHOIS-privacy on)
**A records:** `brain | api | bot | status . signalmesh.dev` → `62.171.164.19` (gray cloud, no proxy)
**Cert:** Let's Encrypt for `brain.signalmesh.dev`, valid through 2026-08-18, auto-renewal via `certbot.timer`
**Nginx config:** `/etc/nginx/sites-available/brain.signalmesh.dev`, proxies to 127.0.0.1:8443
**Public URL:** `https://brain.signalmesh.dev/health` returns Brain JSON ✅

**Coexisting:** Old demo bot at `62.171.164.19.nip.io` (sniper-bot.service, port 5000)
left untouched — preserves XTB/IC Markets demo data collection.

**Observation from demo bot at time of Brain go-live:**
50 trades, 64% win rate, avg_win $14.58, avg_loss -$26.50, expectancy -$0.21/trade.
Net-negative EV from R:R imbalance, NOT from bad entries. This is the failure
mode Brain v2's Quant agent is designed to catch upfront.

## Open items for next session

1. TradingView IP allowlist on nginx (deny all other source IPs to /webhook/*)
2. Decision-journal log format (structured JSON per signal evaluated)
3. v18 Pine alert: add second webhook URL pointing to brain.signalmesh.dev
4. Positive-edge fixture to verify DA → RM → Executor agents fire

## 2026-05-21 morning — TradingView 3s timeout discovered

**Issue:** TradingView documentation (verified today) states webhooks time out
at 3 seconds. Brain's 6-agent council takes 5-90s to deliberate. If the webhook
handler waits for council completion before returning, TradingView will close
the connection and the signal will appear as "failed" in their UI — even if
Brain processed it successfully.

**Fix required (BEFORE fan-out):** Make /webhook/v18 return 200 immediately
after parsing + auth check, then run council.evaluate() in a background task.
FastAPI's BackgroundTasks or asyncio.create_task() pattern.

**Until this fix:** Brain will work for manual curl tests but real TradingView
alerts may show as failed in the TV alert log even when Brain processes them.


## 2026-05-21 morning — TradingView IP allowlist + 3s timeout finding

**Allowlist applied.** /etc/nginx/sites-available/brain.signalmesh.dev now has
a geo block that 403s any source IP except:
- 52.89.214.238, 34.212.75.30, 54.218.53.128, 52.32.178.7 (TradingView)
- 127.0.0.1, 62.171.164.19 (local testing)

/health stays open. /webhook/* is locked. Everything else 404s.
Backup at /etc/nginx/sites-available/brain.signalmesh.dev.bak.2026-05-21.

**3s timeout discovered from TradingView docs (verified 2026-05-21).**
TradingView closes the connection if Brain doesn't respond in 3 seconds.
Council deliberation takes 5-90s. /webhook/v18 must return 200 immediately
and run council.evaluate() in a background task before fan-out can succeed.

**Required before fan-out:**
1. Convert /webhook/v18 to fire-and-forget pattern (FastAPI BackgroundTasks
   or asyncio.create_task)
2. Decision-journal log format so background tasks can be analyzed later
3. Pine alert payload schema (alert_name, symbol, side, entry, sl, tp, secret)

## 2026-05-21 — Decision journal live

Schema: see src/utils/decision_journal.py. One JSON line per signal at
logs/decisions.jsonl. Fields always present (null when not applicable) so the
file parses as a stable dataframe.

First journaled signal: v18-tradingview_xauusd_buy_20260521_105014_61c4
Scout veto on tight SL, 3559ms latency, $0.03 estimated cost.

Cost estimates are heuristics, NOT accounting. Real numbers come from the
Anthropic console. Heuristic exists to give order-of-magnitude awareness
during shakedown.

Operator commands:
- Tail journal:     tail -f /home/shyam/brain-v2/brain/logs/decisions.jsonl
- Last 5 decisions: tail -5 /home/shyam/brain-v2/brain/logs/decisions.jsonl | jq -c .
- Approval rate:    jq -s 'group_by(.approved) | map({k:.[0].approved,n:length})' logs/decisions.jsonl
- Costs to date:    jq -s 'map(.anthropic_cost_est_usd) | add' logs/decisions.jsonl

## 2026-05-21 — Rate-limit blocker discovered (Anthropic Tier 1)

First real end-to-end test of council failed at Researcher's retry:
- Scout PROCEED on grade-A XAUUSD setup (13:39:07)
- Researcher 1st call succeeded, parse failed (known bug)
- Researcher retry call → anthropic.RateLimitError 429
- Account at Tier 1: 30,000 input tokens/min for claude-sonnet-4-6
- Council architecture needs ~60K tokens/signal across 6 agents

**Decision:** Move to Anthropic Tier 2 by adding $40 credit (auto-promotes
on cumulative spend). Single-signal council deliberations cannot complete
at Tier 1 due to retry behavior on parse failures.

**Open separately:** Researcher parse bug still recurring on first attempt
despite max_tokens=8000 fix. Real fix is two-pass split (web search pass,
then format pass). Deferring until tier upgrade is in place.


## 2026-05-21 — Permissive auth for shakedown (final auth design)

User instinct: bot should adapt to Pine reality, not force Pine edits with
every Brain change. v18 Pine source on TradingView may or may not include
"secret" in alert() JSON — Brain accepts both.

**Behavior:**
- `secret` field present + matches TRADINGVIEW_WEBHOOK_SECRET → auth_state=authenticated
- `secret` field present + wrong value → 401 reject (clear attack signal)
- `secret` field absent → auth_state=unauthenticated_ip_allowlist_only, accept
- Set `BRAIN_REQUIRE_SECRET=true` in .env to enforce strict mode (live trading)

**Defense layers active:**
1. nginx geo block — only TradingView's 4 IPs reach Brain (primary defense)
2. Optional inline secret if Pine happens to send it

**Live trading switch:**
When flipping dispatcher to live mode, also set BRAIN_REQUIRE_SECRET=true.
If Pine isn't sending secret by then, edit Pine ONCE to add it. That's the
only Pine edit ever needed.


## 2026-05-22 — Phase 1 complete: Polymarket Executor live

**Droplet:** DigitalOcean Frankfurt FRA1, $6/mo basic, Ubuntu 24.04
- IP: 64.226.107.138 (private: 10.114.0.2)
- Hostname: executor-pm-1
- User: bots (sudo NOPASSWD), SSH key-only login, root login disabled

**Domain:** executor-pm.signalmesh.dev → 64.226.107.138 (Cloudflare DNS, gray cloud)

**Service:** brother-executor-pm.service (systemd, hardened, auto-restart)
- Working dir: /home/bots/executor_polymarket
- Venv: .venv (py-clob-client 0.34.6, web3 7.16.0, cryptography 48.0.0)
- Logs: /home/bots/logs/events/events_YYYY-MM-DD.jsonl

**nginx + TLS:**
- /etc/nginx/sites-available/executor-pm
- Let's Encrypt cert, auto-renew via certbot.timer
- geo block allowlists Contabo Brain IP (62.171.164.19) + loopback for /signal and /admin
- /health open for watchdog monitoring (future)

**Firewall:** UFW active, inbound deny by default, allow 22/80/443 only

**End-to-end smoke test passed 2026-05-22 11:19 UTC:**
- Brain signed envelope with /home/shyam/brain-v2/keys/brain_signing_private.key
- HTTPS POST to https://executor-pm.signalmesh.dev/signal
- Executor verified signature, marked nonce, gated through 10 safety checks
- DRY_RUN=true → returned dry_run order, no real submission
- Event logged: signal_verified, nonce 55b9d793-c01e-4b75-b21f-d4c8b9e5fa16

**Known open items for Phase 2+ (Watchdog + Cutover):**
1. Reconciler stub returns {} for on-chain positions — must wire to real
   py-clob-client.get_positions() before any live wallet funds
2. Brain dispatcher is in print mode — flip to live only after watchdog drilled
3. Watchdog box not yet deployed — emergency HALT untested in production form
4. Polymarket opportunity scanner not yet built — Brain has no way to generate
   /webhook/polymarket calls automatically; manual curl only for now
5. Status website (status.signalmesh.dev) not yet built
6. ADMIN_HALT_TOKEN appeared in chat — rotate before live funding

## 2026-05-23 — Polymarket Scanner deployed

**Service:** brother-pm-scanner.service (Contabo, systemd, hardened)
**Code:** /home/shyam/brain-v2/scanner_polymarket/scanner.py (335 lines)
**Cadence:** 60min, max 3 candidates per cycle
**Source:** Polymarket Gamma API (public, no auth) — gamma-api.polymarket.com/markets
**Filter:** volume24hr ≥ $10K, resolution 1-90 days, YES price 0.05-0.95, has CLOB tokens
**Dedup:** scanner_state.json tracks evaluated condition_ids per UTC day
**Journal:** scanner_polymarket/logs/scanner.jsonl (one row per cycle)
**Cost projection:** ~$5-15/day during shakedown (Sonnet 4.6 Tier 2)

**Validated:**
- First foreground cycle 11:11 UTC: 100 markets fetched, 18 filtered, 3 posted,
  all Iran-related geopolitical markets, all Scout-vetoed for ambiguous resolution
  criteria. ~$0.09 cost. Total cycle 36.8s.
- First systemd cycle 11:17 UTC: dedup worked (3 prior markets skipped),
  picked fresh candidate "Brazil World Cup" — proves chain is autonomous.

**Brother v18 architecture status: PIPELINE COMPLETE**
- Contabo: Brain + Scanner + (untouched old XTB bot)
- Frankfurt: PM Executor (DRY_RUN locked)
- Domain: signalmesh.dev (auto-renew Let's Encrypt)
- Auth: Ed25519 envelopes Brain → Executor, verified end-to-end
- Safety: dispatch_mode=print, DRY_RUN=true, kill_switch ready

**Remaining for full v18 production-readiness:**
1. Watchdog service (Telegram alerts + emergency HALT drill)
2. Reconciler real wiring (py-clob-client.get_positions) before any live funding
3. Status dashboard (status.signalmesh.dev)
4. Flip Brain dispatcher to live (after 14d clean shakedown)
5. Fund Polymarket wallet with disposable USDC (only after watchdog drilled)

## 2026-05-26 — Emergency HALT drilled successfully (first time)

**Trigger:** Watchdog (Amsterdam 64.227.70.55) → halt_all.py polymarket
**Path:** ssh amsterdam → python -m src.halt_all polymarket → HTTPS POST to
  https://executor-pm.signalmesh.dev/admin/halt with admin token
**Bug found + fixed during drill:**
  - nginx geo allowlist on Frankfurt was missing 64.227.70.55, so initial
    halt attempts returned HTTP 403 at the nginx layer before reaching the
    executor app.
  - Fixed: added 64.227.70.55 (Amsterdam Watchdog) to /etc/nginx/sites-
    available/executor-pm geo block alongside existing 62.171.164.19
    (Contabo Brain) and 127.0.0.1.
**Result:** kill_switch tripped, /health confirmed, state.json reset by
  manual edit + systemd restart returned to false.
**SSH aliases added on Contabo:** `ssh frankfurt`, `ssh amsterdam` via
  ~/.ssh/config (User=bots, IdentityFile=~/.ssh/id_ed25519_brain_v2).
**Drill lessons:** test BEFORE you need it. Three drill attempts (two
  failed silently, one revealed the nginx misconfig) caught a real bug
  that would have made emergency halt impossible during a real incident.

## 2026-05-26 — Dashboard Approved Signals panel added

User noted that stats panel showed "22 approved / 284 total / 7.8% approval"
but no way to actually SEE those 22 approved signals. Added dedicated panel.

**Backend:** new endpoint `GET /api/decisions/approved?n=30` returns the
last N rows where `approved == true`, with entry/SL/TP/RR fields populated.

**Frontend:** new renderer `approved_feed` in app.js. Visual: green left
border, BUY/SELL/YES/NO side pill, monospace entry/SL/TP/RR line. Sits
next to AI Brain panel in the grid.

**Pattern that worked:** add endpoint → add renderer → edit panels.json →
restart backend → hard refresh browser. No CSS rebuild step, no nginx
reload (nginx serves static frontend directly).

Confirms the architecture promise: adding panels is JSON config + small
code, not redesign.

## 2026-05-27 — Reconciler real-wiring deployed (3-layer)

**File:** /home/bots/executor_polymarket/src/polymarket/positions.py (438 lines)
**Patched:** /home/bots/executor_polymarket/src/main.py (backup at .bak.20260527_091007)

**Three layers, layered for graceful degradation:**
1. PositionsLedger — JSON ledger at logs/positions.json. Always active.
2. CLOBPositionsView — sums buys-sells from py-clob-client.get_trades().
   Active when CLOB authenticated (POLYGON_PRIVATE_KEY set).
3. OnchainPositionsView — web3 balanceOfBatch on Polymarket Conditional
   Tokens contract 0x4D97DCd97eC945f40cF65F87097ACe5EA0476045 (Polygon).
   Active when WALLET_ADDRESS set.

**Activation matrix:**
- Both empty: stub mode (local == external, no drift triggers)
- POLYGON_PRIVATE_KEY only: CLOB-based reconciliation
- WALLET_ADDRESS only: on-chain checks
- Both set: full — ledger synced from CLOB, verified vs on-chain

**Current state:** stub mode (no wallet configured). System is correctly
degraded. When wallet is added later (post-shakedown), all 3 layers
activate without code changes.

**Status surfaced in /health.positions for dashboard visibility.**

**Activation procedure (recorded for future):**
1. Generate wallet on Frankfurt via eth_account.Account.create()
2. Fund with disposable USDC (start $10-25 max)
3. Add WALLET_ADDRESS + POLYGON_PRIVATE_KEY to /home/bots/executor_polymarket/.env
4. sudo systemctl restart brother-executor-pm
5. /health.positions.mode should flip to "full"


## 2026-05-28 — CLOB V2 migration (clob.py rewrite)
- Installed py-clob-client-v2 1.0.0 alongside V1 (no conflict, diff module name).
- Rewrote clob.py for V2 EOA path: SignatureTypeV2.EOA (type 0), WALLET_ADDRESS
  as funder, create_and_post_order + OrderArgs + PartialCreateOrderOptions.
- V1 backup at clob.py.v1bak. Deployed, syntax OK, service active, DRY_RUN intact.
- Confirmed V2 contract addresses on docs: CTF unchanged
  (0x4D97...6045), pUSD CollateralToken 0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB,
  CollateralOnramp 0x93070a847efEf7F70739046A929D47a521F5B8ee.
- CHOSE EOA path (sig type 0) over deposit-wallet (type 3) for simplicity.

## STILL PENDING before live (next session, after Binance unlock):
1. wallet.py: add pUSD balance check (currently USDC.e only)
2. Verify Poland geoblock status for Polymarket API
3. Decide if USDC needs manual wrap() to pUSD on EOA path, or deposit handles it
4. Fund: $1-2 test first (Polygon network!), then rest + POL gas
5. Configure .env: WALLET_ADDRESS (chat ok) + POLYGON_PRIVATE_KEY (nano only, never chat)
6. Test ONE tiny order on liquid market, watch reconciler see it

## 2026-05-29 — Wallet funded, V2 stack live, allowances pending

**Funded:** wallet 0x1c331E585246289624e94445c8E7aec21f45BdDd on Polygon.
- 5 USDC (native) + 5 POL withdrawn from Binance.
- Swapped 4.0 native USDC -> USDC.e on Uniswap V3 (0.01% pool); slippage $0.0005.
- Wrapped 3.99 USDC.e -> pUSD via Polymarket CollateralOnramp.
- Wallet now holds: ~4.5 POL gas, ~0.88 native USDC residual, 3.99 pUSD trade-ready.

**Code shipped:**
- swap.py — native USDC -> USDC.e via Uniswap V3 SwapRouter02
- test_order.py — auth/probe/construct/post tester for V2 SDK
- executor .env wired with key + funder + EOA signature type + working RPC

**Verified:** executor /health.positions.mode = "full", CLOB V2 authenticated
(EOA path), CLOB sees pUSD balance 3990000, all reads work.

**Open today, blocking live order:**
1. CTF Exchange V2 (0xE111...B996B) allowance for pUSD = 0
2. NegRisk Exchange (0xe222...0F59) allowance for pUSD = 0
3. CTF (0x4D97...6045) setApprovalForAll(exchange, true) for outcome tokens

Need approve_exchanges.py: 3 on-chain approve txs, then SDK lazy-approval may
handle the rest. Without these, every create_and_post_order will fail.

**Market microstructure note:** 90 of top 100 Polymarket markets by volume are
neg_risk. The 10% non-neg-risk subset is dominated by binary geopolitical
markets with very wide spreads (0.01/0.99 style). To test against liquid
markets at all, NegRisk Exchange approval is required, not optional.

**Lessons:**
- Binance USDC on Polygon = native (c3359), NOT bridged (4174). Always swap first.
- Address derivation must be verified after every .env edit (KEY length 66, MATCH:True).
- Don't paste partial keys in chat. Math may make a 5-char leak safe; the
  habit makes the 60-char leak inevitable.

## 2026-05-30 — Geoblock discovered, Dublin migration planned

**Discovery:** Polymarket V2 CLOB returns 403 on POST /order from Germany
(Frankfurt executor IP). Per docs.polymarket.com/developers/CLOB/geoblock,
DE/NL fully blocked, PL close-only. Read endpoints (/ok, /health) work from
blocked regions; only order placement is geofenced.

**Tested and confirmed working from Frankfurt before discovering 403:**
- V2 CLOB authentication (EOA path) ✓
- Market discovery via Gamma ✓
- Order book reads ✓
- Order construction + signing (SignedOrderV2 produced) ✓
- Wallet on /health shows mode=full, pUSD 3.99 visible to CLOB ✓
- 4 on-chain approvals deployed (CTF_EXCHANGE_V2, NEGRISK_EXCHANGE,
  setApprovalForAll x2) ✓

**Decision:** Migrate executor to DigitalOcean Dublin (eu-west-1), the
documented "closest non-georestricted region." Brain (Contabo) and Watchdog
(Amsterdam) stay — they don't call Polymarket APIs.

**Rejected:** Proxy-based geoblock circumvention. Polymarket TOS explicitly
forbids; risk of permanent account/wallet ban; ongoing $30-100/mo proxy
cost exceeds DigitalOcean Dublin droplet cost ($4-6/mo); circumventing
their geo policy doesn't change Polish law about trading on unlicensed
gambling sites anyway.

**Next session:** Execute Dublin migration via MIGRATION_HANDOFF.md
(12-phase runbook written this session). Fresh Claude chat recommended
given today's session length and number of incidents (key/address mix-up,
partial key leak, three filter iterations on test_order.py).

