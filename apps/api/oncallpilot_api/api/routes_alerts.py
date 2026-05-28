"""Alertmanager webhook endpoint (spec §6.1 / §6.8 / §8.1)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oncallpilot_api.api.schemas import (
    AlertmanagerWebhookRequest,
    AlertmanagerWebhookResponse,
)
from oncallpilot_api.config import Settings
from oncallpilot_api.db.models import Incident
from oncallpilot_api.db.repositories import (
    create_incident_with_fingerprint_dedup,
    mark_incident_resolved,
)
from oncallpilot_api.db.session import get_db_session
from oncallpilot_api.dependencies import get_config, get_event_bus, get_settings
from oncallpilot_api.services.event_bus import EventBus
from oncallpilot_api.services.investigation_service import InvestigationService

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


def _parse_starts_at(raw: str) -> datetime | None:
    """Best-effort parse of Alertmanager's startsAt timestamp."""
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


@router.post("/alertmanager", response_model=AlertmanagerWebhookResponse)
async def alertmanager_webhook(
    body: AlertmanagerWebhookRequest,
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_config),
    event_bus: EventBus = Depends(get_event_bus),
) -> AlertmanagerWebhookResponse:
    """Receive an Alertmanager webhook and create or resolve incidents (spec §6.8)."""
    first = body.alerts[0]

    # --- extract fields from the first alert ---
    service = first.labels.get("service")
    if not service:
        raise HTTPException(status_code=400, detail="Missing required label: service")

    severity = first.labels.get("severity", "warning")
    description = first.annotations.get("description") or first.annotations.get("summary")
    fingerprint = first.fingerprint
    started_at = _parse_starts_at(first.startsAt)

    if first.status == "firing":
        incident, created = await create_incident_with_fingerprint_dedup(
            db,
            fp=fingerprint,
            severity=severity,
            service=service,
            description=description,
            started_at=started_at,
        )

        session_id: str | None = None
        if created:
            svc = InvestigationService(db=db, event_bus=event_bus, settings=settings)
            session_id = await svc.enqueue(
                incident_id=str(incident.id),
                source="alertmanager",
            )

        return AlertmanagerWebhookResponse(
            incident_id=str(incident.id),
            session_id=session_id,
            created=created,
        )

    # --- status == "resolved" ---
    stmt = select(Incident).where(
        Incident.fingerprint == fingerprint,
        Incident.status.in_(["open", "investigating"]),
    )
    result = await db.execute(stmt)
    existing = result.scalars().first()

    if existing is None:
        raise HTTPException(
            status_code=404,
            detail=f"No open incident found for fingerprint {fingerprint}",
        )

    resolved = await mark_incident_resolved(db, existing.id)
    if resolved is not None:
        resolved.closed_reason = "alertmanager: resolved"
        await db.flush()

    return AlertmanagerWebhookResponse(
        incident_id=str(existing.id),
        session_id=None,
        created=False,
    )
