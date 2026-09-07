"""Task classification, escalation policy, model selection and agents."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.database.enums import (
    Classification,
    EscalationBlockReason,
    EscalationReason,
    Route,
    TaskType,
)
from app.gateway.escalation import may_escalate, why_escalate
from app.gateway.router import GatewayRequest
from app.gateway.task_classifier import classify
from app.local_ai.model_manager import ModelManager
from app.validation import validate_answer


class TestTaskClassifier:
    @pytest.mark.parametrize(
        "message,expected",
        [
            ("2+2", TaskType.ARITHMETIC),
            ("Summarise this contract", TaskType.SUMMARIZATION),
            ("Extract the totals from this invoice", TaskType.EXTRACTION),
            ("How many days between 2026-01-01 and 2026-03-01?", TaskType.DATE),
            ("Write a python function to parse dates", TaskType.CODE),
            ("Is this valid JSON: {}", TaskType.STRUCTURED_DATA),
            ("Classify this email as spam or not", TaskType.CLASSIFICATION),
            ("Compare the pros and cons of each option", TaskType.RESEARCH),
            ("Explain step by step why this fails", TaskType.REASONING),
            ("What is the capital of France?", TaskType.GENERAL),
        ],
    )
    def test_patterns(self, message, expected):
        assert classify(message).task_type is expected

    def test_a_caller_declaration_always_wins(self):
        result = classify("2+2", declared="summarization")
        assert result.task_type is TaskType.SUMMARIZATION and result.confidence == 1.0

    def test_an_unknown_declaration_is_ignored_not_an_error(self):
        assert classify("2+2", declared="nonsense").task_type is TaskType.ARITHMETIC

    def test_named_documents_force_document_qa(self):
        assert classify("anything", document_ids=["doc_1"]).task_type is TaskType.DOCUMENT_QA

    def test_general_is_a_valid_answer_not_a_failure(self):
        result = classify("tell me something interesting")
        assert result.task_type is TaskType.GENERAL and result.reason


class TestEscalationIntent:
    def _intent(self, **kwargs):
        defaults = dict(
            local_available=True,
            local_timed_out=False,
            local_failed=False,
            validation=None,
            had_context=False,
            task_needs_context=False,
            premium_requested=False,
            threshold=0.62,
        )
        defaults.update(kwargs)
        return why_escalate(**defaults)

    def test_a_passing_answer_does_not_escalate(self):
        good = validate_answer("The capital of France is Paris.", task_type="general")
        assert self._intent(validation=good).wanted is False

    def test_exactly_one_reason_is_returned(self):
        intent = self._intent(local_timed_out=True, local_failed=True, local_available=False)
        assert intent.reason is EscalationReason.LOCAL_TIMEOUT  # the more specific one

    def test_a_veto_is_a_validation_failure(self):
        bad = validate_answer("INSUFFICIENT_CONTEXT", task_type="general")
        assert self._intent(validation=bad).reason is EscalationReason.VALIDATION_FAILURE

    def test_a_source_backed_task_with_no_sources_is_a_knowledge_failure(self):
        bad = validate_answer("INSUFFICIENT_CONTEXT", task_type="document_qa")
        intent = self._intent(validation=bad, task_needs_context=True, had_context=False)
        assert intent.reason is EscalationReason.NO_KNOWLEDGE_FOUND

    def test_a_far_below_threshold_answer_is_task_too_complex(self):
        weak = validate_answer(
            "Maybe. I think possibly. I'm not sure. It might be. Hard to say.",
            task_type="document_qa",
        )
        intent = self._intent(validation=weak, threshold=0.9)
        assert intent.reason in (
            EscalationReason.TASK_TOO_COMPLEX,
            EscalationReason.LOW_CONFIDENCE,
        )

    def test_premium_is_only_honoured_when_the_caller_asked_and_it_is_allowed(self):
        assert self._intent(premium_requested=True).reason is (
            EscalationReason.USER_REQUESTED_PREMIUM_MODEL
        )


class TestEscalationPermission:
    def _permission(self, settings=None, **kwargs):
        defaults = dict(
            settings=settings or Settings(),
            classification=Classification.INTERNAL,
            task_type="general",
            client_may_escalate=True,
            client_max_classification="INTERNAL",
            any_paid_provider=True,
        )
        defaults.update(kwargs)
        return may_escalate(**defaults)

    def test_allowed_when_everything_lines_up(self):
        assert self._permission().allowed is True

    def test_disabled_escalation_blocks_everything(self):
        assert self._permission(settings=Settings(ESCALATION_ENABLED=False)).blocked_reason is (
            EscalationBlockReason.DISABLED
        )

    def test_no_provider_configured_blocks(self):
        assert self._permission(any_paid_provider=False).blocked_reason is (
            EscalationBlockReason.NOT_CONFIGURED
        )

    def test_a_denylisted_task_type_blocks(self):
        settings = Settings(PAID_TASK_DENYLIST="document_qa, extraction")
        assert self._permission(settings=settings, task_type="document_qa").blocked_reason is (
            EscalationBlockReason.TASK_TYPE_DENIED
        )

    def test_restricted_blocks_regardless_of_everything_else(self):
        assert self._permission(classification=Classification.RESTRICTED).blocked_reason is (
            EscalationBlockReason.CLASSIFICATION_BLOCKED
        )


class TestModelSelection:
    class _Fake:
        def __init__(self, models):
            self.models = models

        def list_models(self):
            return self.models

    def test_a_reasoning_task_gets_the_strong_model(self):
        manager = ModelManager(self._Fake(["llama3.2:3b", "qwen2.5:7b"]), Settings())
        assert manager.select(TaskType.REASONING) == "qwen2.5:7b"

    def test_a_trivial_task_gets_a_small_model(self):
        manager = ModelManager(self._Fake(["llama3.2:1b", "qwen2.5:7b"]), Settings())
        assert manager.select(TaskType.ARITHMETIC) == "llama3.2:1b"

    def test_it_degrades_rather_than_failing_when_the_wanted_class_is_missing(self):
        manager = ModelManager(self._Fake(["qwen2.5:7b"]), Settings())
        assert manager.select(TaskType.ARITHMETIC) == "qwen2.5:7b"

    def test_no_installed_model_returns_none_rather_than_a_guess(self):
        manager = ModelManager(self._Fake([]), Settings())
        assert manager.select(TaskType.GENERAL) is None
        assert manager.is_available() is False

    def test_a_requested_model_wins_when_it_is_installed(self):
        manager = ModelManager(self._Fake(["llama3.2:3b", "qwen2.5:7b"]), Settings())
        assert manager.select(TaskType.ARITHMETIC, requested="qwen2.5:7b") == "qwen2.5:7b"

    def test_a_requested_model_that_is_missing_falls_back(self):
        manager = ModelManager(self._Fake(["llama3.2:3b"]), Settings())
        assert manager.select(TaskType.GENERAL, requested="ghost:70b") == "llama3.2:3b"

    def test_the_report_distinguishes_exact_from_resolved(self):
        manager = ModelManager(self._Fake(["llama3.2:3b"]), Settings())
        row = next(r for r in manager.report() if r["role"] == "small")
        assert row["installed"] is False
        assert row["resolved_to"] == "llama3.2:3b"


class TestAgents:
    def test_an_agent_sets_the_default_task_type(self, runtime, db, client_row):
        from app.api.deps import AGENTS

        services = runtime.for_session(db, client_row.client_id)
        response = services.router.handle(
            GatewayRequest(
                message="What does it say?", client=client_row, agent=AGENTS.get("document")
            )
        )
        assert response.task_type is TaskType.DOCUMENT_QA
        assert response.agent == "document"

    def test_an_agents_system_prompt_is_added_to_the_base_rules_not_instead_of_them(
        self, runtime, db, client_row, local_provider
    ):
        from app.api.deps import AGENTS

        services = runtime.for_session(db, client_row.client_id)
        services.router.handle(
            GatewayRequest(
                message="Review this code", client=client_row, agent=AGENTS.get("developer")
            )
        )
        system = local_provider.calls[-1].messages[0].content
        assert "You are AI Helper" in system            # base rules survive
        assert "never claim to have made it" in system  # agent fragment added

    def test_an_agent_can_only_narrow_the_clients_tools(self, runtime, db, client_row):
        from app.agents import narrowed_tools
        from app.api.deps import AGENTS

        document_agent = AGENTS.get("document")
        assert "calculator" not in (narrowed_tools(document_agent, None) or [])
        assert narrowed_tools(document_agent, ["memory_search"]) == ["memory_search"]

    def test_an_agent_cannot_reach_a_tool_the_client_lacks(self, runtime, db):
        from app.agents import narrowed_tools
        from app.api.deps import AGENTS

        assert narrowed_tools(AGENTS.get("research"), ["calculator"]) == []


class TestRouteAccounting:
    def test_every_route_value_is_recorded_on_the_request_log(self, runtime, db, client_row):
        from sqlalchemy import select

        from app.database.models import RequestLog
        from tests.fakes import HARD_MARKER

        services = runtime.for_session(db, client_row.client_id)
        services.router.handle(GatewayRequest(message="2+2", client=client_row))
        services.router.handle(GatewayRequest(message="What is the capital of France?", client=client_row))
        services.router.handle(
            GatewayRequest(message=f"Explain the {HARD_MARKER} rule.", client=client_row)
        )
        db.flush()
        routes = {row.route for row in db.scalars(select(RequestLog))}
        assert routes == {Route.TOOL.value, Route.LOCAL.value, Route.PAID.value}

    def test_the_request_log_stores_a_fingerprint_not_the_question(self, runtime, db, client_row):
        from sqlalchemy import select

        from app.database.models import RequestLog

        services = runtime.for_session(db, client_row.client_id)
        services.router.handle(
            GatewayRequest(message="a very distinctive private question", client=client_row)
        )
        db.flush()
        row = db.scalars(select(RequestLog)).first()
        assert row.question_fingerprint
        assert "distinctive" not in str(row.__dict__)


class TestBlockReasonPrecedence:
    """A privacy block outranks a configuration block.

    "We did not send it because no provider is configured" is a far weaker
    statement than "we would never have sent it", and it changes meaning the
    day someone enables a provider. The audit trail must carry the stronger
    reason.
    """

    def _permission(self, **kwargs):
        defaults = dict(
            settings=Settings(),
            classification=Classification.RESTRICTED,
            task_type="general",
            client_may_escalate=True,
            client_max_classification="INTERNAL",
            any_paid_provider=False,
        )
        defaults.update(kwargs)
        return may_escalate(**defaults)

    def test_restricted_reports_the_privacy_block_even_with_no_provider(self):
        assert self._permission().blocked_reason is EscalationBlockReason.CLASSIFICATION_BLOCKED

    def test_restricted_reports_the_privacy_block_even_with_escalation_disabled(self):
        permission = self._permission(settings=Settings(ESCALATION_ENABLED=False))
        assert permission.blocked_reason is EscalationBlockReason.CLASSIFICATION_BLOCKED

    def test_a_forbidden_client_outranks_a_missing_provider(self):
        permission = self._permission(
            classification=Classification.INTERNAL, client_may_escalate=False
        )
        assert permission.blocked_reason is EscalationBlockReason.CLIENT_NOT_PERMITTED

    def test_configuration_reasons_still_surface_when_nothing_intrinsic_blocks(self):
        assert (
            self._permission(classification=Classification.INTERNAL).blocked_reason
            is EscalationBlockReason.NOT_CONFIGURED
        )
