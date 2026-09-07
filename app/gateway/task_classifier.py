"""Task classification.

Deterministic and cheap: a request is classified before any model is
consulted, because the classification decides which model gets consulted. A
classifier that needed a model to run would be a model call spent on every
request, including the ones a tool could have answered for free.

The signals are surface features — an explicit task_type from the caller, an
attached document reference, the shape of the message. When nothing matches,
GENERAL is the answer, and GENERAL is not a failure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.database.enums import TaskType

# Ordered: the first family whose pattern matches wins, so the specific
# patterns are listed before the general ones.
_PATTERNS: list[tuple[TaskType, list[re.Pattern[str]]]] = [
    (
        TaskType.ARITHMETIC,
        [
            re.compile(r"^\s*[-+(]?\s*\d[\d\s().,]*[-+*/%^][\d\s().,+\-*/%^]*\s*=?\s*[?.]?\s*$"),
            re.compile(r"(?i)\b(?:calculate|compute|what is|how much is)\b[^?]*\d+\s*[-+*/%^]\s*\d+"),
        ],
    ),
    (
        TaskType.DATE,
        [
            re.compile(r"(?i)\bhow many (?:days|weeks|months|years)\b.{0,40}\bbetween\b"),
            re.compile(r"(?i)\bwhat (?:day|weekday)\b.{0,30}\b\d{4}-\d{2}-\d{2}"),
            re.compile(r"\b\d{4}-\d{2}-\d{2}\s*[+\-]\s*\d+\s*(?:days?|weeks?|months?|years?)"),
            re.compile(r"(?i)\b(?:end|last day) of (?:the )?month\b"),
        ],
    ),
    (
        TaskType.STRUCTURED_DATA,
        [
            re.compile(r"(?i)\b(?:valid|parse|validate)\b.{0,20}\bjson\b"),
            re.compile(r"(?i)\breturn\b.{0,30}\b(?:as )?json\b"),
            re.compile(r"(?i)\bconvert\b.{0,30}\b(?:to )?(?:json|csv|yaml)\b"),
        ],
    ),
    (
        TaskType.SUMMARIZATION,
        [
            re.compile(r"(?i)\b(?:summari[sz]e|summary of|tl;?dr|give me the gist|key points of)\b"),
            re.compile(r"(?i)\bin (?:a few|one|two|three) (?:sentences|bullet points)\b"),
        ],
    ),
    (
        TaskType.EXTRACTION,
        [
            re.compile(r"(?i)\bextract\b.{0,40}\b(?:from|out of)\b"),
            re.compile(r"(?i)\b(?:pull|list) (?:out )?(?:all )?the\b.{0,30}\b(?:fields|values|numbers|dates|names)\b"),
            re.compile(r"(?i)\bwhat (?:is|are) the\b.{0,30}\bin (?:this|the) (?:document|invoice|file|text)\b"),
        ],
    ),
    (
        TaskType.CLASSIFICATION,
        [
            re.compile(r"(?i)\bclassify\b|\bcategori[sz]e\b|\blabel this\b"),
            re.compile(r"(?i)\bis this (?:a|an)\b.{0,30}\bor\b"),
            re.compile(r"(?i)\b(?:sentiment|intent) of\b"),
        ],
    ),
    (
        TaskType.CODE,
        [
            re.compile(r"(?i)\b(?:write|fix|debug|refactor|review)\b.{0,30}\b(?:code|function|class|script|query|regex)\b"),
            re.compile(r"(?i)\b(?:python|javascript|typescript|sql|bash|rust|go|java|php)\b.{0,40}\b(?:function|snippet|example|error)\b"),
            re.compile(r"```"),
            re.compile(r"(?i)\b(?:stack ?trace|traceback|exception|compiler error)\b"),
        ],
    ),
    (
        TaskType.RESEARCH,
        [
            re.compile(r"(?i)\b(?:research|investigate|compare|find out|survey|what are the options for)\b"),
            re.compile(r"(?i)\bpros and cons\b|\btrade-?offs?\b"),
        ],
    ),
    (
        TaskType.REASONING,
        [
            re.compile(r"(?i)\b(?:why|how come)\b.{0,60}\?"),
            re.compile(r"(?i)\b(?:explain|reason through|work out|walk me through)\b"),
            re.compile(r"(?i)\bstep by step\b"),
        ],
    ),
]

_DOCUMENT_HINTS = re.compile(
    r"(?i)\b(?:in|from|according to|based on)\s+(?:the\s+)?"
    r"(?:document|documents|file|files|pdf|invoice|contract|report|upload|attachment)s?\b"
)


@dataclass
class Classification:
    task_type: TaskType
    confidence: float
    reason: str

    def as_dict(self) -> dict:
        return {
            "task_type": self.task_type.value,
            "confidence": round(self.confidence, 2),
            "reason": self.reason,
        }


def classify(
    message: str,
    *,
    declared: TaskType | str | None = None,
    has_documents: bool = False,
    document_ids: list[str] | None = None,
) -> Classification:
    """Pick the task type. A caller's declaration always wins."""
    if declared:
        try:
            return Classification(TaskType(str(declared).lower()), 1.0, "declared by the caller")
        except ValueError:
            pass  # an unknown label is ignored, not an error

    text = (message or "").strip()

    if document_ids:
        return Classification(TaskType.DOCUMENT_QA, 0.95, "the request names specific documents")
    if has_documents and _DOCUMENT_HINTS.search(text):
        return Classification(
            TaskType.DOCUMENT_QA, 0.85, "the request refers to uploaded documents"
        )

    for task_type, patterns in _PATTERNS:
        for pattern in patterns:
            if pattern.search(text):
                return Classification(task_type, 0.8, f"matched the {task_type.value} pattern")

    if has_documents and len(text.split()) > 4:
        return Classification(
            TaskType.DOCUMENT_QA, 0.5, "documents are available and the question is open-ended"
        )
    return Classification(TaskType.GENERAL, 0.4, "no specific pattern matched")
