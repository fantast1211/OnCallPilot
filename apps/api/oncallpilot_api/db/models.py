"""SQLAlchemy models for OnCallPilot."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ---------------------------------------------------------------------------
# Status validation constants
# ---------------------------------------------------------------------------

INCIDENT_STATUSES: set[str] = {"open", "investigating", "resolved", "error"}
INVESTIGATION_SESSION_STATUSES: set[str] = {"pending", "running", "completed", "failed"}
CHAT_SESSION_STATUSES: set[str] = {"active", "completed"}
CHAT_MESSAGE_ROLES: set[str] = {"user", "assistant", "system"}
TOOL_CALL_STATUSES: set[str] = {"pending", "running", "success", "failed"}
REMEDIATION_ACTION_STATUSES: set[str] = {"pending", "approved", "executed", "failed"}
DATASOURCE_HEALTH_STATUSES: set[str] = {"healthy", "degraded", "unreachable", "unknown"}


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    fingerprint: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    service: Mapped[str | None] = mapped_column(String(256))
    namespace: Mapped[str | None] = mapped_column(String(256))
    cluster: Mapped[str | None] = mapped_column(String(256))
    description: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_reason: Mapped[str | None] = mapped_column(Text)
    reopen_count: Mapped[int] = mapped_column(Integer, default=0)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    investigation_sessions: Mapped[list[InvestigationSession]] = relationship(
        back_populates="incident"
    )
    memories: Mapped[list[IncidentMemory]] = relationship(back_populates="incident")
    remediation_actions: Mapped[list[RemediationAction]] = relationship(
        back_populates="incident"
    )

    __table_args__ = (
        Index(
            "ix_incidents_fingerprint_open",
            "fingerprint",
            postgresql_where="status IN ('open', 'investigating')",
            unique=True,
        ),
    )


class InvestigationSession(Base):
    __tablename__ = "investigation_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    job_id: Mapped[str | None] = mapped_column(String(256))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    incident: Mapped[Incident] = relationship(
        back_populates="investigation_sessions"
    )
    chat_sessions: Mapped[list[ChatSession]] = relationship(
        back_populates="investigation_session"
    )
    tool_calls: Mapped[list[ToolCall]] = relationship(
        back_populates="investigation_session",
        foreign_keys="ToolCall.investigation_session_id",
    )


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    investigation_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("investigation_sessions.id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    investigation_session: Mapped[InvestigationSession] = relationship(
        back_populates="chat_sessions"
    )
    messages: Mapped[list[ChatMessage]] = relationship(back_populates="chat_session")
    tool_calls: Mapped[list[ToolCall]] = relationship(
        back_populates="chat_session",
        foreign_keys="ToolCall.chat_session_id",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    chat_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    chat_session: Mapped[ChatSession] = relationship(back_populates="messages")


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    investigation_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("investigation_sessions.id"),
    )
    chat_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id"),
    )
    tool_name: Mapped[str] = mapped_column(String(256), nullable=False)
    input_data: Mapped[dict | None] = mapped_column(JSONB)
    output_data: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    step_index: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    investigation_session: Mapped[InvestigationSession | None] = relationship(
        back_populates="tool_calls",
        foreign_keys=[investigation_session_id],
    )
    chat_session: Mapped[ChatSession | None] = relationship(
        back_populates="tool_calls",
        foreign_keys=[chat_session_id],
    )

    __table_args__ = (
        CheckConstraint(
            "(investigation_session_id IS NOT NULL AND chat_session_id IS NULL) "
            "OR (investigation_session_id IS NULL AND chat_session_id IS NOT NULL)",
            name="ck_tool_call_single_session_ref",
        ),
    )


class RunbookDocument(Base):
    __tablename__ = "runbook_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    service: Mapped[str | None] = mapped_column(String(256))
    tags: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class IncidentMemory(Base):
    __tablename__ = "incident_memories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[dict | None] = mapped_column(JSONB)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    incident: Mapped[Incident] = relationship(back_populates="memories")


class RemediationAction(Base):
    __tablename__ = "remediation_actions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False
    )
    action_type: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    parameters: Mapped[dict | None] = mapped_column(JSONB)
    result: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    incident: Mapped[Incident] = relationship(back_populates="remediation_actions")


class ServiceCatalogEntry(Base):
    __tablename__ = "service_catalog_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    service_name: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    team: Mapped[str | None] = mapped_column(String(256))
    contacts: Mapped[dict | None] = mapped_column(JSONB)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DatasourceStatus(Base):
    __tablename__ = "datasource_status"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unknown"
    )
    latency_ms: Mapped[float | None] = mapped_column(Float)
    detail: Mapped[str | None] = mapped_column(Text)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
