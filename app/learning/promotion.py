"""The promotion pipeline.

CANDIDATE -> VALIDATED -> PROMOTED, with an explicit gate at each step. The
work order's rule is the design: *do not blindly teach the local system every
API answer*. Three things have to be true before an answer becomes something
the system will repeat.

1. **It validates on its own terms.** The same validation pipeline that judged
   the local attempt is run over the paid answer.
2. **It is reproducible locally.** The candidate is handed back to the local
   model as context and the model is asked the original question again. If the
   local model cannot produce a passing answer *even with the solution in
   front of it*, promoting it would buy nothing: retrieval would find it and
   the request would escalate anyway.
3. **Nothing about it is disqualifying.** Empty, contradicted, unsafe, or
   below the configured confidence floor.

Gate 2 is skipped only when PROMOTION_REQUIRES_REPRODUCTION is false, and the
reason is then recorded on the row so no one has to guess later.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.audit import SOLUTION_PROMOTED, SOLUTION_REJECTED, SOLUTION_VALIDATED, record
from app.core.config import Settings
from app.core.errors import ProviderUnavailableError
from app.core.logging import get_logger
from app.database.enums import SolutionStatus
from app.database.models import SolutionCandidate
from app.learning.solution_store import SolutionStore
from app.local_ai.prompts import build_system_prompt, reproduction_prompt
from app.providers.base import CompletionRequest, Message, Provider
from app.validation import validate_answer

log = get_logger("promotion")


@dataclass
class PromotionOutcome:
    status: SolutionStatus
    reason: str
    validation: dict | None = None
    reproduction: dict = field(default_factory=dict)

    @property
    def promoted(self) -> bool:
        return self.status is SolutionStatus.PROMOTED

    def as_dict(self) -> dict:
        return {
            "status": self.status.value,
            "reason": self.reason,
            "promoted": self.promoted,
            "reproduction": self.reproduction,
        }


class PromotionPipeline:
    def __init__(
        self,
        session: Session,
        client_id: str,
        *,
        settings: Settings,
        local_provider: Provider | None,
        retriever=None,
    ):
        self.session = session
        self.client_id = client_id
        self.settings = settings
        self.local = local_provider
        self.retriever = retriever
        self.store = SolutionStore(session, client_id)

    # ------------------------------------------------------------ gate one
    def validate(self, solution: SolutionCandidate) -> PromotionOutcome:
        report = validate_answer(
            solution.answer,
            question=solution.question,
            task_type=solution.task_type,
            context_texts=(solution.context or {}).get("texts") or None,
            threshold=self.settings.PROMOTION_MIN_CONFIDENCE,
        )
        if not report.passed:
            reason = f"validation failed: {report.primary_failure}"
            self.store.set_status(solution, SolutionStatus.REJECTED, reason)
            record(
                self.session,
                actor=self.client_id,
                action=SOLUTION_REJECTED,
                resource_type="solution",
                resource_id=solution.id,
                detail={"stage": "validation", "reason": reason, "confidence": report.confidence},
            )
            return PromotionOutcome(SolutionStatus.REJECTED, reason, report.as_dict())

        solution.validation_result = {**(solution.validation_result or {}), "promotion": report.as_dict()}
        self.store.set_status(solution, SolutionStatus.VALIDATED, "passed the validation pipeline")
        record(
            self.session,
            actor=self.client_id,
            action=SOLUTION_VALIDATED,
            resource_type="solution",
            resource_id=solution.id,
            detail={"confidence": report.confidence},
        )
        return PromotionOutcome(SolutionStatus.VALIDATED, "validated", report.as_dict())

    # ------------------------------------------------------------ gate two
    def reproduce(self, solution: SolutionCandidate) -> dict:
        """Can the local model answer the question with this solution in hand?"""
        if self.local is None:
            return {"attempted": False, "reason": "no local provider configured"}
        model = None
        resolver = getattr(self.local, "resolve_model", None)
        if resolver is not None:
            model = resolver(solution.task_type)
            if model is None:
                return {"attempted": False, "reason": "no local model installed"}
        request = CompletionRequest(
            messages=[
                Message(role="system", content=build_system_prompt(solution.task_type)),
                Message(
                    role="user",
                    content=reproduction_prompt(solution.question, solution.answer),
                ),
            ],
            model=model,
            max_tokens=self.settings.LOCAL_MAX_TOKENS,
            temperature=0.0,
        )
        try:
            response = self.local.complete(request)
        except ProviderUnavailableError as exc:
            return {"attempted": False, "reason": f"local provider unavailable: {exc.message}"}

        report = validate_answer(
            response.text,
            question=solution.question,
            task_type=solution.task_type,
            context_texts=[solution.answer],
            retrieval_score=1.0,
            threshold=self.settings.CONFIDENCE_THRESHOLD,
        )
        return {
            "attempted": True,
            "passed": report.passed,
            "confidence": report.confidence,
            "model": response.model,
            "failure": report.primary_failure,
        }

    # --------------------------------------------------------------- driver
    def process(self, solution: SolutionCandidate) -> PromotionOutcome:
        """Run every gate in order and leave the row in its final state."""
        outcome = self.validate(solution)
        if outcome.status is SolutionStatus.REJECTED:
            return outcome

        reproduction: dict = {}
        if self.settings.PROMOTION_REQUIRES_REPRODUCTION:
            reproduction = self.reproduce(solution)
            solution.reproduction = reproduction
            if reproduction.get("attempted") and not reproduction.get("passed"):
                reason = (
                    "the local model could not produce a passing answer even with this "
                    f"solution as context ({reproduction.get('failure')})"
                )
                self.store.set_status(solution, SolutionStatus.REJECTED, reason)
                record(
                    self.session,
                    actor=self.client_id,
                    action=SOLUTION_REJECTED,
                    resource_type="solution",
                    resource_id=solution.id,
                    detail={"stage": "reproduction", "reason": reason},
                )
                return PromotionOutcome(
                    SolutionStatus.REJECTED, reason, outcome.validation, reproduction
                )
            if not reproduction.get("attempted"):
                # Cannot check. That is not a pass — it stays VALIDATED and a
                # human (or a later run, when the model is back) decides.
                reason = (
                    "reproduction could not be attempted: "
                    f"{reproduction.get('reason')} — held at VALIDATED"
                )
                solution.status_reason = reason[:300]
                log.info("promotion_held", solution_id=solution.id, reason=reason)
                return PromotionOutcome(
                    SolutionStatus.VALIDATED, reason, outcome.validation, reproduction
                )
        else:
            reproduction = {"attempted": False, "reason": "reproduction gate disabled by configuration"}
            solution.reproduction = reproduction

        self.store.set_status(
            solution, SolutionStatus.PROMOTED, "validated and reproducible by the local model"
        )
        if self.retriever is not None:
            try:
                self.retriever.index_solution(solution)
            except Exception as exc:
                # An unindexed PROMOTED row would never be found again.
                self.store.set_status(
                    solution,
                    SolutionStatus.VALIDATED,
                    f"promotion rolled back: indexing failed ({type(exc).__name__})",
                )
                log.error("promotion_index_failed", solution_id=solution.id, error=type(exc).__name__)
                return PromotionOutcome(
                    SolutionStatus.VALIDATED,
                    "indexing failed; not promoted",
                    outcome.validation,
                    reproduction,
                )
        record(
            self.session,
            actor=self.client_id,
            action=SOLUTION_PROMOTED,
            resource_type="solution",
            resource_id=solution.id,
            detail={"task_type": solution.task_type, "provider": solution.provider},
        )
        log.info("solution_promoted", solution_id=solution.id)
        return PromotionOutcome(
            SolutionStatus.PROMOTED, "promoted", outcome.validation, reproduction
        )

    def reject(self, solution: SolutionCandidate, reason: str) -> PromotionOutcome:
        self.store.set_status(solution, SolutionStatus.REJECTED, reason)
        if self.retriever is not None:
            # A rejected solution that stays indexed would still be retrieved,
            # so this is attempted — but a vector-store outage must not stop
            # the rejection itself from being recorded.
            with contextlib.suppress(Exception):
                self.retriever.unindex_solution(solution.id)
        record(
            self.session,
            actor=self.client_id,
            action=SOLUTION_REJECTED,
            resource_type="solution",
            resource_id=solution.id,
            detail={"stage": "manual", "reason": reason},
        )
        return PromotionOutcome(SolutionStatus.REJECTED, reason)
