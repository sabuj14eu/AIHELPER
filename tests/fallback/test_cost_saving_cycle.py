"""The cost-saving regression test (work order §33) — the one that matters most.

    Question A -> local fails -> API solves -> solution saved and promoted
    Question A again -> retrieval finds it -> local succeeds -> API NOT called

Nothing here is stubbed except the two providers. The retrieval, validation,
capture, promotion and routing are the production code paths.
"""

from __future__ import annotations

import pytest

from app.database.enums import EscalationReason, Route, SolutionStatus
from app.gateway.router import GatewayRequest
from app.learning.solution_store import SolutionStore
from tests.fakes import HARD_MARKER

HARD_QUESTION = f"Explain the {HARD_MARKER} rule and when it applies."
# Deliberately NOT a normalisation-equivalent of HARD_QUESTION: different
# wording and word order, so this exercises vector similarity rather than the
# exact fingerprint path. The test asserts exact_match is False for that reason.
SIMILAR_QUESTION = f"When does the {HARD_MARKER} rule apply, and what exactly does it say?"


@pytest.fixture
def first_pass(runtime, db, client_row, paid_provider):
    services = runtime.for_session(db, client_row.client_id)
    response = services.router.handle(GatewayRequest(message=HARD_QUESTION, client=client_row))
    db.flush()
    return services, response


def test_first_time_the_local_model_fails_and_the_api_answers(first_pass, paid_provider):
    _, response = first_pass
    assert response.route is Route.PAID
    assert paid_provider.call_count == 1
    assert response.escalation_reason is EscalationReason.VALIDATION_FAILURE
    assert response.cost_usd > 0
    assert response.answer == paid_provider.answer


def test_the_answer_is_stored_and_promoted(first_pass, db, client_row):
    _, response = first_pass
    assert response.solution_id is not None
    solution = SolutionStore(db, client_row.client_id).get(response.solution_id)
    assert solution is not None
    assert solution.status == SolutionStatus.PROMOTED.value
    assert solution.reproduction.get("passed") is True
    assert solution.failure_reason == EscalationReason.VALIDATION_FAILURE.value


def test_the_same_question_is_then_answered_locally_with_no_paid_call(
    first_pass, runtime, db, client_row, paid_provider
):
    calls_after_first = paid_provider.call_count
    services = runtime.for_session(db, client_row.client_id)
    second = services.router.handle(GatewayRequest(message=HARD_QUESTION, client=client_row))

    assert second.route is Route.LOCAL, f"expected a local answer, got {second.route}"
    assert paid_provider.call_count == calls_after_first, "the paid provider was called again"
    assert second.cost_usd == 0.0
    assert second.memory_hit is True
    assert second.solution_id is not None
    assert second.retrieval["exact_match"] is True


def test_a_paraphrase_is_also_answered_locally(
    first_pass, runtime, db, client_row, paid_provider
):
    """The vector path, not the fingerprint path."""
    from app.learning.similarity import fingerprint

    assert fingerprint(SIMILAR_QUESTION) != fingerprint(HARD_QUESTION), (
        "the paraphrase normalises to the same string as the original, so this test "
        "would be exercising the exact-match path instead of vector similarity"
    )
    calls_after_first = paid_provider.call_count
    services = runtime.for_session(db, client_row.client_id)
    second = services.router.handle(GatewayRequest(message=SIMILAR_QUESTION, client=client_row))

    assert second.route is Route.LOCAL
    assert paid_provider.call_count == calls_after_first
    assert second.memory_hit is True
    assert second.retrieval["exact_match"] is False
    assert second.retrieval["solution_score"] > 0


def test_the_reuse_is_counted(first_pass, runtime, db, client_row):
    services = runtime.for_session(db, client_row.client_id)
    services.router.handle(GatewayRequest(message=HARD_QUESTION, client=client_row))
    services.router.handle(GatewayRequest(message=HARD_QUESTION, client=client_row))
    db.flush()
    _, first = first_pass
    solution = SolutionStore(db, client_row.client_id).get(first.solution_id)
    assert solution.reuse_count == 2
