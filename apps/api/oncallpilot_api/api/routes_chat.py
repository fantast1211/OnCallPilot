"""Chat API routes (spec §6.3) — Phase 5 placeholder."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from oncallpilot_api.api.schemas import (
    AppendChatMessageRequest,
    ChatMessageResponse,
    ChatSessionResponse,
    CreateChatSessionRequest,
)
from oncallpilot_api.db.session import get_db_session
from oncallpilot_api.services.chat_service import ChatService

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.post("/sessions")
async def create_session(
    body: CreateChatSessionRequest,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    svc = ChatService(db)
    session_id = await svc.create_session(body.investigation_session_id)
    return {"session_id": session_id}


@router.get("/sessions")
async def list_sessions(
    limit: int = 20,
    db: AsyncSession = Depends(get_db_session),
) -> list[ChatSessionResponse]:
    svc = ChatService(db)
    sessions = await svc.list_sessions(limit=limit)
    return [
        ChatSessionResponse(
            id=str(s.id),
            investigation_session_id=str(s.investigation_session_id),
            status=s.status,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> ChatSessionResponse:
    svc = ChatService(db)
    session = await svc.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return ChatSessionResponse(
        id=str(session.id),
        investigation_session_id=str(session.investigation_session_id),
        status=session.status,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.post("/sessions/{session_id}/messages")
async def append_message(
    session_id: str,
    body: AppendChatMessageRequest,
    db: AsyncSession = Depends(get_db_session),
) -> ChatMessageResponse:
    svc = ChatService(db)
    session = await svc.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")

    await svc.append_message(session_id, body.role, body.content)

    # Phase 5 placeholder: echo response
    echo_content = await svc.respond(session_id)
    assistant_msg = await svc.append_message(session_id, "assistant", echo_content)

    return ChatMessageResponse(
        id=str(assistant_msg.id),
        role=assistant_msg.role,
        content=assistant_msg.content,
        created_at=assistant_msg.created_at,
    )


@router.get("/sessions/{session_id}/messages")
async def get_messages(
    session_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> list[ChatMessageResponse]:
    svc = ChatService(db)
    session = await svc.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")

    messages = await svc.get_messages(session_id)
    return [
        ChatMessageResponse(
            id=str(m.id),
            role=m.role,
            content=m.content,
            created_at=m.created_at,
        )
        for m in messages
    ]
