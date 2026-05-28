"""Pydantic request/response schemas for OnCallPilot API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Alertmanager webhook
# ---------------------------------------------------------------------------


class AlertmanagerAlert(BaseModel):
    """Single alert from an Alertmanager webhook payload."""

    status: str
    labels: dict[str, str]
    annotations: dict[str, str]
    fingerprint: str
    startsAt: str


class AlertmanagerWebhookRequest(BaseModel):
    """Alertmanager webhook request body (spec §6.8)."""

    alerts: list[AlertmanagerAlert]


class AlertmanagerWebhookResponse(BaseModel):
    """Response after processing an Alertmanager webhook."""

    incident_id: str
    session_id: str | None = None
    created: bool


# ---------------------------------------------------------------------------
# Incident
# ---------------------------------------------------------------------------


class IncidentResponse(BaseModel):
    """Serialized incident."""

    id: str
    fingerprint: str
    status: str
    severity: str
    service: str | None = None
    description: str | None = None
    started_at: datetime | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    closed_reason: str | None = None
    reopen_count: int
    created_at: datetime
    updated_at: datetime


class IncidentListResponse(BaseModel):
    """Paginated list of incidents."""

    items: list[IncidentResponse]
    total: int


class IncidentDetailResponse(IncidentResponse):
    """Incident with associated investigation sessions."""

    investigation_sessions: list[InvestigationSessionResponse]


class CloseIncidentRequest(BaseModel):
    """Request body for closing an incident."""

    reason: str


class ReopenIncidentRequest(BaseModel):
    """Request body for reopening an incident."""

    reason: str


class CreateInvestigationRequest(BaseModel):
    """Request body for starting a new investigation on an incident."""

    extra_context: dict | None = None


# ---------------------------------------------------------------------------
# Investigation session
# ---------------------------------------------------------------------------


class InvestigationSessionResponse(BaseModel):
    """Serialized investigation session."""

    id: str
    incident_id: str
    status: str
    started_at: datetime
    ended_at: datetime | None = None


class ManualInvestigationRequest(BaseModel):
    """Request body for creating a manual investigation (not tied to existing incident)."""

    query: str
    mode: str = "monitor"
    context: dict = {}


class InvestigationDetailResponse(InvestigationSessionResponse):
    """Investigation session with tool calls."""

    tool_calls: list[ToolCallResponse]


class ToolCallResponse(BaseModel):
    """Serialized tool call record."""

    id: str
    tool_name: str
    status: str
    input_data: dict | None = None
    output_data: dict | None = None
    step_index: int | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    latency_ms: int | None = None
    error_message: str | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


class ChatSessionResponse(BaseModel):
    """Serialized chat session."""

    id: str
    investigation_session_id: str
    status: str
    created_at: datetime
    updated_at: datetime


class CreateChatSessionRequest(BaseModel):
    """Request body for creating a chat session."""

    investigation_session_id: str


class AppendChatMessageRequest(BaseModel):
    """Request body for appending a message to a chat session."""

    role: str
    content: str


class ChatMessageResponse(BaseModel):
    """Serialized chat message."""

    id: str
    role: str
    content: str
    created_at: datetime
