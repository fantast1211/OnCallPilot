"""Investigation REST API (spec §6.2 / §8.2)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oncallpilot_api.api.schemas import (
    InvestigationDetailResponse,
    InvestigationSessionResponse,
    ManualInvestigationRequest,
    ToolCallResponse,
)
from oncallpilot_api.config import Settings
from oncallpilot_api.db.models import Incident, InvestigationSession
from oncallpilot_api.db.repositories import (
    create_incident_with_fingerprint_dedup,
    get_investigation_detail,
)
from oncallpilot_api.db.session import get_db_session
from oncallpilot_api.dependencies import get_config, get_event_bus, get_settings
from oncallpilot_api.services.event_bus import EventBus
from oncallpilot_api.services.investigation_service import InvestigationService

router = APIRouter(prefix="/api/v1/investigations", tags=["investigations"])


@router.post("")
async def create_manual_investigation(
    body: ManualInvestigationRequest,
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_config),
    event_bus: EventBus = Depends(get_event_bus),
) -> dict[str, str]:
    """Create a manual investigation (not tied to an existing incident).

    A placeholder incident is created first, then an investigation is enqueued.
    """
    # Create a placeholder incident for this investigation
    incident, _created = await create_incident_with_fingerprint_dedup(
        db,
        fp=f"manual:{uuid.uuid4()}",
        severity="info",
        service=None,
        description=body.query,
    )

    svc = InvestigationService(db=db, event_bus=event_bus, settings=settings)
    session_id = await svc.enqueue(
        incident_id=str(incident.id),
        source="manual",
        query=body.query,
    )
    return {"session_id": session_id}


@router.get("/{session_id}", response_model=InvestigationDetailResponse)
async def get_investigation(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> InvestigationDetailResponse:
    """Get investigation session detail with tool calls."""
    session = await get_investigation_detail(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Investigation session not found")

    tool_calls = [
        ToolCallResponse(
            id=str(tc.id),
            tool_name=tc.tool_name,
            status=tc.status,
            input_data=tc.input_data,
            output_data=tc.output_data,
            step_index=tc.step_index,
            started_at=tc.started_at,
            ended_at=tc.ended_at,
            latency_ms=tc.latency_ms,
            error_message=tc.error_message,
            created_at=tc.created_at,
        )
        for tc in (session.tool_calls or [])
    ]
    return InvestigationDetailResponse(
        id=str(session.id),
        incident_id=str(session.incident_id),
        status=session.status,
        started_at=session.started_at,
        ended_at=session.ended_at,
        tool_calls=tool_calls,
    )


