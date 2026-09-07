"""Rate limiting.

A token bucket per client, held in this process's memory.

Stated plainly so nobody is surprised in production: **this limiter is
per-process**. Two workers means twice the effective limit, and a restart
resets every bucket. It is a guard against a runaway client and an accidental
loop, not a security boundary against a determined attacker. Moving it behind
Redis is the documented next step (docs/operations.md) and the interface below
is what a Redis implementation would replace.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class Decision:
    allowed: bool
    remaining: float
    retry_after: float = 0.0
    limit: int = 0


class TokenBucketLimiter:
    def __init__(self, rate_per_minute: int, burst: int):
        self.rate_per_minute = max(1, rate_per_minute)
        self.burst = max(1, burst)
        self._lock = threading.Lock()
        self._buckets: dict[str, tuple[float, float]] = {}

    def _capacity(self, override: int | None) -> tuple[float, float]:
        """Refill rate and bucket capacity.

        ``rate_per_minute`` is the sustained rate; ``burst`` is how many
        requests may arrive at once. Capacity is therefore the burst, not the
        larger of the two — taking the maximum would make the burst setting do
        nothing whenever it was smaller than the rate, which is the usual case.
        """
        rate_per_minute = override if override and override > 0 else self.rate_per_minute
        return rate_per_minute / 60.0, float(self.burst)

    def check(self, key: str, *, rate_override: int | None = None, cost: float = 1.0) -> Decision:
        refill_per_second, capacity = self._capacity(rate_override)
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(key, (capacity, now))
            tokens = min(capacity, tokens + (now - last) * refill_per_second)
            if tokens < cost:
                needed = (cost - tokens) / refill_per_second
                self._buckets[key] = (tokens, now)
                return Decision(
                    allowed=False,
                    remaining=tokens,
                    retry_after=round(needed, 2),
                    limit=int(capacity),
                )
            tokens -= cost
            self._buckets[key] = (tokens, now)
            return Decision(allowed=True, remaining=tokens, limit=int(capacity))

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._buckets.clear()
            else:
                self._buckets.pop(key, None)
