"""Chat service — Phase 5 placeholder, Phase 7 swaps in LangGraph."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oncallpilot_api.db.models import ChatMessage, ChatSession
from oncallpilot_api.db.repositories import append_chat_message, create_chat_session


class ChatService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_session(self, investigation_session_id: str) -> str:
        chat = await create_chat_session(
            self.db,
            investigation_session_id=uuid.UUID(investigation_session_id),
        )
        return str(chat.id)

    async def append_message(self, session_id: str, role: str, content: str) -> ChatMessage:
        return await append_chat_message(
            self.db,
            chat_session_id=uuid.UUID(session_id),
            role=role,
            content=content,
        )

    async def get_messages(self, session_id: str) -> list[ChatMessage]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.chat_session_id == uuid.UUID(session_id))
            .order_by(ChatMessage.created_at)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_session(self, session_id: str) -> ChatSession | None:
        return await self.db.get(ChatSession, uuid.UUID(session_id))

    async def list_sessions(self, limit: int = 20) -> list[ChatSession]:
        stmt = select(ChatSession).order_by(ChatSession.created_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def respond(self, session_id: str) -> str:
        # Phase 5 placeholder — Phase 7 replaces with LangGraph call.
        return "chat graph 在 Phase 7 接入"
