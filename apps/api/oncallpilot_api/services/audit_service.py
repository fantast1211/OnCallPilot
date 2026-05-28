"""Audit service — thin validation layer over tool-call recording."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from oncallpilot_api.db.repositories import append_tool_call
from oncallpilot_api.db.models import ToolCall


async def record_tool_call(
    db: AsyncSession,
    *,
    investigation_session_id: uuid.UUID | None = None,
    chat_session_id: uuid.UUID | None = None,
    tool_name: str,
    input_data: dict | None = None,
    output_data: dict | None = None,
    status: str = "success",
    step_index: int | None = None,
) -> ToolCall:
    """Record a tool call, enforcing that exactly one session ID is provided."""
    if investigation_session_id is not None and chat_session_id is not None:
        raise ValueError(
            "investigation_session_id and chat_session_id are mutually exclusive"
        )
    if investigation_session_id is None and chat_session_id is None:
        raise ValueError(
            "Exactly one of investigation_session_id or chat_session_id must be provided"
        )

    return await append_tool_call(
        db,
        investigation_session_id=investigation_session_id,
        chat_session_id=chat_session_id,
        tool_name=tool_name,
        input_data=input_data,
        output_data=output_data,
        status=status,
        step_index=step_index,
    )
