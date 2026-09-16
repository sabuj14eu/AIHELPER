"""Live connectors: market news and the trading platform's read-only mirror.

Two tools that let Brother talk about *now* instead of only about the pack:

* ``market_news`` reads the same ForexFactory weekly calendar the v7 bot and
  the v18 brain read (one calendar, three readers, one staleness law) and
  renders the platform's three-state news risk: HIGH within 60 minutes of a
  high-impact event, ELEVATED within 240, LOW otherwise, and UNKNOWN whenever
  the feed cannot be read. UNKNOWN is never reported as LOW; a missing
  calendar proves nothing about the world (Freshness Law).
* ``trading_status`` reads the Sniper-System platform's API v1 with a user
  API key: portfolio, stats, open trades, last signals. Every one of those
  endpoints is read-only by the platform's Iron Rule 1; nothing here can
  place, modify or dispatch anything, and the key never appears in output.

Both carry the ``tool:live_data`` permission, are switched off per
deployment by settings, and report source, fetch time and age on every
reading so the model can quote freshness instead of asserting it.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx

from app.core.config import Settings
from app.database.enums import RiskLevel
from app.tools.registry import PERM_LIVE_DATA, IntentMatch, ToolResult, ToolSpec

UNKNOWN, HIGH, ELEVATED, LOW = "UNKNOWN", "HIGH", "ELEVATED", "LOW"
USER_AGENT = "AI-Helper/1.2 (self-hosted assistant; read-only)"
TIMEOUT = 15.0
HIGH_WINDOW_MIN = 60      # the platform's news_risk rule (workspace.news_risk)
ELEVATED_WINDOW_MIN = 240

_CURRENCY = re.compile(r"\b(USD|EUR|GBP|JPY|AUD|CAD|CHF|NZD|CNY)\b", re.I)
_CURRENCY_WORDS = {
    "dollar": "USD", "euro": "EUR", "pound": "GBP", "sterling": "GBP", "yen": "JPY",
    "gold": "USD", "xau": "USD", "silver": "USD", "xag": "USD",
    "us100": "USD", "nasdaq": "USD", "nas100": "USD", "spx": "USD", "us500": "USD",
}
_NEWS_WORDS = re.compile(
    r"\b(news|calendar|economic events?|nfp|non-?farm|cpi|fomc|pmi|payrolls?|rate decision|"
    r"high[- ]impact|red folder)\b",
    re.I,
)
_TRADING_WORDS = re.compile(
    r"\b(bot|v7|v18|executor|mt5|accounts?|portfolio|equity|balance|drawdown|floating|"
    r"open trades?|positions?|signals?|trades?|trading|plan|setup|heartbeat)\b",
    re.I,
)
_STATUS_WORDS = re.compile(
    r"\b(status|how(?:'s| is| are| was)|what(?:'s| is| are)|show|report|check|any|list|"
    r"open|last|latest|current|running|online|alive|today)\b",
    re.I,
)
_REASONING_WORDS = re.compile(
    r"\b(why|how (?:do|does|did|would|should|can)|should|explain|compare|strategy|"
    r"if|whether|opinion|think|recommend|draft|write|plan|setup|idea|view|outlook|careful)\b",
    re.I,
)
_DIRECT_MAX_CHARS = 90


def _age_text(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60} min"
    return f"{seconds // 3600}h {(seconds % 3600) // 60:02d}m"


def _parse_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def currency_in(text: str) -> str | None:
    """A currency the message names, directly or through an asset that keys off it."""
    match = _CURRENCY.search(text or "")
    if match:
        return match.group(1).upper()
    lowered = (text or "").lower()
    for word, code in _CURRENCY_WORDS.items():
        if re.search(rf"\b{word}\b", lowered):
            return code
    return None


# ====================================================================== news
@dataclass
class FeedReading:
    events: list[dict]
    fetched_at: datetime
    source: str


@dataclass
class _FeedCache:
    reading: FeedReading | None = None
    last_error: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


def normalise_events(rows: list) -> list[dict]:
    """ForexFactory rows -> one shape. Drops a row only when title or time is missing."""
    out: list[dict] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()
        when = _parse_time(row.get("date") or row.get("event_time") or "")
        if not title or when is None:
            continue
        item = {
            "title": title,
            "time": when,
            "impact": str(row.get("impact") or "medium").strip().lower(),
            "currency": str(row.get("country") or row.get("currency") or "").strip().upper(),
        }
        for key in ("forecast", "previous", "actual"):
            value = row.get(key)
            if value not in (None, ""):
                item[key] = str(value)[:32]
        out.append(item)
    out.sort(key=lambda e: e["time"])
    return out


def news_verdict(
    reading: FeedReading | None,
    *,
    now: datetime,
    max_age: timedelta,
    error: str | None = None,
) -> dict:
    """The platform's three-state rule over one reading. Never raises."""
    if reading is None:
        return {"state": UNKNOWN, "reason": f"the calendar could not be read ({error or 'never fetched'})"}
    age = now - reading.fetched_at
    if age > max_age:
        return {
            "state": UNKNOWN,
            "reason": f"the last good reading is {_age_text(age.total_seconds())} old, past the "
            f"{_age_text(max_age.total_seconds())} maximum ({error or 'refresh failed'})",
        }
    if not reading.events:
        return {"state": UNKNOWN, "reason": "the feed returned an empty week; no rows proves nothing"}
    newest = max(e["time"] for e in reading.events)
    upcoming_high = [e for e in reading.events if e["impact"] == "high" and e["time"] >= now]
    if newest < now - max_age and not upcoming_high:
        return {
            "state": UNKNOWN,
            "reason": f"dead feed: its newest event was {_age_text((now - newest).total_seconds())} "
            "ago and nothing is upcoming",
        }
    if not upcoming_high:
        return {"state": LOW, "reason": "no high-impact event remains in this week's calendar"}
    nxt = upcoming_high[0]
    minutes = (nxt["time"] - now).total_seconds() / 60
    label = f"{nxt['currency']} {nxt['title']} at {nxt['time'].strftime('%H:%M')} UTC"
    if minutes <= HIGH_WINDOW_MIN:
        state = HIGH
    elif minutes <= ELEVATED_WINDOW_MIN:
        state = ELEVATED
    else:
        state = LOW
    return {
        "state": state,
        "reason": f"next high-impact event in {_age_text(minutes * 60)}: {label}",
        "next": nxt,
        "minutes_to_next": int(minutes),
    }


def make_market_news_spec(settings: Settings, client: httpx.Client | None = None) -> ToolSpec:
    cache = _FeedCache()

    def fetch(now: datetime) -> tuple[FeedReading | None, str | None]:
        with cache.lock:
            fresh_for = timedelta(seconds=settings.MARKET_NEWS_REFRESH_SECONDS)
            if cache.reading is not None and now - cache.reading.fetched_at <= fresh_for:
                return cache.reading, None
            http = client or httpx.Client(timeout=TIMEOUT)
            try:
                response = http.get(
                    settings.MARKET_NEWS_URL,
                    headers={"user-agent": USER_AGENT, "accept": "application/json"},
                    timeout=TIMEOUT,
                )
                response.raise_for_status()
                rows = response.json()
                if not isinstance(rows, list):
                    raise ValueError("feed body is not a list")
                cache.reading = FeedReading(
                    events=normalise_events(rows), fetched_at=now, source=settings.MARKET_NEWS_URL
                )
                cache.last_error = None
            except httpx.TimeoutException:
                cache.last_error = "timeout"
            except httpx.HTTPError as exc:
                cache.last_error = type(exc).__name__
            except ValueError as exc:
                cache.last_error = f"unreadable body: {exc}"
            finally:
                if client is None:
                    http.close()
            return cache.reading, cache.last_error

    def market_news(currency: str | None = None, hours: int = 24, **_ignored) -> ToolResult:
        if not settings.MARKET_NEWS_ENABLED:
            return ToolResult(ok=False, error="market news is disabled in this deployment")
        now = datetime.now(UTC)
        reading, error = fetch(now)
        max_age = timedelta(hours=settings.MARKET_NEWS_MAX_AGE_HOURS)
        verdict = news_verdict(reading, now=now, max_age=max_age, error=error)
        wanted = (currency or "").upper() or None
        horizon = now + timedelta(hours=max(1, min(int(hours), 168)))

        lines = [f"Market news risk: {verdict['state']} — {verdict['reason']}."]
        if reading is not None:
            age = now - reading.fetched_at
            lines.append(
                f"Source: ForexFactory weekly calendar ({reading.source}), fetched "
                f"{reading.fetched_at.strftime('%Y-%m-%d %H:%M')} UTC, age {_age_text(age.total_seconds())}; "
                f"a reading older than {_age_text(max_age.total_seconds())} is UNKNOWN."
            )
        lines.append(
            f"Rule: HIGH within {HIGH_WINDOW_MIN} min of a high-impact event, ELEVATED within "
            f"{ELEVATED_WINDOW_MIN} min, LOW otherwise, UNKNOWN when the calendar cannot be read. "
            "The v7 bot's own gate blocks 30 min either side of any high-impact event (45 min for majors)."
        )
        upcoming: list[dict] = []
        if reading is not None:
            for event in reading.events:
                if event["time"] < now or event["time"] > horizon:
                    continue
                if wanted and event["currency"] != wanted:
                    continue
                if event["impact"] != "high":
                    continue
                upcoming.append(event)
            scope = f" for {wanted}" if wanted else ""
            lines.append(f"High-impact events in the next {int(hours)}h{scope}:")
            if upcoming:
                for event in upcoming[:12]:
                    extras = " ".join(
                        f"{k} {event[k]}" for k in ("actual", "forecast", "previous") if k in event
                    )
                    lines.append(
                        f"  {event['time'].strftime('%a %H:%M')} UTC  {event['currency']:<4} "
                        f"{event['title']}" + (f"  ({extras})" if extras else "")
                    )
            else:
                lines.append("  none in this window (calendar read; that is a reading, not a guess)")
        value = {
            "state": verdict["state"],
            "reason": verdict["reason"],
            "minutes_to_next_high": verdict.get("minutes_to_next"),
            "fetched_at": reading.fetched_at.isoformat() if reading else None,
            "age_seconds": int((now - reading.fetched_at).total_seconds()) if reading else None,
            "source": reading.source if reading else settings.MARKET_NEWS_URL,
            "currency": wanted,
            "upcoming_high": [
                {**e, "time": e["time"].isoformat()} for e in upcoming[:12]
            ],
            "error": error,
        }
        return ToolResult(
            ok=True,
            value=value,
            display="\n".join(lines),
            meta={"untrusted": True, "live": True, "state": verdict["state"]},
        )

    def intent(message: str) -> IntentMatch | None:
        if not settings.MARKET_NEWS_ENABLED or not _NEWS_WORDS.search(message):
            return None
        arguments: dict = {}
        currency = currency_in(message)
        if currency:
            arguments["currency"] = currency
        if re.search(r"\bthis week\b", message, re.I):
            arguments["hours"] = 168
        direct = len(message) <= _DIRECT_MAX_CHARS and not _REASONING_WORDS.search(message)
        return IntentMatch(arguments=arguments, direct=direct)

    return ToolSpec(
        name="market_news",
        description=(
            "Read the ForexFactory economic calendar (the system's one news source) and report "
            "the three-state news risk with the next high-impact events, their forecast and "
            "previous values, and how fresh the reading is. UNKNOWN when the feed cannot be read."
        ),
        permissions={PERM_LIVE_DATA},
        input_schema={
            "type": "object",
            "properties": {
                "currency": {"type": "string"},
                "hours": {"type": "integer"},
            },
            "additionalProperties": False,
        },
        output_schema={"type": "object", "properties": {"value": {"type": "object"}}},
        risk=RiskLevel.LOW,
        handler=market_news,
        answers_directly=True,
        intent=intent,
        enabled=settings.MARKET_NEWS_ENABLED,
    )


# =================================================================== trading
def _money(value) -> str:
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "UNKNOWN"


def make_trading_status_spec(settings: Settings, client: httpx.Client | None = None) -> ToolSpec:
    def configured() -> bool:
        return bool(
            settings.TRADING_STATUS_ENABLED
            and settings.TRADING_PLATFORM_URL
            and settings.TRADING_PLATFORM_API_KEY
        )

    def get(http: httpx.Client, path: str, params: dict | None = None):
        """One read. Returns (data, error); the key never enters the error."""
        try:
            response = http.get(
                settings.TRADING_PLATFORM_URL.rstrip("/") + path,
                params=params,
                headers={
                    "authorization": f"Bearer {settings.TRADING_PLATFORM_API_KEY}",
                    "accept": "application/json",
                    "user-agent": USER_AGENT,
                },
                timeout=TIMEOUT,
            )
            if response.status_code != 200:
                return None, f"HTTP {response.status_code}"
            return response.json(), None
        except httpx.TimeoutException:
            return None, "timeout"
        except httpx.HTTPError as exc:
            return None, type(exc).__name__
        except ValueError:
            return None, "non-JSON body"

    def trading_status(section: str = "all", **_ignored) -> ToolResult:
        if not settings.TRADING_STATUS_ENABLED:
            return ToolResult(ok=False, error="the trading platform connector is disabled")
        if not configured():
            return ToolResult(
                ok=False,
                error="the trading platform connector is not configured "
                "(TRADING_PLATFORM_URL and TRADING_PLATFORM_API_KEY)",
            )
        now = datetime.now(UTC)
        http = client or httpx.Client(timeout=TIMEOUT)
        want = (section or "all").lower()
        errors: dict[str, str] = {}
        data: dict = {}
        try:
            plan = {
                "portfolio": ("/api/v1/portfolio", None),
                "stats": ("/api/v1/stats", None),
                "trades": ("/api/v1/trades", {"status": "open", "limit": 20}),
                "signals": ("/api/v1/signals", {"limit": 8}),
            }
            for name, (path, params) in plan.items():
                if want not in ("all", name):
                    continue
                payload, error = get(http, path, params)
                if error:
                    errors[name] = error
                else:
                    data[name] = payload
        finally:
            if client is None:
                http.close()

        if not data:
            return ToolResult(
                ok=False,
                error="the trading platform did not answer: "
                + ", ".join(f"{k} {v}" for k, v in errors.items()),
            )

        host = re.sub(r"^https?://", "", settings.TRADING_PLATFORM_URL).rstrip("/")
        lines = [
            f"Trading platform mirror (read-only, DEMO accounts) — {host}, read "
            f"{now.strftime('%Y-%m-%d %H:%M')} UTC. The platform reports what heartbeats told it; "
            "'online' is heartbeat-driven inside its staleness window."
        ]
        portfolio = data.get("portfolio")
        if isinstance(portfolio, dict):
            lines.append(
                f"Accounts: {portfolio.get('online', 'UNKNOWN')} of {portfolio.get('accounts', 'UNKNOWN')} online · "
                f"balance {_money(portfolio.get('balance'))} · equity {_money(portfolio.get('equity'))} · "
                f"floating {_money(portfolio.get('floating_pnl'))} · free margin {_money(portfolio.get('free_margin'))}"
            )
        elif "portfolio" in errors:
            lines.append(f"Accounts: UNKNOWN ({errors['portfolio']})")

        trades = data.get("trades")
        if isinstance(trades, list):
            lines.append(f"Open trades ({len(trades)}):")
            for t in trades[:20]:
                lines.append(
                    f"  {t.get('symbol')} {t.get('direction')} {t.get('lots')} lots @ {t.get('entry')} "
                    f"sl {t.get('sl')} tp {t.get('tp')} · session {t.get('session') or 'UNKNOWN'} · "
                    f"opened {str(t.get('open_time') or 'UNKNOWN')[:16]} · floating {_money(t.get('profit'))}"
                )
            if not trades:
                lines.append("  none")
        elif "trades" in errors:
            lines.append(f"Open trades: UNKNOWN ({errors['trades']})")

        signals = data.get("signals")
        if isinstance(signals, list):
            lines.append(f"Last signals ({len(signals)}):")
            for s in signals[:8]:
                lines.append(
                    f"  {str(s.get('created_at') or '')[:16]} {s.get('system')} {s.get('direction')} "
                    f"{s.get('symbol')} {s.get('tf')} · status {s.get('status')} · grade {s.get('grade')} "
                    f"· rr {s.get('rr')} · id {s.get('signal_id')}"
                )
            if not signals:
                lines.append("  none mirrored yet")
        elif "signals" in errors:
            lines.append(f"Last signals: UNKNOWN ({errors['signals']})")

        stats = data.get("stats")
        if isinstance(stats, dict):
            count = stats.get("count", "UNKNOWN")
            sample = ""
            if stats.get("low_sample"):
                sample = f" — LOW SAMPLE, under the platform's {stats.get('min_sample', '?')}-trade floor; not a verdict"
            parts = [f"closed trades n={count}{sample}"]
            for key, label, unit in (
                # win_rate arrives as a percentage (analytics.core_stats rounds
                # it to one place), so it is rendered with its unit: "54.1"
                # standing next to "profit factor 1.21" is a number whose
                # meaning the reader has to guess.
                ("win_rate", "win rate", "%"),
                ("profit_factor", "profit factor", ""),
                ("total_profit", "net", ""), ("today_profit", "today", ""),
                ("weekly_profit", "7d", ""), ("monthly_profit", "30d", ""),
                ("max_drawdown", "max drawdown", ""),
                ("consecutive_losses", "consecutive losses", ""),
                ("best_symbol", "best symbol", ""), ("worst_symbol", "worst symbol", ""),
            ):
                if key not in stats:
                    continue
                # A key the platform sent as null was being dropped, which reads
                # as "not reported" when it means something: profit_factor is
                # null when there were no losing trades to divide by. Absence is
                # not zero and it is not silence -- it is UNKNOWN, and Brother
                # does not guess which of the two it was.
                value = stats[key]
                parts.append(f"{label} UNKNOWN" if value is None else f"{label} {value}{unit}")
            lines.append("Stats: " + " · ".join(parts))
        elif "stats" in errors:
            lines.append(f"Stats: UNKNOWN ({errors['stats']})")

        return ToolResult(
            ok=True,
            value={"read_at": now.isoformat(), "sections": data, "errors": errors},
            display="\n".join(lines),
            meta={"untrusted": True, "live": True, "partial": bool(errors)},
        )

    def intent(message: str) -> IntentMatch | None:
        if not configured() or not _TRADING_WORDS.search(message):
            return None
        direct = (
            len(message) <= _DIRECT_MAX_CHARS
            and bool(_STATUS_WORDS.search(message))
            and not _REASONING_WORDS.search(message)
        )
        return IntentMatch(arguments={}, direct=direct)

    return ToolSpec(
        name="trading_status",
        description=(
            "Read the Sniper-System platform's read-only mirror with the configured API key: "
            "accounts online, balance and equity, open trades, the last signals and the closed-trade "
            "stats with their sample size. It can read; it cannot place, modify or dispatch anything."
        ),
        permissions={PERM_LIVE_DATA},
        input_schema={
            "type": "object",
            "properties": {"section": {"type": "string"}},
            "additionalProperties": False,
        },
        output_schema={"type": "object", "properties": {"value": {"type": "object"}}},
        risk=RiskLevel.LOW,
        handler=trading_status,
        answers_directly=True,
        intent=intent,
        enabled=settings.TRADING_STATUS_ENABLED,
    )
