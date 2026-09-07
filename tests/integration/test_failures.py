"""Failure injection (work order §31).

Every one of these simulates a component that is down, slow, or lying, and
asserts what the system does about it. The rule under test throughout: a
degraded component degrades the answer, it does not lose the request, and it
never quietly spends money it was not allowed to spend.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select

from app.core.errors import ProviderTimeoutError, ProviderUnavailableError
from app.database.enums import EscalationBlockReason, EscalationReason, Route
from app.database.models import CostRecord
from app.gateway.router import GatewayRequest
from app.local_ai.ollama_client import OllamaClient
from tests.fakes import HARD_MARKER

HARD = f"Explain the {HARD_MARKER} rule."


def ask(runtime, db, client, message=HARD, **kwargs):
    services = runtime.for_session(db, client.client_id)
    response = services.router.handle(GatewayRequest(message=message, client=client, **kwargs))
    db.flush()
    return response


class TestOllamaClientFailures:
    def _client(self, handler):
        return OllamaClient(
            "http://ollama",
            timeout=1.0,
            client=httpx.Client(transport=httpx.MockTransport(handler), base_url="http://ollama"),
        )

    def test_ollama_offline(self):
        def handler(_request):
            raise httpx.ConnectError("connection refused")

        client = self._client(handler)
        assert client.is_alive() is False
        assert client.list_models() == []
        with pytest.raises(ProviderUnavailableError):
            client.chat("m", [{"role": "user", "content": "hi"}])

    def test_ollama_timeout_is_distinct_from_unavailable(self):
        def handler(_request):
            raise httpx.ReadTimeout("too slow")

        with pytest.raises(ProviderTimeoutError):
            self._client(handler).chat("m", [{"role": "user", "content": "hi"}])

    def test_a_missing_model_is_reported(self):
        def handler(_request):
            return httpx.Response(404, text="model 'ghost' not found")

        with pytest.raises(ProviderUnavailableError, match="model missing"):
            self._client(handler).chat("ghost", [{"role": "user", "content": "hi"}])

    def test_a_server_error_is_reported(self):
        def handler(_request):
            return httpx.Response(500, text="internal error")

        with pytest.raises(ProviderUnavailableError):
            self._client(handler).chat("m", [{"role": "user", "content": "hi"}])

    def test_a_non_json_body_is_reported(self):
        def handler(_request):
            return httpx.Response(200, text="<html>a proxy error page</html>")

        with pytest.raises(ProviderUnavailableError, match="non-JSON"):
            self._client(handler).chat("m", [{"role": "user", "content": "hi"}])

    def test_a_malformed_message_is_reported(self):
        def handler(_request):
            return httpx.Response(200, json={"message": {"content": {"unexpected": "shape"}}})

        with pytest.raises(ProviderUnavailableError, match="malformed"):
            self._client(handler).chat("m", [{"role": "user", "content": "hi"}])


class TestLocalModelDown:
    def test_an_unavailable_local_model_escalates_with_the_right_reason(
        self, runtime, db, client_row, local_provider, paid_provider
    ):
        local_provider.unavailable = True
        response = ask(runtime, db, client_row, "What is the capital of France?")
        assert response.route is Route.PAID
        assert response.escalation_reason is EscalationReason.LOCAL_MODEL_UNAVAILABLE
        assert paid_provider.call_count == 1

    def test_a_local_timeout_is_reported_as_a_timeout_not_a_failure(
        self, runtime, db, client_row, local_provider
    ):
        local_provider.timeout = True
        response = ask(runtime, db, client_row, "What is the capital of France?")
        assert response.escalation_reason is EscalationReason.LOCAL_TIMEOUT

    def test_no_installed_model_is_reported(self, runtime, db, client_row, local_provider):
        local_provider.installed = False
        response = ask(runtime, db, client_row, "What is the capital of France?")
        assert response.escalation_reason is EscalationReason.LOCAL_MODEL_UNAVAILABLE

    def test_with_the_local_model_down_and_no_paid_provider_the_request_fails_honestly(
        self, runtime, db, client_row, local_provider, paid_provider
    ):
        local_provider.unavailable = True
        paid_provider.is_enabled = False
        response = ask(runtime, db, client_row, "What is the capital of France?")
        assert response.route is Route.FAILED
        assert response.success is False
        assert response.answer == ""
        assert response.escalation_blocked_reason is EscalationBlockReason.NOT_CONFIGURED
        assert response.notes, "a failed request must say why"


class TestPaidProviderFailures:
    def test_a_paid_provider_that_is_down_degrades_to_the_local_attempt(
        self, runtime, db, client_row, paid_provider
    ):
        paid_provider.fail = True
        response = ask(runtime, db, client_row)
        assert response.route is not Route.PAID
        assert response.escalation_blocked_reason is EscalationBlockReason.PROVIDER_FAILED
        assert response.success is False
        assert any("unverified" in note or "unavailable" in note for note in response.notes)

    def test_the_second_provider_is_tried_when_the_first_fails(
        self, runtime, db, client_row, settings, paid_provider
    ):
        from tests.fakes import FakePaidProvider

        settings.PAID_PROVIDER_ORDER = "anthropic,openai"
        backup = FakePaidProvider(name="openai", model="fake-openai")
        paid_provider.fail = True
        runtime.providers.register_paid(backup)

        response = ask(runtime, db, client_row)
        assert response.route is Route.PAID
        assert response.provider == "openai"
        assert backup.call_count == 1

    def test_a_paid_provider_returning_a_refusal_is_not_treated_as_an_answer(
        self, runtime, db, client_row, paid_provider
    ):
        paid_provider.answer = "I cannot help with that."
        response = ask(runtime, db, client_row)
        assert response.success is False
        assert response.solution_id is None

    def test_the_openai_provider_maps_http_errors(self, settings):
        from app.providers.base import CompletionRequest, Message
        from app.providers.openai_provider import OpenAIProvider

        settings.OPENAI_ENABLED = True
        settings.OPENAI_API_KEY = "sk-test"

        def handler(_request):
            return httpx.Response(429, json={"error": {"message": "rate limited"}})

        provider = OpenAIProvider(
            settings, client=httpx.Client(transport=httpx.MockTransport(handler), base_url="http://x")
        )
        with pytest.raises(ProviderUnavailableError):
            provider.complete(CompletionRequest(messages=[Message(role="user", content="hi")]))

    def test_the_anthropic_provider_maps_timeouts(self, settings):
        from app.providers.anthropic_provider import AnthropicProvider
        from app.providers.base import CompletionRequest, Message

        settings.ANTHROPIC_ENABLED = True
        settings.ANTHROPIC_API_KEY = "test"

        def handler(_request):
            raise httpx.ReadTimeout("slow")

        provider = AnthropicProvider(
            settings, client=httpx.Client(transport=httpx.MockTransport(handler), base_url="http://x")
        )
        with pytest.raises(ProviderTimeoutError):
            provider.complete(CompletionRequest(messages=[Message(role="user", content="hi")]))

    def test_a_provider_error_body_is_never_surfaced_to_the_caller(self, settings):
        """A 400 body can echo the prompt back; it must not reach the client."""
        from app.providers.base import CompletionRequest, Message
        from app.providers.openai_provider import OpenAIProvider

        settings.OPENAI_ENABLED = True
        settings.OPENAI_API_KEY = "sk-test"

        def handler(_request):
            return httpx.Response(400, json={"error": {"message": "your prompt was: SECRET"}})

        provider = OpenAIProvider(
            settings, client=httpx.Client(transport=httpx.MockTransport(handler), base_url="http://x")
        )
        with pytest.raises(ProviderUnavailableError) as caught:
            provider.complete(CompletionRequest(messages=[Message(role="user", content="hi")]))
        assert "SECRET" not in str(caught.value.detail)


class TestVectorStoreFailure:
    def test_a_retrieval_failure_degrades_the_answer_but_does_not_lose_the_request(
        self, runtime, db, client_row, monkeypatch
    ):
        services = runtime.for_session(db, client_row.client_id)

        def explode(*_args, **_kwargs):
            raise RuntimeError("qdrant is unreachable")

        monkeypatch.setattr(services.retriever, "retrieve", explode)
        response = services.router.handle(
            GatewayRequest(message="What is the capital of France?", client=client_row)
        )
        assert response.success is True
        assert response.memory_hit is False

    def test_an_embedding_failure_does_not_fail_retrieval(
        self, runtime, db, client_row, monkeypatch
    ):
        services = runtime.for_session(db, client_row.client_id)

        def explode(_texts):
            raise RuntimeError("embedding model is gone")

        monkeypatch.setattr(services.retriever.embedder, "embed", explode)
        result = services.retriever.retrieve("anything at all")
        assert result.items == []


class TestBudgetExhaustion:
    def test_when_the_budget_is_gone_the_system_keeps_working_locally(
        self, runtime, db, client_row, settings, paid_provider
    ):
        settings.AI_DAILY_API_BUDGET = 0.0
        hard = ask(runtime, db, client_row)
        easy = ask(runtime, db, client_row, "What is the capital of France?")
        tool = ask(runtime, db, client_row, "2 + 2")

        assert paid_provider.call_count == 0
        assert hard.escalation_blocked_reason is EscalationBlockReason.DAILY_BUDGET_EXHAUSTED
        assert easy.success is True and tool.success is True
        assert db.scalars(select(CostRecord)).all() == []

    def test_an_oversized_prompt_is_refused_before_it_is_sent(
        self, runtime, db, client_row, settings, paid_provider
    ):
        settings.AI_MAX_INPUT_TOKENS_PER_REQUEST = 10
        response = ask(runtime, db, client_row)
        assert paid_provider.call_count == 0
        assert response.escalation_blocked_reason is EscalationBlockReason.REQUEST_TOO_LARGE


class TestDatabaseFailure:
    def test_health_reports_the_database_as_down(self, runtime, settings, monkeypatch):
        from app.api.routes import health as health_module

        monkeypatch.setattr(
            health_module, "get_engine", lambda *_: (_ for _ in ()).throw(RuntimeError("no db"))
        )
        components = health_module._collect(runtime, settings)
        database = next(c for c in components if c.name == "database")
        assert database.status == "DOWN"
        assert health_module._overall(components) == "down"
