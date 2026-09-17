"""The market mirror, as four read-only GETs.

AI Helper is a read-only market-data consumer; SignalMesh is the trading
authority and the executor. These four endpoints are the consuming half —
they read the platform's own market reads and hand them on, adding
provenance and a freshness verdict and nothing else.

They compute no price, store no price and decide nothing. There is no POST,
no PUT and no DELETE here, and there never will be: a write path in a mirror
is a second source of truth.

The other half of the separation matters as much: **a web search is not a
price.** `web_search` carries `tool:network`; this reads a fixed,
operator-configured platform URL and cannot see a search result at all.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import current_client, settings_dep
from app.core.config import Settings
from app.database.models import Client
from app.market import MarketMirror

router = APIRouter(prefix="/api/v1", tags=["market"])

# Mirrors the platform's own bound. Kept here too so a caller learns the
# limit from a 422 rather than from a silently shortened series.
MAX_CANDLES = 1000


def _mirror(settings: Settings) -> MarketMirror:
    return MarketMirror(settings)


@router.get("/market/snapshot", summary="The platform's canonical market snapshot")
def market_snapshot(
    symbol: str = Query(min_length=1, max_length=32),
    client: Client = Depends(current_client),
    settings: Settings = Depends(settings_dep),
) -> dict:
    """Price, structure, levels, news, macro and freshness, as the platform
    computed them once for every one of its own consumers.

    Nothing is recomputed on the way through. The platform's snapshot exists
    so that two readers can never disagree about the same instant, and a
    mirror that recalculated anything would be the second reader that does.
    """
    return _mirror(settings).snapshot(symbol.strip().upper()).as_dict()


@router.get("/market/desk", summary="The Trade Desk's lanes (PAPER RESEARCH)")
def market_desk(
    symbol: str = Query(min_length=1, max_length=32),
    client: Client = Depends(current_client),
    settings: Settings = Depends(settings_dep),
) -> dict:
    """The desk's candidate lanes, with their PAPER RESEARCH label intact.

    Brother may explain these. It may not act on them, and neither may
    anything downstream of this endpoint: they never become READY and never
    reach an executor.
    """
    return _mirror(settings).desk(symbol.strip().upper()).as_dict()


@router.get("/market/candles", summary="Closed OHLC candles")
def market_candles(
    symbol: str = Query(min_length=1, max_length=32),
    tf: str = Query(default="15m", max_length=8),
    n: int = Query(default=300, ge=1, le=MAX_CANDLES),
    client: Client = Depends(current_client),
    settings: Settings = Depends(settings_dep),
) -> dict:
    """Closed candles, oldest first, each with its stored spread and source.

    Closed only, because a forming bar is not a fact yet. Tick volume is
    named `tick_volume` by the platform and stays named that here — it is
    not traded size and must never be reasoned about as liquidity.
    """
    return _mirror(settings).candles(symbol.strip().upper(), tf.strip().lower(), n).as_dict()


@router.get("/outlook", summary="The posted weekly and monthly outlook")
def outlook(
    symbol: str = Query(min_length=1, max_length=32),
    client: Client = Depends(current_client),
    settings: Settings = Depends(settings_dep),
) -> dict:
    """AIH-6. Both horizons rendered against one measured price, so the two
    can never disagree about "now"; ABSENT when nothing has been posted."""
    return _mirror(settings).outlook(symbol.strip().upper()).as_dict()
