"""Incident REST API (spec §6.1 / §6.2)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from oncallpilot_api.api.schemas import (
    CloseIncidentRequest,
    CreateInvestigationRequest,
    IncidentDetailResponse,
    IncidentListResponse,
    IncidentResponse,
    InvestigationSessionResponse,
    ReopenIncidentRequest,
)
from oncallpilot_api.config import Settings
from oncallpilot_api.db.models import Incident
from oncallpilot_api.db.repositories import (
    close_incident,
    count_incidents,
    get_incident_detail,
    list_recent_incidents,
    reopen_incident,
)
from oncallpilot_api.db.session import get_db_session
from oncallpilot_api.dependencies import get_config, get_event_bus, get_settings
from oncallpilot_api.services.event_bus import EventBus
from oncallpilot_api.services.investigation_service import InvestigationService

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


def _incident_response(inc: Incident) -> IncidentResponse:
    return IncidentResponse(
        id=str(inc.id),
        fingerprint=inc.fingerprint,
        status=inc.status,
        severity=inc.severity,
        service=inc.service,
        description=inc.description,
        started_at=inc.started_at,
        resolved_at=inc.resolved_at,
        closed_at=inc.closed_at,
        closed_reason=inc.closed_reason,
        reopen_count=inc.reopen_count,
        created_at=inc.created_at,
        updated_at=inc.updated_at,
    )


@router.get("", response_model=IncidentListResponse)
async def list_incidents(
    limit: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    service: str | None = Query(None),
    db: AsyncSession = Depends(get_db_session),
) -> IncidentListResponse:
    """List recent incidents with optional status/service filters."""
    items = await list_recent_incidents(db, limit=limit, status=status, service=service)
    total = await count_incidents(db, status=status, service=service)
    return IncidentListResponse(
        items=[_incident_response(i) for i in items],
        total=total,
    )


@router.get("/{incident_id}", response_model=IncidentDetailResponse)
async def get_incident(
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> IncidentDetailResponse:
    """Get incident detail with associated investigation sessions."""
    inc = await get_incident_detail(db, incident_id)
    if inc is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    sessions = [
        InvestigationSessionResponse(
            id=str(s.id),
            incident_id=str(s.incident_id),
            status=s.status,
            started_at=s.started_at,
            ended_at=s.ended_at,
        )
        for s in (inc.investigation_sessions or [])
    ]
    return IncidentDetailResponse(
        **_incident_response(inc).model_dump(),
        investigation_sessions=sessions,
    )


@router.post("/{incident_id}/close", response_model=IncidentResponse)
async def close_incident_endpoint(
    incident_id: uuid.UUID,
    body: CloseIncidentRequest,
    db: AsyncSession = Depends(get_db_session),
) -> IncidentResponse:
    """Close an incident."""
    inc = await close_incident(db, incident_id, body.reason)
    if inc is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return _incident_response(inc)


@router.post("/{incident_id}/reopen", response_model=IncidentResponse)
async def reopen_incident_endpoint(
    incident_id: uuid.UUID,
    body: ReopenIncidentRequest,
    db: AsyncSession = Depends(get_db_session),
) -> IncidentResponse:
    """Reopen a closed incident."""
    inc = await reopen_incident(db, incident_id, body.reason)
    if inc is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return _incident_response(inc)


@router.post("/{incident_id}/investigations")
async def create_investigation(
    incident_id: uuid.UUID,
    body: CreateInvestigationRequest | None = None,
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_config),
    event_bus: EventBus = Depends(get_event_bus),
) -> dict[str, str]:
    """Start a new investigation on an existing incident."""
    # Verify incident exists
    inc = await get_incident_detail(db, incident_id)
    if inc is None:
        raise HTTPException(status_code=404, detail="Incident not found")

    svc = InvestigationService(db=db, event_bus=event_bus, settings=settings)
    extra = (body or CreateInvestigationRequest()).extra_context
    source = "manual"
    query = None
    if extra:
        source = extra.get("source", source)
        query = extra.get("query", query)

    session_id = await svc.enqueue(
        incident_id=str(incident_id),
        source=source,
        query=query,
    )
    return {"session_id": session_id}
