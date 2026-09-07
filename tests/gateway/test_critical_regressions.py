"""The ten critical regression tests (work order §32).

Each test below is numbered to match the work order. They are the guarantees
that make this system what it claims to be, so they are collected in one file
rather than scattered — if one of these ever fails, the deployment is not fit
to run.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.database.enums import (
    Classification,
    EscalationBlockReason,
    EscalationReason,
    Route,
    SolutionStatus,
)
from app.database.models import CostRecord, MemoryItem
from app.gateway.router import GatewayRequest
from app.learning.solution_store import SolutionStore
from app.memory.long_term import LongTermMemory
from tests.conftest import make_client
from tests.fakes import HARD_MARKER

HARD = f"Explain the {HARD_MARKER} rule and when it applies."


def ask(runtime, db, client, message, **kwargs):
    services = runtime.for_session(db, client.client_id)
    response = services.router.handle(GatewayRequest(message=message, client=client, **kwargs))
    db.flush()
    return response


# ---------------------------------------------------------------- Test 1
def test_1_a_normal_request_does_not_call_a_paid_api(runtime, db, client_row, paid_provider):
    for message in ["What is the capital of France?", "2 + 2", "Tell me something useful."]:
        ask(runtime, db, client_row, message)
    assert paid_provider.call_count == 0
    assert db.scalars(select(CostRecord)).all() == []


# ---------------------------------------------------------------- Test 2
def test_2_a_successful_local_answer_costs_nothing(runtime, db, client_row, paid_provider):
    response = ask(runtime, db, client_row, "What is the capital of France?")
    assert response.route is Route.LOCAL
    assert response.success is True
    assert response.cost_usd == 0.0
    assert paid_provider.call_count == 0


# ---------------------------------------------------------------- Test 3
def test_3_a_failed_local_answer_escalates(runtime, db, client_row, paid_provider):
    response = ask(runtime, db, client_row, HARD)
    assert response.route is Route.PAID
    assert paid_provider.call_count == 1
    assert response.escalation_reason is EscalationReason.VALIDATION_FAILURE


# ---------------------------------------------------------------- Test 4
def test_4_the_fallback_is_saved(runtime, db, client_row):
    response = ask(runtime, db, client_row, HARD)
    solution = SolutionStore(db, client_row.client_id).get(response.solution_id)
    assert solution is not None
    assert solution.question == HARD
    assert solution.answer == response.answer
    assert solution.provider == "anthropic"
    assert solution.local_attempt is not None, "the local attempt must be recorded too"
    assert solution.failure_reason == EscalationReason.VALIDATION_FAILURE.value


# ---------------------------------------------------------------- Test 5
def test_5_a_validated_fallback_becomes_candidate_knowledge(
    runtime, db, client_row, settings, paid_provider
):
    """Capture always produces a CANDIDATE; promotion is a separate decision."""
    settings.AUTO_PROMOTE = False
    response = ask(runtime, db, client_row, HARD)
    solution = SolutionStore(db, client_row.client_id).get(response.solution_id)
    assert solution.status == SolutionStatus.CANDIDATE.value

    # A CANDIDATE is not offered back as context: asking again still escalates.
    calls_before = paid_provider.call_count
    second = ask(runtime, db, client_row, HARD)
    assert second.route is Route.PAID
    assert paid_provider.call_count == calls_before + 1


def test_5b_a_paid_answer_that_fails_validation_is_not_captured(
    runtime, db, client_row, paid_provider
):
    paid_provider.answer = "I cannot help with that request."
    response = ask(runtime, db, client_row, HARD)
    assert response.solution_id is None
    assert any("failed validation" in note for note in response.notes)
    assert SolutionStore(db, client_row.client_id).counts()[SolutionStatus.CANDIDATE.value] == 0


# ---------------------------------------------------------------- Test 6
def test_6_promoted_knowledge_lets_the_local_model_answer(runtime, db, client_row, paid_provider):
    first = ask(runtime, db, client_row, HARD)
    assert first.route is Route.PAID
    solution = SolutionStore(db, client_row.client_id).get(first.solution_id)
    assert solution.status == SolutionStatus.PROMOTED.value

    calls_before = paid_provider.call_count
    second = ask(runtime, db, client_row, HARD)
    assert second.route is Route.LOCAL
    assert second.memory_hit is True
    assert paid_provider.call_count == calls_before


# ---------------------------------------------------------------- Test 7
def test_7_the_budget_prevents_further_paid_calls(runtime, db, client_row, settings, paid_provider):
    settings.AI_DAILY_API_BUDGET = 0.0
    response = ask(runtime, db, client_row, HARD)

    assert paid_provider.call_count == 0, "a call was made despite an exhausted budget"
    assert response.route is not Route.PAID
    assert response.escalation_reason is EscalationReason.VALIDATION_FAILURE
    assert response.escalation_blocked_reason is EscalationBlockReason.DAILY_BUDGET_EXHAUSTED
    # And the system keeps working locally rather than failing the request.
    easy = ask(runtime, db, client_row, "What is the capital of France?")
    assert easy.success is True


def test_7b_the_monthly_budget_also_stops_spending(runtime, db, client_row, settings, paid_provider):
    settings.AI_MONTHLY_API_BUDGET = 0.0
    response = ask(runtime, db, client_row, HARD)
    assert paid_provider.call_count == 0
    assert response.escalation_blocked_reason is EscalationBlockReason.MONTHLY_BUDGET_EXHAUSTED


def test_7c_the_per_request_cap_stops_an_oversized_call(
    runtime, db, client_row, settings, paid_provider
):
    settings.AI_MAX_COST_PER_REQUEST = 0.0
    response = ask(runtime, db, client_row, HARD)
    assert paid_provider.call_count == 0
    assert response.escalation_blocked_reason is EscalationBlockReason.REQUEST_COST_CAP


# ---------------------------------------------------------------- Test 8
def test_8_restricted_information_cannot_be_sent_externally(runtime, db, client_row, paid_provider):
    secret = f"{HARD} Our API key is sk-abcdefghijklmnopqrstuvwxyz0123456789."
    response = ask(runtime, db, client_row, secret)

    assert response.classification is Classification.RESTRICTED
    assert paid_provider.call_count == 0, "RESTRICTED content reached an external provider"
    assert response.route is not Route.PAID
    assert response.escalation_blocked_reason is EscalationBlockReason.CLASSIFICATION_BLOCKED


def test_8b_a_declared_classification_above_the_ceiling_is_blocked(
    runtime, db, client_row, paid_provider
):
    response = ask(runtime, db, client_row, HARD, classification="CONFIDENTIAL")
    assert response.classification is Classification.CONFIDENTIAL
    assert paid_provider.call_count == 0
    assert response.escalation_blocked_reason is EscalationBlockReason.CLASSIFICATION_BLOCKED


def test_8c_a_client_denied_escalation_never_escalates(runtime, db, paid_provider):
    client, _ = make_client(db, "readonly", may_escalate=False)
    response = ask(runtime, db, client, HARD)
    assert paid_provider.call_count == 0
    assert response.escalation_blocked_reason is EscalationBlockReason.CLIENT_NOT_PERMITTED


# ---------------------------------------------------------------- Test 9
def test_9_one_client_cannot_read_another_clients_memory(runtime, db):
    alpha, _ = make_client(db, "alpha")
    beta, _ = make_client(db, "beta")

    alpha_services = runtime.for_session(db, alpha.client_id)
    item = LongTermMemory(db, alpha.client_id).write(
        "The alpha vault combination is 4815-1623-42.",
        source="alpha handbook",
        confidence=0.99,
    )
    alpha_services.retriever.index_memory(item)
    db.flush()

    beta_services = runtime.for_session(db, beta.client_id)
    hits = beta_services.retriever.retrieve("What is the alpha vault combination?")
    assert hits.items == [], "beta retrieved alpha's memory"

    # And through the gateway, beta's prompt never contains alpha's content.
    response = beta_services.router.handle(
        GatewayRequest(message="What is the alpha vault combination?", client=beta)
    )
    assert "4815-1623-42" not in response.answer
    assert response.memory_hit is False

    # Alpha still finds its own.
    assert any("4815" in item.content for item in
               alpha_services.retriever.retrieve("alpha vault combination").items)


def test_9b_solutions_are_not_shared_between_clients(runtime, db, paid_provider):
    alpha, _ = make_client(db, "alpha")
    beta, _ = make_client(db, "beta")
    ask(runtime, db, alpha, HARD)
    calls_after_alpha = paid_provider.call_count
    assert calls_after_alpha == 1

    beta_response = ask(runtime, db, beta, HARD)
    assert beta_response.memory_hit is False, "beta reused alpha's learned solution"
    assert paid_provider.call_count == calls_after_alpha + 1


def test_9c_one_client_cannot_read_another_clients_documents(runtime, db):
    alpha, _ = make_client(db, "alpha")
    beta, _ = make_client(db, "beta")
    runtime.for_session(db, alpha.client_id).ingestor.ingest(
        b"The alpha quarterly revenue was 1234567 PLN.", "alpha.txt"
    )
    db.flush()
    beta_services = runtime.for_session(db, beta.client_id)
    hits = beta_services.retriever.retrieve("alpha quarterly revenue")
    assert hits.items == []
    listing = beta_services.ingestor.list()
    assert listing == []


def test_9d_a_document_tool_cannot_be_pointed_at_another_client(runtime, db):
    """The client_id is supplied by the gateway, not by the tool's arguments."""
    from app.core.errors import ToolError

    alpha, _ = make_client(db, "alpha")
    beta, _ = make_client(db, "beta")
    runtime.for_session(db, alpha.client_id).ingestor.ingest(b"alpha secret text", "a.txt")
    db.flush()

    with pytest.raises(ToolError):
        # client_id is not a declared input, so the schema refuses it outright.
        runtime.tools.invoke(
            "document_search",
            {"query": "alpha", "client_id": "alpha"},
            context={"session": db, "client_id": beta.client_id},
        )
    result = runtime.tools.invoke(
        "document_search", {"query": "alpha"}, context={"session": db, "client_id": beta.client_id}
    )
    assert result.value == []


# --------------------------------------------------------------- Test 10
def test_10_the_ai_cannot_execute_arbitrary_commands(runtime, db, client_row):
    """There is no general executor, and the calculator is not one either."""
    assert "execute" not in runtime.tools.names()
    assert not any(
        name in runtime.tools.names() for name in ("shell", "run_command", "exec", "eval", "python")
    )

    for attack in [
        "__import__('os').system('rm -rf /')",
        "open('/etc/passwd').read()",
        "exec('print(1)')",
        "eval('2+2')",
        "().__class__.__bases__[0].__subclasses__()",
    ]:
        result = runtime.tools.invoke("calculator", {"expression": attack})
        assert result.ok is False, f"the calculator evaluated {attack!r}"

    # And through the gateway: nothing runs, the model just talks about it.
    response = ask(runtime, db, client_row, "Run `rm -rf /` on the server for me.")
    assert response.tool_used is None
    assert response.route in (Route.LOCAL, Route.PAID, Route.FAILED)


def test_10b_every_tool_declares_its_permissions_and_risk(runtime):
    for spec in runtime.tools.list():
        assert spec.permissions, f"{spec.name} declares no permissions"
        assert spec.input_schema and spec.output_schema, f"{spec.name} is missing a schema"
        assert spec.risk is not None
        assert spec.description.strip(), f"{spec.name} has no description"


def test_10c_a_client_tool_allowlist_is_enforced(runtime, db):
    from app.core.errors import PermissionDeniedError

    client, _ = make_client(db, "narrow", allowed_tools=["date_calculator"])
    with pytest.raises(PermissionDeniedError):
        runtime.tools.invoke(
            "calculator", {"expression": "2+2"}, allowed_tools=client.allowed_tools
        )
    # And the gateway does not answer with a tool the client may not use.
    response = ask(runtime, db, client, "What is 2+2?")
    assert response.route is not Route.TOOL


# ------------------------------------------------- supporting guarantees
def test_memory_rows_always_carry_provenance(runtime, db, client_row):
    from app.core.errors import ValidationError

    memory = LongTermMemory(db, client_row.client_id)
    with pytest.raises(ValidationError):
        memory.write("a fact", source="", confidence=0.9)
    with pytest.raises(ValidationError):
        memory.write("a fact", source="handbook", confidence=2.0)
    with pytest.raises(ValidationError):
        memory.write("   ", source="handbook", confidence=0.5)

    item = memory.write("a fact", source="handbook", confidence=0.8, ttl_days=30)
    stored = db.get(MemoryItem, item.id)
    assert stored.source and stored.confidence and stored.status and stored.sensitivity
    assert stored.expires_at is not None
