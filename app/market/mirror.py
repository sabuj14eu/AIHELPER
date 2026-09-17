"""One client for the platform's market mirror. Reads; never writes.

The platform is the trading authority and the single market-data truth.
This asks it four questions and hands the answers back unchanged, with
one addition: a `mirror` block saying where the answer came from, how old
it is, and — when it could not be had — why, in a word a caller can branch
on rather than a message a caller has to parse.

**What it must never do**, each of which is a test:

* invent a price, a bid, an ask or a level when the platform has none,
* turn a stale answer into a usable one,
* reach any URL but the configured platform's, or
* issue anything but a GET.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

from app.core.config import Settings
from app.core.logging import get_logger

log = get_logger("market")

TIMEOUT = 20.0
USER_AGENT = "ai-helper/market-mirror"

# The four reads, and the only four. A path not in this table cannot be
# requested: the caller names an endpoint, never a URL, so no request body
# and no caller input can steer this at another host or another route.
ENDPOINTS = {
    "snapshot": "/api/v1/market/snapshot",
    "desk": "/api/v1/market/desk",
    "candles": "/api/v1/market/candles",
    "outlook": "/api/v1/outlook",
}

# Why an answer is not available, as a word rather than a sentence. A
# caller branches on these; the human-readable `note` is for a reader.
NOT_CONFIGURED = "NOT_CONFIGURED"
UNREACHABLE = "UNREACHABLE"
REFUSED = "REFUSED"
UNKNOWN = "UNKNOWN"
OK = "OK"


@dataclass
class MirrorResult:
    """An answer from the platform, or a named reason there is none."""

    endpoint: str
    state: str
    data: dict | None = None
    note: str = ""
    read_at: str = ""
    params: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.state == OK and self.data is not None

    @property
    def freshness(self) -> dict:
        """The platform's own freshness block, or UNKNOWN if there is none.

        Never synthesised. If the platform did not say how fresh something
        is, the honest answer is that we do not know — not that it is fine.
        """
        if not self.ok:
            return {"state": UNKNOWN, "note": self.note or "no answer from the platform"}
        block = self.data.get("freshness")
        if isinstance(block, dict) and block.get("state"):
            return block
        snapshot = self.data.get("snapshot") or {}
        candles = (snapshot.get("freshness") or {}).get("candles")
        if isinstance(candles, dict) and candles.get("state"):
            return candles
        return {"state": UNKNOWN, "note": "the platform reported no freshness for this read"}

    @property
    def is_usable(self) -> bool:
        """Fresh enough to reason from.

        STALE is not a degraded yes. The platform's own rule is that a stale
        feed produces no levels at all, and a mirror that softened that
        would be the first place the Freshness Law leaked.
        """
        return self.ok and self.freshness.get("state") == "LIVE"

    def as_dict(self) -> dict:
        return {
            "mirror": {
                "endpoint": self.endpoint,
                "state": self.state,
                "note": self.note,
                "read_at": self.read_at,
                "params": self.params,
                "freshness": self.freshness,
                "usable": self.is_usable,
                "source": "SignalMesh platform (read-only mirror)",
            },
            "data": self.data,
        }


class MarketMirror:
    """Reads the platform. Holds no state and decides nothing."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self.settings.TRADING_PLATFORM_URL
                    and self.settings.TRADING_PLATFORM_API_KEY)

    def read(self, endpoint: str, **params) -> MirrorResult:
        """One GET. Every failure comes back named, never raised.

        A market read that raises would make a caller's error path decide
        what a missing price means, and that decision belongs here.
        """
        now = datetime.now(UTC).isoformat()
        clean = {k: v for k, v in params.items() if v is not None}
        if endpoint not in ENDPOINTS:
            raise ValueError(f"unknown market endpoint '{endpoint}'")
        if not self.configured:
            return MirrorResult(
                endpoint, NOT_CONFIGURED, note=(
                    "the trading platform connector is not configured "
                    "(TRADING_PLATFORM_URL and TRADING_PLATFORM_API_KEY)"),
                read_at=now, params=clean)

        http = self._client or httpx.Client(timeout=TIMEOUT)
        try:
            response = http.get(
                self.settings.TRADING_PLATFORM_URL.rstrip("/") + ENDPOINTS[endpoint],
                params=clean,
                headers={
                    # The key is read from settings and never enters a note,
                    # a log line or an error (Iron Rule 7).
                    "authorization": f"Bearer {self.settings.TRADING_PLATFORM_API_KEY}",
                    "accept": "application/json",
                    "user-agent": USER_AGENT,
                },
                timeout=TIMEOUT,
            )
        except httpx.TimeoutException:
            return MirrorResult(endpoint, UNREACHABLE, note="the platform timed out",
                                read_at=now, params=clean)
        except httpx.HTTPError as exc:
            return MirrorResult(endpoint, UNREACHABLE,
                                note=f"the platform could not be reached "
                                     f"({type(exc).__name__})",
                                read_at=now, params=clean)
        finally:
            if self._client is None:
                http.close()

        if response.status_code == 401:
            return MirrorResult(endpoint, REFUSED,
                                note="the platform rejected this API key",
                                read_at=now, params=clean)
        if response.status_code != 200:
            # The platform's own 400s say something useful ("unknown
            # timeframe '7m'"), so they are passed through rather than
            # flattened into "it failed".
            detail = ""
            with contextlib.suppress(Exception):
                detail = str(response.json().get("detail", ""))[:200]
            return MirrorResult(endpoint, REFUSED,
                                note=f"HTTP {response.status_code}"
                                     + (f": {detail}" if detail else ""),
                                read_at=now, params=clean)
        try:
            data = response.json()
        except ValueError:
            return MirrorResult(endpoint, UNREACHABLE,
                                note="the platform returned a non-JSON body",
                                read_at=now, params=clean)
        if not isinstance(data, dict):
            return MirrorResult(endpoint, UNREACHABLE,
                                note="the platform returned an unexpected shape",
                                read_at=now, params=clean)
        log.info("market_read", endpoint=endpoint, **clean)
        return MirrorResult(endpoint, OK, data=data, read_at=now, params=clean)

    # Four named reads, so a caller never builds a path.
    def snapshot(self, symbol: str) -> MirrorResult:
        return self.read("snapshot", symbol=symbol)

    def desk(self, symbol: str) -> MirrorResult:
        return self.read("desk", symbol=symbol)

    def candles(self, symbol: str, tf: str = "15m", n: int = 300) -> MirrorResult:
        return self.read("candles", symbol=symbol, tf=tf, n=n)

    def outlook(self, symbol: str) -> MirrorResult:
        return self.read("outlook", symbol=symbol)
