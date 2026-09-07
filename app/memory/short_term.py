"""Conversation memory.

Short-lived by design: a bounded window of recent turns, scoped to one
conversation and one client. It is not knowledge — nothing here is treated as
a fact, and nothing here is retrieved for a different conversation.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.database.models import Conversation, Message

DEFAULT_WINDOW = 12
MAX_STORED_CHARS = 8000


@dataclass
class Turn:
    role: str
    content: str

    def as_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


class ShortTermMemory:
    def __init__(self, session: Session, client_id: str):
        self.session = session
        self.client_id = client_id

    def get_or_create(self, conversation_id: str | None, *, user_ref: str | None = None) -> Conversation:
        if conversation_id:
            conversation = self.session.get(Conversation, conversation_id)
            if conversation is not None:
                if conversation.client_id != self.client_id:
                    # Do not reveal that the id exists at all.
                    raise PermissionError("conversation not found for this client")
                return conversation
        conversation = Conversation(
            id=conversation_id or new_id("conv"), client_id=self.client_id, user_ref=user_ref
        )
        self.session.add(conversation)
        self.session.flush()
        return conversation

    def append(
        self,
        conversation: Conversation,
        role: str,
        content: str,
        *,
        request_id: str | None = None,
        meta: dict | None = None,
    ) -> Message:
        message = Message(
            conversation_id=conversation.id,
            client_id=self.client_id,
            role=role,
            content=(content or "")[:MAX_STORED_CHARS],
            request_id=request_id,
            meta=meta or {},
        )
        self.session.add(message)
        if not conversation.title and role == "user":
            conversation.title = (content or "")[:120]
        self.session.flush()
        return message

    def window(self, conversation_id: str, limit: int = DEFAULT_WINDOW) -> list[Turn]:
        """The most recent ``limit`` turns, oldest first."""
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id, Message.client_id == self.client_id)
            .order_by(Message.id.desc())
            .limit(limit)
        )
        rows = list(self.session.scalars(stmt))
        return [Turn(role=m.role, content=m.content) for m in reversed(rows)]

    def list_conversations(self, limit: int = 50, offset: int = 0) -> list[Conversation]:
        stmt = (
            select(Conversation)
            .where(Conversation.client_id == self.client_id)
            .order_by(Conversation.updated_at.desc())
            .limit(min(limit, 200))
            .offset(offset)
        )
        return list(self.session.scalars(stmt))

    def delete(self, conversation_id: str) -> bool:
        conversation = self.session.get(Conversation, conversation_id)
        if conversation is None or conversation.client_id != self.client_id:
            return False
        self.session.delete(conversation)
        return True
