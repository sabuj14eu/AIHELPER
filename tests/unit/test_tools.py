"""Tools: the calculator's sandbox, dates, JSON, and the registry's rules."""

from __future__ import annotations

import pytest

from app.core.errors import PermissionDeniedError, ToolError
from app.database.enums import RiskLevel
from app.tools.calculator import calculate
from app.tools.dates import date_calculate
from app.tools.dispatcher import try_dispatch
from app.tools.json_tools import json_process
from app.tools.registry import ToolRegistry, ToolResult, ToolSpec, validate_against_schema


class TestCalculator:
    @pytest.mark.parametrize(
        "expression,expected",
        [
            ("2+2", "4"),
            ("1200 * 0.23", "276"),
            ("(5+5)/2", "5"),
            ("2**10", "1024"),
            ("sqrt(16)", "4"),
            ("round(3.7)", "4"),
            ("min(3, 9)", "3"),
            ("17 % 5", "2"),
            ("-4 + 10", "6"),
            ("5203.80 * 0.0976", "507.89088"),
        ],
    )
    def test_arithmetic(self, expression, expected):
        result = calculate(expression)
        assert result.ok and result.value == expected

    def test_decimal_money_arithmetic_is_exact(self):
        """0.1 + 0.2 must be 0.3 — this is why the engine uses Decimal."""
        assert calculate("0.1 + 0.2").value == "0.3"

    @pytest.mark.parametrize(
        "attack",
        [
            "__import__('os').system('ls')",
            "open('/etc/passwd')",
            "exec('x=1')",
            "eval('1')",
            "().__class__",
            "[x for x in range(10)]",
            "lambda: 1",
            "print(1)",
            "globals()",
            "1 if True else 2",
            "x := 5",
        ],
    )
    def test_nothing_but_arithmetic_runs(self, attack):
        assert calculate(attack).ok is False

    @pytest.mark.parametrize("expression", ["9**9**9", "2**5000", "1/0", "10 % 0", "sqrt(-1)"])
    def test_dangerous_or_impossible_arithmetic_is_refused(self, expression):
        assert calculate(expression).ok is False

    def test_an_oversized_expression_is_refused(self):
        assert calculate("1+" * 400 + "1").ok is False

    def test_an_empty_expression_is_refused(self):
        assert calculate("   ").ok is False


class TestDates:
    def test_difference(self):
        assert date_calculate("difference", start="2026-01-01", end="2026-03-01").value == "59"

    def test_month_addition_clamps_rather_than_overflowing(self):
        assert date_calculate("add", start="2026-01-31", amount=1, unit="months").value == "2026-02-28"

    def test_leap_year(self):
        assert date_calculate("end_of_month", start="2024-02-05").value == "2024-02-29"
        assert date_calculate("add", start="2024-02-29", amount=1, unit="years").value == "2025-02-28"

    def test_weekday(self):
        result = date_calculate("weekday", start="2026-09-07")
        assert result.value == "Monday" and result.meta["is_weekend"] is False

    @pytest.mark.parametrize("bad", ["07/09/2026", "not-a-date", "2026-13-01"])
    def test_a_bad_date_is_an_error_not_a_guess(self, bad):
        assert date_calculate("weekday", start=bad).ok is False

    def test_missing_arguments_are_reported(self):
        assert date_calculate("difference", start="2026-01-01").ok is False


class TestJson:
    def test_parse_and_path(self):
        assert json_process('{"a":{"b":[1,2,3]}}', path="a.b.1").value == "2"

    def test_a_parse_error_names_the_position(self):
        result = json_process("{bad}")
        assert result.ok is False and "line 1" in result.error

    def test_a_missing_path_is_an_error(self):
        assert json_process('{"a":1}', path="b.c").ok is False

    def test_an_oversized_document_is_refused(self):
        assert json_process("[" + "1," * 200_000 + "1]").ok is False


class TestRegistry:
    def _spec(self, name="probe", **kwargs):
        defaults = dict(
            description="a probe tool",
            permissions={"tool:compute"},
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            risk=RiskLevel.LOW,
            handler=lambda **_: ToolResult(ok=True, value="x"),
        )
        defaults.update(kwargs)
        return ToolSpec(name=name, **defaults)

    def test_a_tool_without_permissions_is_refused(self):
        registry = ToolRegistry()
        with pytest.raises(ToolError):
            registry.register(self._spec(permissions=set()))

    def test_a_tool_without_schemas_is_refused(self):
        registry = ToolRegistry()
        with pytest.raises(ToolError):
            registry.register(self._spec(input_schema={}))

    def test_duplicate_registration_is_refused(self):
        registry = ToolRegistry()
        registry.register(self._spec())
        with pytest.raises(ToolError):
            registry.register(self._spec())

    def test_an_unknown_tool_is_refused(self):
        with pytest.raises(ToolError):
            ToolRegistry().invoke("nope", {})

    def test_a_missing_permission_is_refused(self):
        registry = ToolRegistry()
        registry.register(self._spec(permissions={"tool:network"}))
        with pytest.raises(PermissionDeniedError):
            registry.invoke("probe", {}, granted_permissions={"tool:compute"})

    def test_a_handler_that_raises_becomes_a_failed_result_not_a_crash(self):
        def explode(**_):
            raise RuntimeError("boom")

        registry = ToolRegistry()
        registry.register(self._spec(handler=explode))
        result = registry.invoke("probe", {})
        assert result.ok is False and "RuntimeError" in result.error


class TestSchemaValidation:
    def test_types_are_enforced(self):
        with pytest.raises(ToolError):
            validate_against_schema({"n": "x"}, {"type": "object", "properties": {"n": {"type": "number"}}})

    def test_a_boolean_is_not_a_number(self):
        with pytest.raises(ToolError):
            validate_against_schema(True, {"type": "number"})

    def test_required_properties_are_enforced(self):
        with pytest.raises(ToolError):
            validate_against_schema({}, {"type": "object", "required": ["a"], "properties": {"a": {}}})

    def test_unexpected_properties_are_refused(self):
        schema = {"type": "object", "properties": {"a": {}}, "additionalProperties": False}
        with pytest.raises(ToolError):
            validate_against_schema({"a": 1, "b": 2}, schema)

    def test_bounds_and_enums_are_enforced(self):
        with pytest.raises(ToolError):
            validate_against_schema(11, {"type": "integer", "maximum": 10})
        with pytest.raises(ToolError):
            validate_against_schema("z", {"type": "string", "enum": ["a", "b"]})
        with pytest.raises(ToolError):
            validate_against_schema("toolong", {"type": "string", "maxLength": 3})


class TestDispatcher:
    def test_it_declines_anything_ambiguous(self, runtime):
        for message in [
            "Explain VAT to me",
            "What is the capital of France?",
            "5",
            "Summarise this: 2+2 is easy",
            "Tell me about the year 2026",
        ]:
            assert try_dispatch(message, runtime.tools).matched is False, message

    def test_it_fires_only_on_unambiguous_shapes(self, runtime):
        for message, expected in [
            ("2+2", "4"),
            ("What is 1200 * 0.23?", "276"),
            ("How many days between 2026-01-01 and 2026-03-01?", "59 days"),
            ("What weekday is 2026-09-07?", "Monday"),
        ]:
            result = try_dispatch(message, runtime.tools)
            assert result.matched and result.answer == expected, message
