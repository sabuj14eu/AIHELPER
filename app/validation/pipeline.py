"""One entry point that runs every validation stage in order."""

from __future__ import annotations

from app.database.enums import TaskType
from app.validation import factuality as factuality_mod
from app.validation import output as output_mod
from app.validation import safety as safety_mod
from app.validation.confidence import ValidationReport, evaluate


def validate_answer(
    answer: str,
    *,
    question: str = "",
    task_type: TaskType | str = TaskType.GENERAL,
    context_texts: list[str] | None = None,
    response_format: str = "text",
    finish_reason: str | None = None,
    retrieval_score: float = 0.0,
    tool_value: str | None = None,
    threshold: float = 0.62,
) -> ValidationReport:
    strict_numbers = TaskType(task_type) in (TaskType.DOCUMENT_QA, TaskType.EXTRACTION)
    output = output_mod.check_output(
        answer, response_format=response_format, finish_reason=finish_reason
    )
    safety = safety_mod.check_output(answer, context_texts=context_texts)
    facts = factuality_mod.check(
        answer, context_texts, question=question, strict_numbers=strict_numbers
    )
    return evaluate(
        answer,
        task_type=task_type,
        output=output,
        safety=safety,
        factuality=facts,
        retrieval_score=retrieval_score,
        tool_value=tool_value,
        threshold=threshold,
    )
