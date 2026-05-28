"""Async repository functions for OnCallPilot database operations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from oncallpilot_api.db.models import (
    ChatMessage,
    ChatSession,
    DatasourceStatus,
    Incident,
    InvestigationSession,
    ToolCall,
)


async def create_incident_with_fingerprint_dedup(
    db: AsyncSession,
    *,
    fingerprint: str | None = None,
    severity: str,
    service: str | None = None,
    namespace: str | None = None,
    cluster: str | None = None,
    description: str | None = None,
    started_at: datetime | None = None,
    fp: str | None = None,
) -> tuple[Incident, bool]:
    """Create an incident, deduplicating by fingerprint for open/investigating incidents.

    If an incident with the same fingerprint already exists in 'open' or
    'investigating' status, updates last_seen_at and returns (existing, False).
    Otherwise creates a new incident and returns (new_incident, True).

    ``fp`` is accepted as a shorthand alias for ``fingerprint``.
    """
    effective_fp = fp or fingerprint
    if effective_fp is None:
        raise TypeError("Either 'fingerprint' or 'fp' must be provided")

    now = datetime.now(timezone.utc)

    # Check for existing open/investigating incident with same fingerprint
    stmt = select(Incident).where(
        Incident.fingerprint == effective_fp,
        Incident.status.in_(["open", "investigating"]),
    )
    result = await db.execute(stmt)
    existing = result.scalars().first()
    if existing is not None:
        existing.last_seen_at = now
        await db.flush()
        return existing, False

    incident = Incident(
        id=uuid.uuid4(),
        fingerprint=effective_fp,
        severity=severity,
        service=service,
        namespace=namespace,
        cluster=cluster,
        description=description,
        started_at=started_at,
        status="open",
        last_seen_at=now,
    )
    db.add(incident)
    await db.flush()
    return incident, True


async def create_investigation_session(
    db: AsyncSession,
    *,
    incident_id: uuid.UUID,
    metadata_: dict | None = None,
) -> InvestigationSession:
    """Create a new investigation session for an incident."""
    session = InvestigationSession(
        id=uuid.uuid4(),
        incident_id=incident_id,
        status="pending",
        metadata_=metadata_,
    )
    db.add(session)
    await db.flush()
    return session


async def append_tool_call(
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
    """Append a tool call record linked to either an investigation or chat session."""
    if investigation_session_id is None and chat_session_id is None:
        raise TypeError("Either investigation_session_id or chat_session_id must be provided")

    tc = ToolCall(
        id=uuid.uuid4(),
        investigation_session_id=investigation_session_id,
        chat_session_id=chat_session_id,
        tool_name=tool_name,
        input_data=input_data,
        output_data=output_data,
        status=status,
        step_index=step_index,
    )
    db.add(tc)
    await db.flush()
    return tc


async def mark_incident_resolved(
    db: AsyncSession,
    incident_id: uuid.UUID,
) -> Incident | None:
    """Mark an incident as resolved. Returns the incident or None if not found."""
    stmt = (
        update(Incident)
        .where(Incident.id == incident_id)
        .values(status="resolved", resolved_at=datetime.now(timezone.utc))
        .returning(Incident)
    )
    result = await db.execute(stmt)
    row = result.first()
    if row is None:
        return None
    # Refresh to get full ORM object
    await db.flush()
    return await db.get(Incident, incident_id)


async def list_recent_incidents(
    db: AsyncSession,
    *,
    limit: int = 20,
    status: str | None = None,
    service: str | None = None,
) -> list[Incident]:
    """Return the most recent incidents ordered by creation time (newest first).

    Optionally filter by status and/or service.
    """
    stmt = select(Incident)
    if status is not None:
        stmt = stmt.where(Incident.status == status)
    if service is not None:
        stmt = stmt.where(Incident.service == service)
    stmt = stmt.order_by(Incident.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_incidents(
    db: AsyncSession,
    *,
    status: str | None = None,
    service: str | None = None,
) -> int:
    """Count incidents with optional filters."""
    from sqlalchemy import func as sqlfunc

    stmt = select(sqlfunc.count()).select_from(Incident)
    if status is not None:
        stmt = stmt.where(Incident.status == status)
    if service is not None:
        stmt = stmt.where(Incident.service == service)
    result = await db.execute(stmt)
    return result.scalar_one()


async def get_incident_detail(
    db: AsyncSession,
    incident_id: uuid.UUID,
) -> Incident | None:
    """Load an incident with its investigation sessions eagerly."""
    stmt = (
        select(Incident)
        .where(Incident.id == incident_id)
        .options(selectinload(Incident.investigation_sessions))
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def close_incident(
    db: AsyncSession,
    incident_id: uuid.UUID,
    reason: str,
) -> Incident | None:
    """Close an incident. Returns the updated incident or None if not found."""
    incident = await db.get(Incident, incident_id)
    if incident is None:
        return None
    incident.status = "resolved"
    incident.closed_at = datetime.now(timezone.utc)
    incident.closed_reason = reason
    await db.flush()
    return incident


async def reopen_incident(
    db: AsyncSession,
    incident_id: uuid.UUID,
    reason: str,
) -> Incident | None:
    """Reopen an incident. Returns the updated incident or None if not found."""
    incident = await db.get(Incident, incident_id)
    if incident is None:
        return None
    incident.status = "open"
    incident.reopen_count = (incident.reopen_count or 0) + 1
    incident.closed_at = None
    incident.closed_reason = None
    await db.flush()
    return incident


async def get_investigation_detail(
    db: AsyncSession,
    investigation_id: uuid.UUID,
) -> InvestigationSession | None:
    """Load an investigation session with incident, tool calls, and chat sessions eagerly."""
    stmt = (
        select(InvestigationSession)
        .where(InvestigationSession.id == investigation_id)
        .options(
            selectinload(InvestigationSession.incident),
            selectinload(InvestigationSession.tool_calls),
            selectinload(InvestigationSession.chat_sessions),
        )
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def create_chat_session(
    db: AsyncSession,
    *,
    investigation_session_id: uuid.UUID,
) -> ChatSession:
    """Create a new chat session linked to an investigation session."""
    chat = ChatSession(
        id=uuid.uuid4(),
        investigation_session_id=investigation_session_id,
        status="active",
    )
    db.add(chat)
    await db.flush()
    return chat


async def append_chat_message(
    db: AsyncSession,
    *,
    chat_session_id: uuid.UUID,
    role: str,
    content: str,
) -> ChatMessage:
    """Append a message to a chat session."""
    msg = ChatMessage(
        id=uuid.uuid4(),
        chat_session_id=chat_session_id,
        role=role,
        content=content,
    )
    db.add(msg)
    await db.flush()
    return msg


async def upsert_datasource_status(
    db: AsyncSession,
    *,
    name: str,
    kind: str,
    status: str,
    latency_ms: float | None = None,
    detail: str | None = None,
) -> DatasourceStatus:
    """Insert or update a datasource status row by name."""
    stmt = select(DatasourceStatus).where(DatasourceStatus.name == name)
    result = await db.execute(stmt)
    existing = result.scalars().first()

    now = datetime.now(timezone.utc)
    if existing is not None:
        existing.kind = kind
        existing.status = status
        existing.latency_ms = latency_ms
        existing.detail = detail
        existing.last_checked_at = now
        await db.flush()
        return existing

    ds = DatasourceStatus(
        id=uuid.uuid4(),
        name=name,
        kind=kind,
        status=status,
        latency_ms=latency_ms,
        detail=detail,
        last_checked_at=now,
    )
    db.add(ds)
    await db.flush()
    return ds


async def get_all_datasource_statuses(
    db: AsyncSession,
) -> list[DatasourceStatus]:
    """Return all datasource status rows ordered by name."""
    stmt = select(DatasourceStatus).order_by(DatasourceStatus.name)
    result = await db.execute(stmt)
    return list(result.scalars().all())
