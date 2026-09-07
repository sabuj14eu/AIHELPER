"""POST /api/v1/chat — the single endpoint a future application needs."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import current_client, resolve_agent, services_dep
from app.api.schemas import ChatRequest, ChatResponse
from app.database.models import Client
from app.gateway.router import GatewayRequest
from app.runtime import SessionServices

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse, summary="Ask AI Helper a question")
def chat(
    body: ChatRequest,
    client: Client = Depends(current_client),
    services: SessionServices = Depends(services_dep),
) -> ChatResponse:
    """Route one request down the local-first ladder.

    Tools first, then memory and documents, then the local model, then — only
    if none of those produced a validated answer, and only if this client,
    this classification and the budget all allow it — a paid provider.
    """
    agent = resolve_agent(body.agent)
    result = services.router.handle(
        GatewayRequest(
            message=body.message,
            client=client,
            task_type=body.task_type,
            conversation_id=body.conversation_id,
            document_ids=body.document_ids,
            namespace=body.namespace,
            classification=body.classification,
            response_format=body.response_format,
            model=body.model,
            premium=body.premium,
            user_ref=body.user_ref,
            max_tokens=body.max_tokens,
            store_conversation=body.store_conversation,
            agent=agent,
        )
    )
    return ChatResponse(**result.as_dict())
