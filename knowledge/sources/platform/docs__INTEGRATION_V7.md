---
title: Platform contract with the v7 bot
domain: platform
repo: sabuj14eu/Sniper-System
sources: docs/INTEGRATION_V7.md
verified_on: 2026-09-16
commit: 3257184
classification: INTERNAL
---

# Connecting the v7 bot's decision stream to the platform

The platform's Decision Lab (`/decision-lab`) unifies decisions from both
systems. v18 decisions arrive automatically through the signal mirror.
v7 already *records* everything (accepts, rejects, blocks, AI-score
breakdowns) in `learning/telemetry.jsonl` — it just doesn't send it
anywhere. This document is the contract + patch to close that gap.

**Direction stays one-way**: v7 → platform. The platform never sends
anything back to a bot (constitutional rule).

## Endpoint

`POST {PLATFORM_URL}/webhooks/brain/decision`
Header: `X-Brain-Secret: <BB_BRAIN_WEBHOOK_SECRET>`
Body: one JSON object **or a list** (batch). Recognised fields (everything
else passes through verbatim into `raw_payload` — append-only contract):

```json
{
  "system": "v7",
  "symbol": "XAUUSD",            // aliases normalized server-side (XAUUSD→GOLD)
  "direction": "BUY",
  "status": "rejected",          // accepted|executed|rejected|blocked|filtered|skipped|paused|ignored
  "reason": "AI filter 38 < threshold 55",
  "session": "london",
  "regime": "TREND",
  "score": 38,
  "gates": { "session": 9, "news": 10, "rr": 4, "trend": 0, "...": "..." },
  "signal_id": "abc123...",
  "ts": "2026-08-07T09:31:00+00:00"
}
```

## Patch for v7 (`bot.py`, at the existing reject choke point ~line 1157)

v7 already funnels every negative decision through one place (the
`capture_reject` call in the `/webhook` route). Add a fire-and-forget POST
next to it, and one more on successful opens:

```python
# --- platform mirror (one-way, best-effort, never blocks trading) ---------
import threading

PLATFORM_URL = os.environ.get("PLATFORM_URL", "")            # e.g. https://app.yourdomain.com
PLATFORM_SECRET = os.environ.get("PLATFORM_SECRET", "")      # = platform BB_BRAIN_WEBHOOK_SECRET

def mirror_decision(record: dict) -> None:
    if not PLATFORM_URL or not PLATFORM_SECRET:
        return
    def _post():
        try:
            requests.post(f"{PLATFORM_URL}/webhooks/brain/decision",
                          json={**record, "system": "v7"},
                          headers={"X-Brain-Secret": PLATFORM_SECRET}, timeout=5)
        except Exception:
            pass  # mirror is best-effort; trading never waits on it
    threading.Thread(target=_post, daemon=True).start()
```

Call sites:
1. Where `capture_reject(...)` fires → `mirror_decision({**telemetry_row, "status": reject_status, "reason": reject_reason})`
2. After a successful open (where `telemetry_open` is written, ~line 1029) → `mirror_decision({**telemetry_row, "status": "executed"})`

Set on the v7 box (`.env` / service env):
```
PLATFORM_URL=https://app.yourdomain.com
PLATFORM_SECRET=<same value as the platform's BB_BRAIN_WEBHOOK_SECRET>
```

Backfill history once (from the v7 directory):
```bash
python - <<'EOF'
import json, os, requests
url = os.environ["PLATFORM_URL"] + "/webhooks/brain/decision"
h = {"X-Brain-Secret": os.environ["PLATFORM_SECRET"]}
batch = []
for line in open("learning/telemetry.jsonl"):
    try:
        r = json.loads(line)
    except ValueError:
        continue
    if r.get("_type") == "reject":
        r["status"] = r.get("reject_status", "rejected"); r["reason"] = r.get("reject_reason", "")
    elif r.get("_type") == "telemetry_open":
        r["status"] = "executed"
    else:
        continue
    r["system"] = "v7"; batch.append(r)
    if len(batch) >= 200:
        requests.post(url, json=batch, headers=h, timeout=30); batch = []
if batch: requests.post(url, json=batch, headers=h, timeout=30)
print("backfill done")
EOF
```

## v18 brain — richer decisions & artifacts

The signal mirror already normalizes v18 decisions. Two optional additions
on the brain box:

- **Rejected-before-signal decisions** (council vetoes that never became a
  dispatched signal): POST them to `/webhooks/brain/decision` with
  `"system": "v18"`.
- **Research artifacts** (nightly cron): POST scorecard / edge-report /
  backtest JSON to `/webhooks/brain/artifact` as
  `{"kind": "edge_report", "title": "Nightly edge 2026-08-07", ...payload}`.
  They appear under `/research`.
- **Candles**: `/webhooks/brain/candles` with
  `{"symbol": "XAUUSD", "tf": "15m", "candles": [{"ts": 1731000000, "o":..,"h":..,"l":..,"c":..,"v":..}]}`
  — or skip this and enable `BB_PUSH_CANDLES=1` on the MT5 reporter, which
  pushes real terminal OHLC directly.

## Monitoring

`/admin/data` shows per-feed candle freshness and last-seen ages for the
v18 signal mirror, both decision streams, and brain webhooks — stale rows,
not green endpoints, are the truth.
