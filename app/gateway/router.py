"""The Gateway router.

Every AI request in the system goes through :meth:`GatewayRouter.handle`, and
it walks exactly one ladder:

  level 0  deterministic tools ................ zero tokens, zero cost
  level 1  memory and knowledge retrieval ..... zero tokens, zero cost
  level 2  the local model, with that context . local compute, zero cost
  level 3  validation ........................ decides whether we are done
  level 4  a paid provider .................... only if levels 0-3 could not,
                                                and only if allowed to

Two rules shape the code more than anything else:

* **Local first is not a preference, it is the control flow.** There is no
  branch that reaches level 4 without having tried and failed at levels 0-3,
  except the explicit "the caller asked for a premium model" path, which is
  itself off by default.
* **No application-specific business logic lives here.** No accounting rules,
  no trading rules, no per-client special cases. Clients differ only in their
  permissions, budgets and namespaces — all of which are data.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.agents.base import AgentSpec, narrowed_tools
from app.core.audit import CHAT_REQUEST, record
from app.core.config import Settings
from app.core.errors import ProviderTimeoutError, ProviderUnavailableError
from app.core.ids import new_request_id
from app.core.logging import client_id_var, get_logger, request_id_var
from app.cost.tracker import CostTracker
from app.database.enums import (
    Classification,
    EscalationBlockReason,
    EscalationReason,
    Route,
    TaskType,
)
from app.database.models import Client, RequestLog
from app.gateway import task_classifier
from app.gateway.escalation import may_escalate, why_escalate
from app.gateway.provider_manager import PaidProviderManager
from app.learning.fallback_capture import capture
from app.learning.promotion import PromotionPipeline
from app.learning.similarity import fingerprint
from app.local_ai.prompts import build_system_prompt, build_user_prompt
from app.memory.retrieval import RetrievalResult, Retriever
from app.memory.short_term import ShortTermMemory
from app.privacy.classification import classify as classify_sensitivity
from app.providers.base import CompletionRequest, CompletionResponse, Message, Provider
from app.providers.provider_registry import ProviderRegistry
from app.tools.dispatcher import try_dispatch
from app.tools.registry import ToolRegistry
from app.validation import ValidationReport, validate_answer
from app.validation.safety import check_input

log = get_logger("gateway")

# Task types whose answers are supposed to come from sources.
CONTEXT_TASKS = {TaskType.DOCUMENT_QA, TaskType.RESEARCH, TaskType.EXTRACTION}


def _system_prompt(task_type: TaskType, response_format: str, agent: AgentSpec | None) -> str:
    """Base rules first; an agent may add to them, never replace them."""
    prompt = build_system_prompt(task_type, response_format)
    if agent is not None and agent.system_prompt:
        prompt = f"{prompt}\n\n{agent.system_prompt}"
    return prompt


@dataclass
class GatewayRequest:
    message: str
    client: Client
    task_type: str | None = None
    conversation_id: str | None = None
    document_ids: list[str] = field(default_factory=list)
    namespace: str | None = None
    classification: str | None = None
    response_format: str = "text"
    model: str | None = None
    premium: bool = False
    user_ref: str | None = None
    max_tokens: int | None = None
    store_conversation: bool = True
    # An agent narrows: it may set a default task type, add a system-prompt
    # fragment and restrict tools. It can never widen what the client may do.
    agent: AgentSpec | None = None


@dataclass
class GatewayResponse:
    request_id: str
    answer: str
    route: Route
    task_type: TaskType
    classification: Classification
    provider: str | None = None
    model: str | None = None
    confidence: float | None = None
    memory_hit: bool = False
    tool_used: str | None = None
    escalation_reason: EscalationReason | None = None
    escalation_blocked_reason: EscalationBlockReason | None = None
    cost_usd: float = 0.0
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    conversation_id: str | None = None
    solution_id: str | None = None
    agent: str | None = None
    success: bool = True
    validation: dict = field(default_factory=dict)
    retrieval: dict = field(default_factory=dict)
    sources: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "answer": self.answer,
            "route": self.route.value,
            "task_type": self.task_type.value,
            "classification": self.classification.value,
            "provider": self.provider,
            "model": self.model,
            "confidence": round(self.confidence, 3) if self.confidence is not None else None,
            "memory_hit": self.memory_hit,
            "tool_used": self.tool_used,
            "escalation_reason": self.escalation_reason.value if self.escalation_reason else None,
            "escalation_blocked_reason": (
                self.escalation_blocked_reason.value if self.escalation_blocked_reason else None
            ),
            "cost_usd": round(self.cost_usd, 6),
            "latency_ms": self.latency_ms,
            "tokens": {"input": self.input_tokens, "output": self.output_tokens},
            "conversation_id": self.conversation_id,
            "solution_id": self.solution_id,
            "agent": self.agent,
            "success": self.success,
            "sources": self.sources,
            "validation": self.validation,
            "retrieval": self.retrieval,
            "notes": self.notes,
        }


class GatewayRouter:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings,
        registry: ProviderRegistry,
        tools: ToolRegistry,
        retriever: Retriever,
        cost_tracker: CostTracker | None = None,
    ):
        self.session = session
        self.settings = settings
        self.registry = registry
        self.tools = tools
        self.retriever = retriever
        self.cost = cost_tracker or CostTracker(session, settings)
        self.paid = PaidProviderManager(session, settings, self.cost)

    # ================================================================ public
    def handle(self, request: GatewayRequest) -> GatewayResponse:
        started = time.perf_counter()
        request_id = new_request_id()
        request_id_var.set(request_id)
        client_id_var.set(request.client.client_id)

        response = self._handle(request, request_id)
        response.latency_ms = int((time.perf_counter() - started) * 1000)
        self._log_request(request, response)
        return response

    # =============================================================== private
    def _handle(self, request: GatewayRequest, request_id: str) -> GatewayResponse:
        client = request.client
        message = (request.message or "").strip()

        # ---- input safety and size -------------------------------------
        input_safety = check_input(message, max_chars=self.settings.MAX_REQUEST_CHARS)
        if input_safety.oversized:
            return GatewayResponse(
                request_id=request_id,
                answer="",
                route=Route.FAILED,
                task_type=TaskType.GENERAL,
                classification=Classification.INTERNAL,
                success=False,
                notes=input_safety.findings,
            )

        # ---- classification of sensitivity ------------------------------
        sensitivity = classify_sensitivity(
            message,
            declared=request.classification,
            client_default=client.default_classification,
        )
        classification = sensitivity.classification

        # ---- classification of the task ---------------------------------
        has_documents = bool(request.document_ids) or self._client_has_documents(client.client_id)
        declared_task = request.task_type
        if not declared_task and request.agent is not None:
            declared_task = request.agent.default_task_type.value
        task = task_classifier.classify(
            message,
            declared=declared_task,
            has_documents=has_documents,
            document_ids=request.document_ids,
        )
        task_type = task.task_type
        allowed_tools = narrowed_tools(request.agent, client.allowed_tools) if request.agent else client.allowed_tools

        base = GatewayResponse(
            request_id=request_id,
            answer="",
            route=Route.FAILED,
            task_type=task_type,
            classification=classification,
            success=False,
            agent=request.agent.name if request.agent else None,
        )
        if input_safety.injection_suspected:
            base.notes.append("request flagged for possible prompt injection")

        # ---- conversation memory ----------------------------------------
        short_term = ShortTermMemory(self.session, client.client_id)
        conversation = None
        if request.store_conversation:
            conversation = short_term.get_or_create(
                request.conversation_id, user_ref=request.user_ref
            )
            base.conversation_id = conversation.id
            short_term.append(conversation, "user", message, request_id=request_id)

        # ================================================== LEVEL 0: tools
        dispatch = try_dispatch(
            message,
            self.tools,
            task_type=task_type,
            allowed_tools=allowed_tools,
            granted_permissions=None,
            context={"session": self.session, "client_id": client.client_id},
        )
        tool_value: str | None = None
        if dispatch.matched and dispatch.answer:
            base.answer = dispatch.answer
            base.route = Route.TOOL
            base.tool_used = dispatch.tool
            base.provider = "tool"
            base.model = dispatch.tool
            base.confidence = 1.0
            base.success = True
            base.notes.append("answered by a deterministic tool; no model was consulted")
            self._remember_answer(short_term, conversation, base.answer, request_id, base)
            return base
        if dispatch.result is not None and dispatch.result.ok:
            # The tool ran but did not answer outright — its value becomes a
            # cross-check on whatever the model says.
            tool_value = str(dispatch.result.value)
        if dispatch.error:
            base.notes.append(f"tool declined: {dispatch.error}")

        # ============================================ LEVEL 1: retrieval
        retrieval = self._retrieve(message, task_type, request.namespace)
        base.memory_hit = retrieval.memory_hit
        base.retrieval = retrieval.as_dict()
        base.sources = [
            {"source": i.source, "ref": i.ref, "score": round(i.score, 4)} for i in retrieval.items
        ]

        # ============================================ LEVEL 2: local model
        local_result = self._run_local(
            message,
            task_type=task_type,
            retrieval=retrieval,
            conversation_turns=(
                short_term.window(conversation.id) if conversation is not None else []
            ),
            requested_model=request.model,
            response_format=request.response_format,
            max_tokens=request.max_tokens,
            agent=request.agent,
        )

        # ======================================== LEVEL 3: validation
        validation: ValidationReport | None = None
        if local_result.response is not None:
            validation = validate_answer(
                local_result.response.text,
                question=message,
                task_type=task_type,
                context_texts=retrieval.context_texts() or None,
                response_format=request.response_format,
                finish_reason=local_result.response.finish_reason,
                retrieval_score=retrieval.top_score,
                tool_value=tool_value,
                threshold=self.settings.CONFIDENCE_THRESHOLD,
            )
            base.validation = validation.as_dict()
            base.confidence = validation.confidence
            base.input_tokens = local_result.response.input_tokens
            base.output_tokens = local_result.response.output_tokens

            if validation.passed:
                base.answer = local_result.response.text
                base.route = Route.LOCAL
                base.provider = local_result.response.provider
                base.model = local_result.response.model
                base.success = True
                if retrieval.solution is not None:
                    base.solution_id = retrieval.solution.id
                    self._mark_solution_used(retrieval, client.client_id)
                    base.notes.append(
                        "answered locally using a previously learned solution; no paid call"
                    )
                self._remember_answer(short_term, conversation, base.answer, request_id, base)
                return base

        # ============================================ LEVEL 4: escalation
        intent = why_escalate(
            local_available=local_result.available,
            local_timed_out=local_result.timed_out,
            local_failed=local_result.failed,
            validation=validation,
            had_context=retrieval.has_context,
            task_needs_context=task_type in CONTEXT_TASKS,
            premium_requested=request.premium and self.settings.ALLOW_USER_REQUESTED_PREMIUM,
            threshold=self.settings.CONFIDENCE_THRESHOLD,
        )
        if not intent.wanted or intent.reason is None:
            # Nothing wanted to escalate but nothing passed either: return the
            # best local attempt, flagged, rather than nothing at all.
            return self._degraded(base, local_result, short_term, conversation, request_id)

        base.escalation_reason = intent.reason
        permission = may_escalate(
            settings=self.settings,
            classification=classification,
            task_type=task_type.value,
            client_may_escalate=client.may_escalate,
            client_max_classification=client.max_external_classification,
            any_paid_provider=self.registry.any_paid_enabled(),
        )
        if not permission.allowed:
            base.escalation_blocked_reason = permission.blocked_reason
            base.notes.append(f"escalation blocked: {permission.detail}")
            return self._degraded(base, local_result, short_term, conversation, request_id)

        paid_result = self._run_paid(
            message,
            request=request,
            request_id=request_id,
            task_type=task_type,
            classification=classification,
            retrieval=retrieval,
            escalation_reason=intent.reason,
        )
        if not paid_result.ok or paid_result.response is None:
            base.escalation_blocked_reason = paid_result.blocked_reason
            base.notes.append(f"paid provider unavailable: {paid_result.detail}")
            return self._degraded(base, local_result, short_term, conversation, request_id)

        paid_response = paid_result.response
        paid_validation = validate_answer(
            paid_response.text,
            question=message,
            task_type=task_type,
            context_texts=retrieval.context_texts() or None,
            response_format=request.response_format,
            finish_reason=paid_response.finish_reason,
            retrieval_score=retrieval.top_score,
            tool_value=tool_value,
            threshold=self.settings.CONFIDENCE_THRESHOLD,
        )
        base.answer = paid_response.text
        base.route = Route.PAID
        base.provider = paid_result.provider
        base.model = paid_result.model
        base.cost_usd = paid_result.cost_usd
        base.input_tokens = paid_response.input_tokens
        base.output_tokens = paid_response.output_tokens
        base.confidence = paid_validation.confidence
        base.validation = paid_validation.as_dict()
        # A veto — a refusal, an empty answer, a contradiction, a safety
        # violation — is not a successful answer no matter which provider
        # produced it. Merely-low confidence still counts as an answer
        # returned, flagged as unverified, because the caller has something
        # usable and the note says how much to trust it.
        base.success = paid_validation.passed or (
            not paid_validation.vetoes and bool(paid_response.text.strip())
        )
        if not paid_validation.passed:
            base.notes.append(
                f"the paid answer also failed validation: {paid_validation.primary_failure}"
            )

        # ------------------------------------------ learn from the fallback
        self._learn(
            base,
            question=message,
            local_attempt=(local_result.response.text if local_result.response else None),
            paid_validation=paid_validation,
            retrieval=retrieval,
            client=client,
            request_id=request_id,
            injection_suspected=input_safety.injection_suspected,
        )
        self._remember_answer(short_term, conversation, base.answer, request_id, base)
        return base

    # ------------------------------------------------------------- level 1
    def _retrieve(
        self, message: str, task_type: TaskType, namespace: str | None
    ) -> RetrievalResult:
        try:
            return self.retriever.retrieve(message, task_type=task_type, namespace=namespace)
        except Exception as exc:
            # Retrieval is an optimisation. Losing it must not lose the request.
            log.warning("retrieval_failed", error=type(exc).__name__)
            return RetrievalResult()

    # ------------------------------------------------------------- level 2
    @dataclass
    class _LocalResult:
        response: CompletionResponse | None = None
        available: bool = True
        timed_out: bool = False
        failed: bool = False
        detail: str = ""

    def _run_local(
        self,
        message: str,
        *,
        task_type: TaskType,
        retrieval: RetrievalResult,
        conversation_turns: list,
        requested_model: str | None,
        response_format: str,
        max_tokens: int | None,
        agent: AgentSpec | None = None,
    ) -> _LocalResult:
        local: Provider | None = self.registry.local
        if local is None or not local.enabled:
            return self._LocalResult(available=False, detail="no local provider configured")

        model = None
        resolver = getattr(local, "resolve_model", None)
        if resolver is not None:
            model = resolver(task_type, requested_model)
            if model is None:
                return self._LocalResult(available=False, detail="no local model is installed")
        else:
            model = requested_model

        messages = [
            Message(
                role="system",
                content=_system_prompt(task_type, response_format, agent),
            )
        ]
        # Recent turns, excluding the one we just stored for this request.
        for turn in conversation_turns[:-1][-6:]:
            if turn.role in ("user", "assistant"):
                messages.append(Message(role=turn.role, content=turn.content))
        messages.append(
            Message(role="user", content=build_user_prompt(message, retrieval.items))
        )

        try:
            response = local.complete(
                CompletionRequest(
                    messages=messages,
                    model=model,
                    max_tokens=max_tokens or self.settings.LOCAL_MAX_TOKENS,
                    temperature=0.2,
                    timeout=self.settings.LOCAL_TIMEOUT_SECONDS,
                    response_format=response_format,
                )
            )
        except ProviderTimeoutError as exc:
            log.warning("local_timeout")
            return self._LocalResult(available=True, timed_out=True, detail=exc.message)
        except ProviderUnavailableError as exc:
            log.warning("local_unavailable", detail=exc.code)
            return self._LocalResult(available=False, failed=True, detail=exc.message)
        return self._LocalResult(response=response)

    # ------------------------------------------------------------- level 4
    def _run_paid(
        self,
        message: str,
        *,
        request: GatewayRequest,
        request_id: str,
        task_type: TaskType,
        classification: Classification,
        retrieval: RetrievalResult,
        escalation_reason: EscalationReason,
    ):
        providers = self.registry.paid_providers(self.settings.paid_provider_order)
        completion = CompletionRequest(
            messages=[
                Message(
                    role="system",
                    content=_system_prompt(task_type, request.response_format, request.agent),
                ),
                Message(role="user", content=build_user_prompt(message, retrieval.items)),
            ],
            model=None,
            max_tokens=request.max_tokens or self.settings.PAID_MAX_TOKENS,
            temperature=0.2,
            timeout=self.settings.PAID_TIMEOUT_SECONDS,
            response_format=request.response_format,
            request_id=request_id,
        )
        return self.paid.call(
            providers,
            completion,
            client_id=request.client.client_id,
            request_id=request_id,
            task_type=task_type.value,
            classification=classification,
            escalation_reason=escalation_reason,
            client_max_classification=request.client.max_external_classification,
            client_daily_budget=request.client.daily_budget_usd,
        )

    # ------------------------------------------------------------ learning
    def _learn(
        self,
        response: GatewayResponse,
        *,
        question: str,
        local_attempt: str | None,
        paid_validation: ValidationReport,
        retrieval: RetrievalResult,
        client: Client,
        request_id: str,
        injection_suspected: bool,
    ) -> None:
        if not paid_validation.passed:
            response.notes.append("not captured as a solution: the paid answer failed validation")
            return
        decision = capture(
            self.session,
            client.client_id,
            question=question,
            answer=response.answer,
            task_type=response.task_type.value,
            provider=response.provider or "unknown",
            model=response.model or "unknown",
            failure_reason=response.escalation_reason.value if response.escalation_reason else None,
            local_attempt=local_attempt,
            validation=paid_validation.as_dict(),
            confidence=paid_validation.confidence,
            classification=response.classification,
            context={"texts": retrieval.context_texts()[:3], "sources": response.sources},
            request_id=request_id,
            ttl_days=self.settings.SOLUTION_TTL_DAYS,
            injection_suspected=injection_suspected,
        )
        if not decision.captured or decision.solution is None:
            response.notes.append(f"not captured as a solution: {decision.reason}")
            return

        response.solution_id = decision.solution.id
        response.notes.append("stored as a CANDIDATE solution for review")

        if not self.settings.AUTO_PROMOTE:
            return
        pipeline = PromotionPipeline(
            self.session,
            client.client_id,
            settings=self.settings,
            local_provider=self.registry.local,
            retriever=self.retriever,
        )
        outcome = pipeline.process(decision.solution)
        response.notes.append(f"promotion pipeline: {outcome.status.value} — {outcome.reason}")

    def _mark_solution_used(self, retrieval: RetrievalResult, client_id: str) -> None:
        from app.learning.solution_store import SolutionStore

        if retrieval.solution is None:
            return
        SolutionStore(self.session, client_id).mark_used(retrieval.solution)

    # ------------------------------------------------------------- helpers
    def _degraded(
        self,
        base: GatewayResponse,
        local_result: _LocalResult,
        short_term: ShortTermMemory,
        conversation,
        request_id: str,
    ) -> GatewayResponse:
        """Return the best available answer, honestly labelled as not validated."""
        if local_result.response is not None and local_result.response.text.strip():
            base.answer = local_result.response.text
            base.route = Route.LOCAL
            base.provider = local_result.response.provider
            base.model = local_result.response.model
            base.success = False
            base.notes.append(
                "returned the local answer, which did not pass validation — treat it as unverified"
            )
            self._remember_answer(short_term, conversation, base.answer, request_id, base)
            return base
        base.route = Route.FAILED
        base.success = False
        base.answer = ""
        if not base.notes:
            base.notes.append(local_result.detail or "no provider could answer this request")
        return base

    def _remember_answer(
        self,
        short_term: ShortTermMemory,
        conversation,
        answer: str,
        request_id: str,
        response: GatewayResponse,
    ) -> None:
        if conversation is None or not answer:
            return
        short_term.append(
            conversation,
            "assistant",
            answer,
            request_id=request_id,
            meta={"route": response.route.value, "provider": response.provider},
        )

    def _client_has_documents(self, client_id: str) -> bool:
        from sqlalchemy import select

        from app.database.models import Document

        return (
            self.session.scalars(
                select(Document.id).where(Document.client_id == client_id).limit(1)
            ).first()
            is not None
        )

    def _log_request(self, request: GatewayRequest, response: GatewayResponse) -> None:
        self.session.add(
            RequestLog(
                request_id=response.request_id,
                client_id=request.client.client_id,
                task_type=response.task_type.value,
                classification=response.classification.value,
                route=response.route.value,
                provider=response.provider,
                model=response.model,
                latency_ms=response.latency_ms,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cost_usd=response.cost_usd,
                confidence=response.confidence,
                memory_hit=response.memory_hit,
                tool_used=response.tool_used,
                escalation_reason=(
                    response.escalation_reason.value if response.escalation_reason else None
                ),
                escalation_blocked_reason=(
                    response.escalation_blocked_reason.value
                    if response.escalation_blocked_reason
                    else None
                ),
                validation_result=response.validation.get("signals", {}),
                local_attempted=response.route in (Route.LOCAL, Route.PAID),
                success=response.success,
                question_fingerprint=fingerprint(request.message, salt=request.client.client_id),
            )
        )
        record(
            self.session,
            actor=request.client.client_id,
            action=CHAT_REQUEST,
            resource_type="request",
            resource_id=response.request_id,
            request_id=response.request_id,
            result="ok" if response.success else "failed",
            detail={
                "route": response.route.value,
                "task_type": response.task_type.value,
                "classification": response.classification.value,
                "provider": response.provider,
                "cost_usd": response.cost_usd,
                "memory_hit": response.memory_hit,
                "escalation_reason": (
                    response.escalation_reason.value if response.escalation_reason else None
                ),
            },
        )
        log.info(
            "request_complete",
            route=response.route.value,
            task_type=response.task_type.value,
            provider=response.provider,
            cost_usd=response.cost_usd,
            memory_hit=response.memory_hit,
            confidence=response.confidence,
            latency_ms=response.latency_ms,
        )
