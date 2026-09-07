"""A first end-to-end pass over the ladder."""

from __future__ import annotations

from app.database.enums import Route
from app.gateway.router import GatewayRequest


def test_tool_answers_without_any_model(runtime, db, client_row, local_provider, paid_provider):
    services = runtime.for_session(db, client_row.client_id)
    response = services.router.handle(
        GatewayRequest(message="What is 1200 * 0.23?", client=client_row)
    )
    assert response.route is Route.TOOL
    assert response.answer == "276"
    assert local_provider.calls == []
    assert paid_provider.call_count == 0
    assert response.cost_usd == 0.0


def test_local_answers_an_easy_question(runtime, db, client_row, paid_provider):
    services = runtime.for_session(db, client_row.client_id)
    response = services.router.handle(
        GatewayRequest(message="What is the capital of France?", client=client_row)
    )
    assert response.route is Route.LOCAL
    assert "Paris" in response.answer
    assert paid_provider.call_count == 0
