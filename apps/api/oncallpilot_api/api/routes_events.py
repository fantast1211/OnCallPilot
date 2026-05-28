"""SSE event stream for investigation sessions (spec §6.2 / §11.2 / §11.3)."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from oncallpilot_api.db.models import InvestigationSession, ToolCall
from oncallpilot_api.db.session import get_db_session
from oncallpilot_api.dependencies import get_event_bus
from oncallpilot_api.services.event_bus import EventBus

router = APIRouter(prefix="/api/v1/investigations", tags=["investigations"])

STREAM_CHANNEL = "oncallpilot:events:investigation:{session_id}"

# Event types per spec §11.2
SESSION_STARTED = "session.started"
STEP_PLANNED = "step.planned"
TOOL_STARTED = "tool.started"
TOOL_COMPLETED = "tool.completed"
EVIDENCE_ADDED = "evidence.added"
SESSION_COMPLETED = "session.completed"
SESSION_FAILED = "session.failed"

TERMINAL_STATUSES = {"completed", "failed"}


def _sse_frame(event_id: str, event_type: str, data: dict) -> str:
    """Format a single SSE frame."""
    return f"id: {event_id}\nevent: {event_type}\ndata: {json.dumps(data)}\n\n"


def _build_replay_frames(
    tool_calls: list[dict],
    last_event_id: str | None,
) -> list[str]:
    """Build SSE frames from pre-loaded tool_call dicts.

    Event IDs are sequential integers starting at 1.
    If *last_event_id* is provided, skips events with id <= that value.
    """
    skip_up_to = int(last_event_id) if last_event_id is not None else 0
    frames: list[str] = []
    seq = 0

    for tc in tool_calls:
        # tool.started
        seq += 1
        if seq > skip_up_to:
            started = {
                "type": TOOL_STARTED,
                "tool_call_id": tc["id"],
                "tool_name": tc["tool_name"],
                "step_index": tc["step_index"],
                "input_data": tc["input_data"],
                "started_at": tc["started_at"],
            }
            frames.append(_sse_frame(str(seq), TOOL_STARTED, started))

        # tool.completed
        seq += 1
        if seq > skip_up_to:
            completed = {
                "type": TOOL_COMPLETED,
                "tool_call_id": tc["id"],
                "tool_name": tc["tool_name"],
                "step_index": tc["step_index"],
                "status": tc["status"],
                "output_data": tc["output_data"],
                "latency_ms": tc["latency_ms"],
                "error_message": tc["error_message"],
                "ended_at": tc["ended_at"],
            }
            frames.append(_sse_frame(str(seq), TOOL_COMPLETED, completed))

    return frames


async def _load_tool_calls_as_dicts(
    db: AsyncSession, session_id: uuid.UUID
) -> list[dict]:
    """Load tool calls for a session ordered by created_at, returned as plain dicts."""
    stmt = (
        select(ToolCall)
        .where(ToolCall.investigation_session_id == session_id)
        .order_by(ToolCall.created_at.asc())
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "id": str(tc.id),
            "tool_name": tc.tool_name,
            "step_index": tc.step_index,
            "input_data": tc.input_data,
            "output_data": tc.output_data,
            "status": tc.status,
            "latency_ms": tc.latency_ms,
            "error_message": tc.error_message,
            "started_at": tc.started_at.isoformat() if tc.started_at else None,
            "ended_at": tc.ended_at.isoformat() if tc.ended_at else None,
        }
        for tc in rows
    ]


@router.get("/{session_id}/events")
async def get_investigation_events(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    event_bus: EventBus = Depends(get_event_bus),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    """SSE stream for investigation events (spec §11.3).

    1. Replay historical tool_calls from the database.
    2. If the session is still running, switch to live EventBus tailing.
    3. If the session is terminal, close after replay.
    """
    session = await db.get(InvestigationSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Investigation session not found")

    # Eagerly load tool calls before StreamingResponse — the DB session
    # dependency is cleaned up by FastAPI before the generator finishes.
    tool_calls = await _load_tool_calls_as_dicts(db, session_id)
    is_terminal = session.status in TERMINAL_STATUSES
    channel = STREAM_CHANNEL.format(session_id=session_id)

    # Pre-build replay frames (no DB access needed in the generator)
    replay_frames = _build_replay_frames(tool_calls, last_event_id)

    async def event_generator() -> AsyncGenerator[str, None]:
        # Phase 1 — replay DB history
        for frame in replay_frames:
            yield frame

        # Phase 2 — live tail (only if session is still running)
        if not is_terminal:
            async for event in event_bus.subscribe(channel, last_event_id):
                event_type = event.get("type", "unknown")
                yield _sse_frame(str(uuid.uuid4()), event_type, event)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
