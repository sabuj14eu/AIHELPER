"""Failure injection (work order §31).

Every one of these simulates a component that is down, slow, or lying, and
asserts what the system does about it. The rule under test throughout: a
degraded component degrades the answer, it does not lose the request, and it
never quietly spends money it was not allowed to spend.
"""

from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy import select

from app.core.errors import ProviderTimeoutError, ProviderUnavailableError
from app.database.enums import EscalationBlockReason, EscalationReason, Route
from app.database.models import CostRecord
from app.gateway.router import GatewayRequest
from app.local_ai.ollama_client import OllamaClient
from app.validation.states import AnswerState
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

    def _stream(self, chunks: list[dict], *, delay: float = 0.0):
        """A handler that answers /api/chat the way Ollama does: NDJSON frames.

        With ``delay`` the frames are yielded lazily, one every ``delay``
        seconds, so the client really does read a slow stream. A MockTransport
        that returns the whole body at once cannot exercise a wall-clock
        deadline -- the loop finishes before the clock moves.
        """
        import time as _t

        def handler(_request):
            def frames():
                for chunk in chunks:
                    if delay:
                        _t.sleep(delay)
                    yield (json.dumps(chunk) + "\n").encode()

            return httpx.Response(200, content=frames())

        return handler

    def test_a_completed_stream_is_reassembled_into_one_answer(self):
        chunks = [
            {"message": {"content": "Paris"}, "done": False},
            {"message": {"content": " is the"}, "done": False},
            {"message": {"content": " capital."}, "done": True, "done_reason": "stop",
             "model": "m", "prompt_eval_count": 12, "eval_count": 5},
        ]
        result = self._client(self._stream(chunks)).chat("m", [{"role": "user", "content": "hi"}])
        assert result["text"] == "Paris is the capital."
        assert result["finish_reason"] == "stop"
        assert result["input_tokens"] == 12 and result["output_tokens"] == 5

    def test_a_deadline_keeps_what_was_generated_instead_of_throwing_it_away(self):
        """The defect this whole change exists for.

        On the production box qwen generates at 5.35 tok/s. The blocking call
        meant an answer 900 tokens along when the clock ran out was lost
        exactly as completely as one that never started.
        """
        chunks = [{"message": {"content": f"word{i} "}, "done": False} for i in range(200)]
        client = OllamaClient(
            "http://ollama",
            timeout=0.3,
            client=httpx.Client(
                transport=httpx.MockTransport(self._stream(chunks, delay=0.01)),
                base_url="http://ollama",
            ),
        )
        result = client.chat("m", [{"role": "user", "content": "hi"}])
        assert result["text"].startswith("word0"), "the work done before the deadline is kept"
        assert result["finish_reason"] == "timeout"

    def test_a_deadline_with_nothing_generated_is_still_a_failure(self):
        """There is no partial answer to keep, so the router must still route on it."""
        client = OllamaClient(
            "http://ollama",
            timeout=0.3,
            client=httpx.Client(
                transport=httpx.MockTransport(self._stream([{"done": False}] * 200, delay=0.01)),
                base_url="http://ollama",
            ),
        )
        with pytest.raises(ProviderTimeoutError):
            client.chat("m", [{"role": "user", "content": "hi"}])

    def test_an_error_frame_mid_stream_is_reported(self):
        chunks = [{"message": {"content": "partial"}, "done": False}, {"error": "out of memory"}]
        with pytest.raises(ProviderUnavailableError, match="reported an error"):
            self._client(self._stream(chunks)).chat("m", [{"role": "user", "content": "hi"}])

    def test_the_model_is_held_in_memory_long_enough_to_matter(self):
        """Loading qwen2.5:7b was measured at 31.0 s, and it landed inside the
        request's own budget every time the model had been idle."""
        from app.local_ai.ollama_client import KEEP_ALIVE

        assert KEEP_ALIVE == "24h"

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
        # Not merely "there are notes": the note that matters is the one that
        # says what went wrong at level 2. Asserting only that the list is
        # non-empty is what let the cause go missing for a release.
        assert "fake local model is not running" in response.notes[0]

    def test_the_reason_there_is_no_answer_survives_the_escalation_blocked_note(
        self, runtime, db, client_row, local_provider, paid_provider
    ):
        """The owner's box: paid providers off, so a note always exists already.

        A blocked escalation explains what could not rescue the request; it does
        not explain why level 2 produced nothing. Both have to be on the
        response, and the cause has to come first.
        """
        local_provider.timeout = True
        paid_provider.is_enabled = False
        response = ask(runtime, db, client_row, "What is the capital of France?")
        assert response.route is Route.FAILED
        assert response.answer == ""
        assert "fake local model timed out" in response.notes[0]
        assert any("escalation blocked" in note for note in response.notes)

    def test_an_empty_local_answer_with_no_paid_provider_says_it_was_empty(
        self, runtime, db, client_row, local_provider, paid_provider
    ):
        local_provider.answer_override = "   "
        paid_provider.is_enabled = False
        response = ask(runtime, db, client_row, "What is the capital of France?")
        assert response.route is Route.FAILED
        assert response.notes[0] == "no answer: the local model returned an empty answer"


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


class TestTheFourStates:
    """A turn is one of four things, and only one of them is a fault.

    Before this, validation answered a boolean and the router turned it into
    "answer" or "route failed", so a careful answer that named its gaps, a
    report that the evidence does not exist, and a crashed model all reached
    the reader looking the same. These fix the difference.
    """

    def test_a_validated_answer_is_verified(self, runtime, db, client_row, local_provider):
        response = ask(runtime, db, client_row, "What is the capital of France?")
        assert response.state is AnswerState.VERIFIED
        assert response.success is True

    def test_a_model_that_lacks_evidence_is_insufficient_not_failed(
        self, runtime, db, client_row, local_provider, paid_provider
    ):
        """The outcome the constitution calls successful must not read as a fault."""
        local_provider.answer_override = (
            "I don't have enough information about the current structure to call this."
        )
        paid_provider.is_enabled = False
        response = ask(runtime, db, client_row, "What is the plan for gold today?")
        assert response.state is AnswerState.INSUFFICIENT
        assert response.route is Route.LOCAL
        assert response.answer, "an insufficiency report is an answer; it must reach the reader"
        assert any("not available" in note for note in response.notes)

    def test_the_insufficient_marker_is_insufficient_not_failed(
        self, runtime, db, client_row, local_provider, paid_provider
    ):
        local_provider.answer_override = "INSUFFICIENT_CONTEXT — the outlook board is missing."
        paid_provider.is_enabled = False
        response = ask(runtime, db, client_row, "What is the plan for gold today?")
        assert response.state is AnswerState.INSUFFICIENT
        assert response.answer

    def test_a_low_confidence_answer_is_useful_and_still_reaches_the_reader(
        self, runtime, db, client_row, local_provider, paid_provider
    ):
        # Enough hedging to land under the threshold without tripping a veto:
        # this is the "answered, but not confidently" case, not a refusal.
        local_provider.answer_override = (
            "I'm not sure. Possibly Paris, though I think it might be somewhere "
            "near there, probably."
        )
        paid_provider.is_enabled = False
        response = ask(runtime, db, client_row, "What is the capital of France?")
        assert response.state is AnswerState.USEFUL
        assert response.success is False, "useful is not verified; the bar has not moved"
        assert response.answer

    def test_a_dead_local_model_is_a_system_failure_that_names_itself(
        self, runtime, db, client_row, local_provider, paid_provider
    ):
        local_provider.timeout = True
        paid_provider.is_enabled = False
        response = ask(runtime, db, client_row, "What is the capital of France?")
        assert response.state is AnswerState.FAILED
        assert response.answer == ""
        assert "fake local model timed out" in response.notes[0]

    def test_a_withholding_veto_produces_failed_not_a_labelled_answer(self):
        """This case tightens the bar rather than relaxing it.

        An answer vetoed for contradicting its own sources used to be handed
        to the reader with an "unverified" note. There is no reading of that
        veto under which the text is worth showing.
        """
        from app.validation.confidence import ValidationReport
        from app.validation.states import derive_state, withholding_reason

        contradicted = ValidationReport(
            passed=False, confidence=0.2, vetoes=["contradicts_context"]
        )
        assert derive_state(has_text=True, validation=contradicted) is AnswerState.FAILED
        assert "contradicted" in withholding_reason(contradicted)

        lacking = ValidationReport(
            passed=False, confidence=0.2, vetoes=["model_lacks_evidence"]
        )
        assert derive_state(has_text=True, validation=lacking) is AnswerState.INSUFFICIENT
        assert withholding_reason(lacking) is None
