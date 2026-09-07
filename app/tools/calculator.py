"""Arithmetic without ``eval``.

The expression is parsed to an AST and walked with an explicit allow-list of
node types and functions. Anything not on the list is refused. There is no
name lookup, no attribute access, no call to anything but the named functions
below, and no way to reach a builtin.
"""

from __future__ import annotations

import ast
import math
from decimal import Decimal, DivisionByZero, InvalidOperation, getcontext

from app.core.errors import ToolError
from app.database.enums import RiskLevel
from app.tools.registry import PERM_COMPUTE, ToolResult, ToolSpec

getcontext().prec = 28

MAX_EXPRESSION_CHARS = 500
MAX_POWER = 1_000  # refuse 9**9**9 style resource exhaustion

ALLOWED_FUNCTIONS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": lambda *args: sum(args),
    "sqrt": math.sqrt,
    "floor": math.floor,
    "ceil": math.ceil,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "pow": pow,
}

ALLOWED_CONSTANTS = {"pi": math.pi, "e": math.e}

_BIN_OPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a**b,
}


def _to_number(value):
    if isinstance(value, bool):
        raise ToolError("booleans are not numbers here")
    if isinstance(value, (int, float, Decimal)):
        return value
    raise ToolError(f"unsupported value of type {type(value).__name__}")


def _eval_node(node: ast.AST):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ToolError("only numeric literals are allowed")
        return Decimal(str(node.value)) if isinstance(node.value, float) else node.value
    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise ToolError(f"operator {type(node.op).__name__} is not allowed")
        left, right = _to_number(_eval_node(node.left)), _to_number(_eval_node(node.right))
        if isinstance(node.op, ast.Pow) and abs(float(right)) > MAX_POWER:
            raise ToolError(f"exponent larger than {MAX_POWER} is refused")
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and float(right) == 0:
            raise ToolError("division by zero")
        if isinstance(left, Decimal) != isinstance(right, Decimal):
            left, right = Decimal(str(left)), Decimal(str(right))
        try:
            return op(left, right)
        except (DivisionByZero, InvalidOperation, ZeroDivisionError) as exc:
            raise ToolError(f"arithmetic error: {exc}") from exc
        except OverflowError as exc:
            raise ToolError("result is too large") from exc
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.USub):
            return -_to_number(_eval_node(node.operand))
        if isinstance(node.op, ast.UAdd):
            return +_to_number(_eval_node(node.operand))
        raise ToolError(f"unary {type(node.op).__name__} is not allowed")
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ToolError("only direct calls to named functions are allowed")
        function = ALLOWED_FUNCTIONS.get(node.func.id)
        if function is None:
            raise ToolError(f"function '{node.func.id}' is not allowed")
        if node.keywords:
            raise ToolError("keyword arguments are not allowed")
        args = [_eval_node(a) for a in node.args]
        try:
            return function(*[float(a) if isinstance(a, Decimal) else a for a in args])
        except (ValueError, TypeError, OverflowError) as exc:
            raise ToolError(f"{node.func.id}: {exc}") from exc
    if isinstance(node, ast.Name):
        if node.id in ALLOWED_CONSTANTS:
            return ALLOWED_CONSTANTS[node.id]
        raise ToolError(f"unknown name '{node.id}'")
    raise ToolError(f"expression element {type(node).__name__} is not allowed")


def evaluate(expression: str) -> Decimal | int | float:
    if not expression or not expression.strip():
        raise ToolError("empty expression")
    if len(expression) > MAX_EXPRESSION_CHARS:
        raise ToolError(f"expression longer than {MAX_EXPRESSION_CHARS} characters")
    cleaned = expression.strip().rstrip("=").replace("×", "*").replace("÷", "/").replace("^", "**")
    try:
        tree = ast.parse(cleaned, mode="eval")
    except SyntaxError as exc:
        raise ToolError(f"could not parse the expression: {exc.msg}") from exc
    return _eval_node(tree)


def _format(value) -> str:
    if isinstance(value, Decimal):
        normalised = value.normalize()
        text = format(normalised, "f")
        return text
    if isinstance(value, float):
        if value == int(value) and abs(value) < 1e15:
            return str(int(value))
        return repr(round(value, 12))
    return str(value)


def calculate(expression: str, **_ignored) -> ToolResult:
    try:
        value = evaluate(expression)
    except ToolError as exc:
        return ToolResult(ok=False, error=exc.message)
    display = _format(value)
    return ToolResult(
        ok=True,
        value=display,
        display=display,
        meta={"expression": expression.strip(), "engine": "ast-allowlist"},
    )


SPEC = ToolSpec(
    name="calculator",
    description=(
        "Evaluate an arithmetic expression exactly. Supports + - * / // % ** and the "
        "functions abs, round, min, max, sum, sqrt, floor, ceil, log, log10, exp, pow, "
        "and the constants pi and e. No variables, no code."
    ),
    permissions={PERM_COMPUTE},
    input_schema={
        "type": "object",
        "properties": {
            "expression": {"type": "string", "maxLength": MAX_EXPRESSION_CHARS},
        },
        "required": ["expression"],
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {"value": {"type": "string"}},
    },
    risk=RiskLevel.LOW,
    handler=calculate,
)
