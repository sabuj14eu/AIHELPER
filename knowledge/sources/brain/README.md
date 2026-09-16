---
title: v18 brain README
domain: brain
repo: sabuj14eu/brother-brain-v2
sources: README.md
verified_on: 2026-09-16
commit: 0f8f49d
classification: INTERNAL
---

# Brother v18 — Three-Tier Trading System

**One Brain. Two Executors. One Watchdog. Zero shared wallet keys.**

This is a security-isolated, signal-driven trading architecture for FX (IC Markets)
and prediction markets (Polymarket). It is the successor to v17. v17 is retired.

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│   ┌──────────────────┐                                              │
│   │  BRAIN (Contabo) │   Generates intelligence. NO wallet keys.    │
│   │                  │                                              │
│   │  - v18 signals   │                                              │
│   │  - 6-agent       │                                              │
│   │    council       │                                              │
│   │  - MiroFish sims │                                              │
│   │  - news/macro    │                                              │
│   │                  │                                              │
│   │  Ed25519 signer  │                                              │
│   └────────┬─────────┘                                              │
│            │                                                        │
│            │  signed JSON over HTTPS                                │
│            │  { signal, nonce, timestamp, signature }               │
│            │                                                        │
│        ┌───┴───────────────┬──────────────────────┐                 │
│        ▼                   ▼                      ▼                 │
│  ┌───────────┐       ┌──────────────┐       ┌──────────┐            │
│  │ EXECUTOR  │       │  EXECUTOR    │       │ WATCHDOG │            │
│  │ IC Markets│       │  Polymarket  │       │          │            │
│  │ (Windows  │       │  (DO Dublin) │       │ pings    │            │
│  │  VPS)     │       │              │       │ every    │            │
│  │           │       │ py-clob-client│      │ 30s,     │            │
│  │ MT4/MT5   │       │ web3 wallet  │       │ Telegram │            │
│  │ bridge    │       │              │       │ alerts   │            │
│  └─────┬─────┘       └──────┬───────┘       └──────────┘            │
│        │                    │                                       │
│        ▼                    ▼                                       │
│   IC Markets          Polymarket CLOB                               │
│   FX / Indices        Polygon mainnet                               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Why this design

**Security.** Brain server has full internet access (news, scraping, agents). If
it ever gets compromised, the attacker still cannot move funds, because no key
ever sits there. Executors hold keys but have no reason to touch the internet
beyond their broker/RPC — outbound firewall whitelist enforces that.

**Resilience.** If Polymarket executor crashes, IC Markets keeps trading. If
Brain crashes, both executors stop receiving new signals but existing positions
remain managed. If an executor's IP gets blocked, the other is unaffected.

**Verifiability.** Every signal is Ed25519-signed by the Brain. Every executor
verifies before acting. Nonces prevent replay. Timestamps reject stale signals.
A compromised executor cannot forge instructions back to the Brain.

**Evolution path.** Brain is the only place where logic changes. Executors stay
ultra-thin and rarely need redeployment. New strategies plug into the Brain
without touching live trading machines.

---

## Repository layout

| Folder                    | Deploys to              | Role                          |
|---------------------------|-------------------------|-------------------------------|
| `brain/`                  | Contabo Linux           | Signal generation + 6 agents  |
| `executor_polymarket/`    | DigitalOcean Dublin     | Polymarket CLOB execution     |
| `executor_ic_markets/`    | Windows VPS             | IC Markets bridge             |
| `watchdog/`               | Any cheap host (or PC)  | Liveness + PnL monitoring     |
| `shared/`                 | Imported by all four    | Crypto + protocol definitions |
| `deploy/`                 | —                       | Deploy scripts + nginx config |

Each of the four runtime components has its own README, its own
`requirements.txt`, and its own `.env.example`. They are **independent
deployments** — you should be able to lose any one of them without breaking the
others.

---

## Deploy order (first time)

1. **Generate Brain signing keypair** on a clean machine (your laptop, offline).
   Distribute the **public key** to both executors and the watchdog.
   Keep the **private key** on the Brain only.

   ```bash
   python -m shared.src.crypto.keygen
   # Produces: brain_signing_private.key  (Brain only)
   #           brain_signing_public.key   (Executors + Watchdog)
   ```

2. **Deploy Polymarket Executor** on DigitalOcean Dublin first (it's the
   simpler one, easier to verify).
   - Fund Polygon wallet with USDC.e + a small MATIC reserve for gas.
   - Set `DRY_RUN=true`. Keep it dry-run for **at least 2 weeks**.
   - Configure UFW outbound whitelist (see `deploy/firewall_executor.sh`).

3. **Deploy IC Markets Executor** on Windows VPS.
   - Install MT5 + Python bridge.
   - Set `DRY_RUN=true`.
   - This executor receives v18 alerts that previously went directly to the
     MT5 bot — now they route through the Brain first.

4. **Deploy Brain** on Contabo.
   - Configure both executor endpoints.
   - Set `ANTHROPIC_API_KEY`, MiroFish path, etc.
   - Start in **signal-print mode** (logs signals but does not POST to
     executors) for the first 48h, just to verify Brain output is sane.

5. **Deploy Watchdog** anywhere with internet.
   - Configure Telegram bot token + your chat ID.
   - Set kill-switch thresholds.

6. **Cutover**: flip Brain's POST mode on. Executors still in DRY_RUN. Watch
   for 7 days. Then flip Polymarket Executor to live with $25 max position.
   Hold IC Markets Executor in DRY_RUN until Polymarket has been live and
   green for 14 days.

---

## Safety defaults

Every executor refuses to act if **any** of these are true:
- Signature verification fails
- Signal timestamp is older than 60s
- Nonce was seen before (replay)
- `DRY_RUN=true`
- Kill switch tripped (manual or watchdog)
- Daily trade count exceeded
- Daily loss limit exceeded
- Wallet balance below floor

Default caps (override per-executor in `.env`):
- Polymarket: 3 trades/day, $25 max position, $15 daily loss limit
- IC Markets: 6 trades/day, 0.5% account-risk per trade, 2% daily loss limit

---

## What's NOT in this repo

- Your **v18 Pine Script source** — it lives on TradingView, not here. The
  Brain receives v18 alerts via webhook (handled in `brain/src/signals/`).
- Wallet **private keys**. Ever. Anywhere. Only `.env` on the relevant
  executor host, never committed.
- **Old v17 / v8 rebuild files**. Deleted, do not resurrect.

---

## Quick reference: data flow

```
v18 TradingView alert
        │
        ▼
[Brain] /webhook/v18  ──┐
                        │
News/sentiment scrape ──┤
                        │ ▼
                       6-agent council
                        │
                       MiroFish sandbox (Polymarket only)
                        │
                       Risk gate (Kelly, caps)
                        │
                       Signal builder + Ed25519 signer
                        │
                       ┌┴──────────────┐
                       ▼               ▼
              [Executor IC]    [Executor Polymarket]
                  │                    │
                 MT5                py-clob-client
                  │                    │
                IC Markets         Polygon CLOB
```

See `docs/PROTOCOL.md` for the full signed-signal spec.
