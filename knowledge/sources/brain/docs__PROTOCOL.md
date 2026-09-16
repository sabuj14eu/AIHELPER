---
title: v18 brain protocol
domain: brain
repo: sabuj14eu/brother-brain-v2
sources: docs/PROTOCOL.md
verified_on: 2026-09-16
commit: 0f8f49d
classification: INTERNAL
---

# Brother v18 — Brain↔Executor Protocol

## Overview

The Brain emits **signed JSON signals** to Executors over HTTPS POST. Every
signal carries an Ed25519 signature, a UUID nonce, and a UTC timestamp.

Executors verify all three before acting. A signal that fails any check is
silently dropped (with logging), never executed.

## Envelope format

```json
{
  "version": 1,
  "issued_at": "2026-05-12T13:45:00Z",
  "nonce": "8f3c1b2e-9a4d-4f1c-b8e7-1a2b3c4d5e6f",
  "target": "polymarket",
  "signal": {
    ...strategy-specific payload...
  },
  "signature": "base64-encoded-ed25519-signature"
}
```

## Signing

The signature covers a **canonical JSON serialization** of the envelope
**without** the `signature` field, with these rules:

- Keys sorted lexicographically
- Compact separators (`,` and `:`, no spaces)
- UTF-8 encoded
- No trailing whitespace

The Brain (`shared.src.protocol.envelope.SignalEnvelope.to_signable_bytes`) and
the Executors (which reconstruct via `parse_envelope` then re-serialize the
same way) both produce identical bytes. The verifier checks the signature
against those bytes.

## Executor verification checklist

Before executing any signal, the Executor runs **all** of these checks. Failing
any one means the signal is rejected.

| #  | Check                                            | Failure action     |
|----|--------------------------------------------------|--------------------|
| 1  | `version == 1`                                   | Drop + log         |
| 2  | `target` matches this executor                   | Drop + log         |
| 3  | `signature` verifies against Brain public key    | Drop + log + alert |
| 4  | `now() - issued_at < 60s`                        | Drop + log         |
| 5  | `nonce` not seen in last 10 minutes              | Drop + log + alert |
| 6  | `DRY_RUN` flag                                   | Log only, no order |
| 7  | Kill switch not tripped                          | Drop + log         |
| 8  | Per-day trade count under cap                    | Drop + log         |
| 9  | Per-day loss under cap                           | Drop + log         |
| 10 | Wallet/account balance above floor               | Drop + log + alert |

Checks 3 and 5 are the ones that, if they fail, trigger a **Telegram alert**
via the Watchdog. A bad signature or a replay nonce is suspicious — you want
to know immediately.

## Signal payloads (target-specific)

### Polymarket signal

```json
{
  "action": "OPEN" | "CLOSE" | "CANCEL_ALL",
  "market": {
    "condition_id": "0x...",
    "token_id_yes": "...",
    "token_id_no": "..."
  },
  "side": "YES" | "NO",
  "order_type": "GTC" | "FOK",
  "limit_price": 0.42,
  "size_usdc": 25.0,
  "post_only": true,
  "thesis_hash": "sha256:...",
  "thesis_summary": "human-readable rationale, max 280 chars"
}
```

### IC Markets signal

```json
{
  "action": "OPEN" | "CLOSE" | "MODIFY" | "CANCEL",
  "symbol": "EURUSD",
  "side": "BUY" | "SELL",
  "order_type": "MARKET" | "LIMIT" | "STOP",
  "entry_price": 1.0832,
  "stop_loss": 1.0810,
  "take_profit": 1.0875,
  "risk_pct": 0.5,
  "magic_number": 180000,
  "comment": "v18-OB-bullish",
  "thesis_hash": "sha256:..."
}
```

`risk_pct` is the percentage of account equity to risk on this trade. The
Executor computes lot size locally from `risk_pct`, `entry_price`, `stop_loss`,
and current account balance — the Brain doesn't need to know account size.

This decoupling is intentional: it means the Brain can drive multiple IC
Markets accounts (different sizes) with the same signal.

## Why this design beats alternatives

**Why Ed25519 not HMAC?** HMAC requires a shared secret. If an Executor is
compromised, the attacker can forge signals. With Ed25519, only the Brain can
sign — Executors only verify. Compromising an Executor can lose its wallet but
cannot escalate to controlling the whole system.

**Why HTTPS request/response not Redis/RabbitMQ?** You want execution
confirmation. POST gives you a 200 + order-id response. Pub/sub is
fire-and-forget — fine for telemetry, dangerous for trades.

**Why a 60-second age limit?** Long enough to survive network hiccups, short
enough that a stolen signal is useless before it can be replayed. Combined
with nonce checking, replay is functionally impossible.

**Why per-trade `risk_pct` not `lot_size`?** Brain doesn't know broker account
balance and shouldn't have to. Executor knows. Separation of concerns.
