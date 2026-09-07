"""The four generic agents shipped in V1.

Generic on purpose: none of them knows anything about accounting, trading,
deliveries or bookings. Those belong to the applications that will connect
later, and adding one must not require touching the Gateway.
"""

from __future__ import annotations

from app.agents.base import AgentRegistry, AgentSpec
from app.database.enums import TaskType

GENERAL = AgentSpec(
    name="general",
    description="Everyday questions, explanations and drafting. The default.",
    default_task_type=TaskType.GENERAL,
    system_prompt="",
)

RESEARCH = AgentSpec(
    name="research",
    description=(
        "Gathers and compares information, separating what the sources support from what "
        "it is inferring."
    ),
    default_task_type=TaskType.RESEARCH,
    system_prompt=(
        "State clearly which parts of your answer come from the CONTEXT and which are your "
        "own inference. When the sources disagree, say so rather than picking one silently. "
        "When nothing supports an answer, say that instead of filling the gap."
    ),
    allowed_tools=("document_search", "document_list", "memory_search", "web_search", "date_calculator"),
)

DOCUMENT = AgentSpec(
    name="document",
    description="Answers strictly from uploaded documents, with citations.",
    default_task_type=TaskType.DOCUMENT_QA,
    system_prompt=(
        "Answer only from the CONTEXT. Cite the source id of every chunk you use. If the "
        "documents do not contain the answer, say so — do not fall back on general knowledge."
    ),
    allowed_tools=("document_search", "document_list", "memory_search"),
)

DEVELOPER = AgentSpec(
    name="developer",
    description="Reads code and errors, explains them, and proposes changes. Advisory only.",
    default_task_type=TaskType.CODE,
    system_prompt=(
        "Give working code and name your assumptions. You cannot run anything, read a "
        "repository or deploy: describe the change, never claim to have made it."
    ),
    allowed_tools=("calculator", "json_parser", "document_search", "date_calculator"),
)


def build_agent_registry() -> AgentRegistry:
    return AgentRegistry([GENERAL, RESEARCH, DOCUMENT, DEVELOPER])
