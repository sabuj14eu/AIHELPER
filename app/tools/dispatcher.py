"""Level 0 of the routing ladder: can a deterministic tool answer this outright?

The matcher is intentionally conservative. It fires only on requests whose
shape is unambiguous — a bare arithmetic expression, an explicit date
question — because a false positive here returns a confidently wrong answer
with no model in the loop to catch it. Everything it declines falls through to
retrieval and the local model, which costs nothing extra.

Nothing here is application-specific: no accounting rules, no trading rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.errors import PermissionDeniedError, ToolError
from app.database.enums import TaskType
from app.tools.registry import ToolRegistry, ToolResult

# A message that is nothing but an arithmetic expression, optionally wrapped in
# "what is …?" / "calculate …" / "compute …".
_ARITH_BODY = r"[0-9\s()+\-*/%^.,]+(?:\*\*[0-9\s()+\-*/%.,]+)*"
_ARITH_PATTERNS = [
    re.compile(rf"^\s*(?P<expr>{_ARITH_BODY})\s*=?\s*[?.]?\s*$"),
    re.compile(
        rf"^\s*(?:what(?:'s| is)|how much is|calculate|compute|evaluate|work out)\s*"
        rf"(?P<expr>{_ARITH_BODY})\s*=?\s*[?.!]?\s*$",
        re.IGNORECASE,
    ),
]
# Requires at least one operator and one digit, so "2" or "(())" do not match.
_HAS_OPERATOR = re.compile(r"[+\-*/%^]|\*\*")
_HAS_DIGIT = re.compile(r"\d")

_DATE = r"(\d{4}-\d{2}-\d{2})"
_DATE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            rf"^\s*(?:how many days?)\s+(?:are\s+)?(?:there\s+)?between\s+{_DATE}\s+and\s+{_DATE}\s*[?.]?\s*$",
            re.IGNORECASE,
        ),
        "difference",
    ),
    (
        re.compile(rf"^\s*what\s+(?:day|weekday)\s+(?:of the week\s+)?(?:is|was)\s+{_DATE}\s*[?.]?\s*$", re.IGNORECASE),
        "weekday",
    ),
    (
        re.compile(rf"^\s*(?:what is\s+)?{_DATE}\s*\+\s*(\d+)\s*(days?|weeks?|months?|years?)\s*[?.]?\s*$", re.IGNORECASE),
        "add",
    ),
    (
        re.compile(rf"^\s*(?:what is\s+)?{_DATE}\s*-\s*(\d+)\s*(days?|weeks?|months?|years?)\s*[?.]?\s*$", re.IGNORECASE),
        "subtract",
    ),
    (
        re.compile(rf"^\s*(?:what is the\s+)?(?:end|last day) of (?:the )?month (?:for|of)\s+{_DATE}\s*[?.]?\s*$", re.IGNORECASE),
        "end_of_month",
    ),
]

_JSON_REQUEST = re.compile(
    r"^\s*(?:is this valid json|validate this json|parse this json)\s*[:\-]?\s*(?P<body>[\[{][\s\S]*)$",
    re.IGNORECASE,
)


@dataclass
class DispatchResult:
    matched: bool
    tool: str | None = None
    arguments: dict | None = None
    result: ToolResult | None = None
    answer: str | None = None
    error: str | None = None


def _arith_expression(message: str) -> str | None:
    for pattern in _ARITH_PATTERNS:
        match = pattern.match(message)
        if not match:
            continue
        expression = match.group("expr").strip().rstrip("=").strip()
        if not expression:
            continue
        if not _HAS_OPERATOR.search(expression) or not _HAS_DIGIT.search(expression):
            continue
        # A lone "-5" is a number, not a calculation.
        if re.fullmatch(r"[+\-]?\s*\d+(?:[.,]\d+)?", expression):
            continue
        return expression
    return None


def try_dispatch(
    message: str,
    registry: ToolRegistry,
    *,
    task_type: TaskType | str = TaskType.GENERAL,
    allowed_tools: list[str] | None = None,
    granted_permissions: set[str] | None = None,
    context: dict | None = None,
) -> DispatchResult:
    """Attempt a zero-token answer. Returns ``matched=False`` to fall through."""
    text = (message or "").strip()
    if not text or len(text) > 2000:
        return DispatchResult(matched=False)

    plan: tuple[str, dict] | None = None

    expression = _arith_expression(text)
    if expression:
        plan = ("calculator", {"expression": expression})

    if plan is None:
        for pattern, operation in _DATE_PATTERNS:
            match = pattern.match(text)
            if not match:
                continue
            groups = match.groups()
            if operation == "difference":
                plan = ("date_calculator", {"operation": "difference", "start": groups[0], "end": groups[1]})
            elif operation in ("add", "subtract"):
                unit = groups[2].lower().rstrip("s") + "s"
                plan = (
                    "date_calculator",
                    {"operation": operation, "start": groups[0], "amount": int(groups[1]), "unit": unit},
                )
            else:
                plan = ("date_calculator", {"operation": operation, "start": groups[0]})
            break

    if plan is None:
        match = _JSON_REQUEST.match(text)
        if match:
            plan = ("json_parser", {"text": match.group("body").strip()})

    if plan is None:
        return DispatchResult(matched=False)

    tool_name, arguments = plan
    try:
        result = registry.invoke(
            tool_name,
            arguments,
            allowed_tools=allowed_tools,
            granted_permissions=granted_permissions,
            context=context,
        )
    except PermissionDeniedError as exc:
        # Not permitted is not the same as not applicable: say so, and let the
        # caller fall through to the model rather than silently succeeding.
        return DispatchResult(matched=False, tool=tool_name, error=exc.message)
    except ToolError as exc:
        return DispatchResult(matched=False, tool=tool_name, error=exc.message)

    if not result.ok:
        return DispatchResult(matched=False, tool=tool_name, arguments=arguments, result=result, error=result.error)

    return DispatchResult(
        matched=True,
        tool=tool_name,
        arguments=arguments,
        result=result,
        answer=result.display or str(result.value),
    )
