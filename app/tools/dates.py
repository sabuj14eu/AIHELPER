"""Date arithmetic. Deterministic, zero tokens, and correct about leap years."""

from __future__ import annotations

import calendar
import re
from datetime import UTC, date, datetime, timedelta

from app.database.enums import RiskLevel
from app.tools.registry import PERM_COMPUTE, ToolResult, ToolSpec

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")

OPERATIONS = ["difference", "add", "subtract", "weekday", "today", "end_of_month"]
UNITS = ["days", "weeks", "months", "years"]


def _parse(value: str) -> date:
    text = (value or "").strip()
    if text.lower() in ("today", "now"):
        return datetime.now(UTC).date()
    if not _ISO.match(text):
        raise ValueError(f"'{value}' is not an ISO date (YYYY-MM-DD)")
    return date.fromisoformat(text)


def _add_months(start: date, months: int) -> date:
    """Month arithmetic that clamps rather than overflowing.

    31 January + 1 month is 28/29 February, not 3 March. Clamping is the
    convention every accounting deadline uses.
    """
    total = start.month - 1 + months
    year = start.year + total // 12
    month = total % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def date_calculate(
    operation: str,
    start: str | None = None,
    end: str | None = None,
    amount: int | None = None,
    unit: str = "days",
    **_ignored,
) -> ToolResult:
    try:
        if operation == "today":
            today = datetime.now(UTC).date()
            return ToolResult(
                ok=True, value=today.isoformat(), display=today.isoformat(), meta={"tz": "UTC"}
            )

        if operation == "difference":
            if not start or not end:
                return ToolResult(ok=False, error="'difference' needs both start and end")
            first, second = _parse(start), _parse(end)
            days = (second - first).days
            return ToolResult(
                ok=True,
                value=str(days),
                display=f"{days} days",
                meta={"start": first.isoformat(), "end": second.isoformat(), "weeks": days // 7},
            )

        if operation in ("add", "subtract"):
            if not start or amount is None:
                return ToolResult(ok=False, error=f"'{operation}' needs start and amount")
            first = _parse(start)
            sign = 1 if operation == "add" else -1
            if unit == "days":
                result = first + timedelta(days=sign * amount)
            elif unit == "weeks":
                result = first + timedelta(weeks=sign * amount)
            elif unit == "months":
                result = _add_months(first, sign * amount)
            elif unit == "years":
                result = _add_months(first, sign * amount * 12)
            else:
                return ToolResult(ok=False, error=f"unknown unit '{unit}'")
            return ToolResult(
                ok=True,
                value=result.isoformat(),
                display=result.isoformat(),
                meta={"start": first.isoformat(), "amount": amount, "unit": unit},
            )

        if operation == "weekday":
            if not start:
                return ToolResult(ok=False, error="'weekday' needs start")
            first = _parse(start)
            name = calendar.day_name[first.weekday()]
            return ToolResult(
                ok=True,
                value=name,
                display=name,
                meta={"iso_weekday": first.isoweekday(), "is_weekend": first.weekday() >= 5},
            )

        if operation == "end_of_month":
            if not start:
                return ToolResult(ok=False, error="'end_of_month' needs start")
            first = _parse(start)
            last_day = calendar.monthrange(first.year, first.month)[1]
            result = date(first.year, first.month, last_day)
            return ToolResult(ok=True, value=result.isoformat(), display=result.isoformat())

        return ToolResult(ok=False, error=f"unknown operation '{operation}'")
    except ValueError as exc:
        return ToolResult(ok=False, error=str(exc))


SPEC = ToolSpec(
    name="date_calculator",
    description=(
        "Date arithmetic: difference between two dates, add/subtract days weeks months "
        "or years, the weekday of a date, the end of a month, or today's UTC date. "
        "Dates are ISO YYYY-MM-DD."
    ),
    permissions={PERM_COMPUTE},
    input_schema={
        "type": "object",
        "properties": {
            "operation": {"type": "string", "enum": OPERATIONS},
            "start": {"type": "string", "maxLength": 32},
            "end": {"type": "string", "maxLength": 32},
            "amount": {"type": "integer", "minimum": -100_000, "maximum": 100_000},
            "unit": {"type": "string", "enum": UNITS},
        },
        "required": ["operation"],
        "additionalProperties": False,
    },
    output_schema={"type": "object", "properties": {"value": {"type": "string"}}},
    risk=RiskLevel.LOW,
    handler=date_calculate,
)
