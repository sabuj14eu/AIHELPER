"""The read-only market mirror.

AI Helper is not a second trading bot. It is a read-only market-data
consumer, and this package is the whole of that consumption: one client
that reads four GETs on the platform, and nothing that computes a price,
stores one, or decides anything from one.

Two separations are enforced here rather than described:

* **The web is never a price.** `web_search` carries `tool:network` and is
  gated by `app/tools/egress.py`; this reads a fixed, operator-configured
  platform URL. A snippet saying "gold is around 4270" can never reach a
  price field, because nothing in this package can see a search result.
* **The mirror never invents.** Stale is stale, missing is missing, and a
  bid/ask does not exist anywhere in the system being mirrored. Each of
  those returns an explicit state, never an estimate.
"""

from app.market.mirror import MarketMirror, MirrorResult

__all__ = ["MarketMirror", "MirrorResult"]
