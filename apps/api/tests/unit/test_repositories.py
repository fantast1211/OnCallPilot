"""Tests for repository CRUD functions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event, text, JSON, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from oncallpilot_api.db.models import (
    Base,
    ChatMessage,
    ChatSession,
    Incident,
    InvestigationSession,
    ToolCall,
)


# ---------------------------------------------------------------------------
# Type mapping helper for SQLite compatibility
# ---------------------------------------------------------------------------

# Map PostgreSQL-specific types to SQLite-compatible ones for DDL rendering
_TYPE_MAP = {
    "UUID": String(36),
    "JSONB": JSON(),
}


def _render_item(type_, obj, autogen_context):
    """Custom render_item that maps PostgreSQL types to SQLite-compatible ones."""
    impl = type_().compile()
    type_name = type(impl).__name__
    if "UUID" in type_name:
        return "VARCHAR(36)"
    if "JSONB" in type_name:
        return "JSON"
    return False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
async def db_session():
    """Create an async SQLite in-memory session for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Use the sync engine to create tables with type adaptation
    sync_engine = engine.sync_engine

    from sqlalchemy import MetaData
    from sqlalchemy.dialects import sqlite

    # Clone metadata and adapt types for SQLite
    test_metadata = MetaData()
    for table in Base.metadata.tables.values():
        # Build new columns with adapted types
        from sqlalchemy import Column, Table
        new_cols = []
        for col in table.columns:
            col_type = col.type
            type_str = type(col_type).__name__
            if type_str == "UUID":
                col_type = String(36)
            elif type_str == "JSONB":
                col_type = JSON()
            new_cols.append(col.copy())
            new_cols[-1].type = col_type

        Table(
            table.name,
            test_metadata,
            *new_cols,
        )

    # Also copy constraints/indexes from original tables
    for table_name, table in Base.metadata.tables.items():
        test_table = test_metadata.tables[table_name]
        for idx in table.indexes:
            # Skip partial indexes (not supported in SQLite)
            if idx.dialect_options.get("postgresql", {}).get("where"):
                continue
            new_idx = idx.copy(target_table=test_table)
        for const in table.constraints:
            if hasattr(const, "copy"):
                try:
                    new_const = const.copy(target_table=test_table)
                except Exception:
                    pass

    async with engine.begin() as conn:
        await conn.run_sync(test_metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(test_metadata.drop_all)
    await engine.dispose()


def _uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Tests: create_incident_with_fingerprint_dedup
# ---------------------------------------------------------------------------


class TestCreateIncidentWithFingerprintDedup:
    async def test_creates_new_incident(self, db_session: AsyncSession):
        from oncallpilot_api.db.repositories import create_incident_with_fingerprint_dedup

        incident, created = await create_incident_with_fingerprint_dedup(
            db_session,
            fingerprint="fp-001",
            severity="critical",
            service="api-gateway",
            namespace="production",
            cluster="us-east-1",
            description="Pod crash loop",
        )
        assert incident.id is not None
        assert incident.fingerprint == "fp-001"
        assert incident.severity == "critical"
        assert incident.status == "open"
        assert incident.service == "api-gateway"
        assert created is True

    async def test_dedup_returns_existing_open_incident(self, db_session: AsyncSession):
        from oncallpilot_api.db.repositories import create_incident_with_fingerprint_dedup

        first, created1 = await create_incident_with_fingerprint_dedup(
            db_session, fingerprint="fp-dup", severity="warning",
        )
        second, created2 = await create_incident_with_fingerprint_dedup(
            db_session, fingerprint="fp-dup", severity="critical",
        )
        assert first.id == second.id
        assert second.status == "open"
        assert created1 is True
        assert created2 is False

    async def test_dedup_creates_new_after_resolved(self, db_session: AsyncSession):
        from oncallpilot_api.db.repositories import create_incident_with_fingerprint_dedup, mark_incident_resolved

        first, _c1 = await create_incident_with_fingerprint_dedup(
            db_session, fingerprint="fp-resolved", severity="warning",
        )
        await mark_incident_resolved(db_session, first.id)
        await db_session.flush()

        second, _c2 = await create_incident_with_fingerprint_dedup(
            db_session, fingerprint="fp-resolved", severity="critical",
        )
        assert second.id != first.id
        assert second.status == "open"


# ---------------------------------------------------------------------------
# Tests: create_investigation_session
# ---------------------------------------------------------------------------


class TestCreateInvestigationSession:
    async def test_creates_session(self, db_session: AsyncSession):
        from oncallpilot_api.db.repositories import (
            create_incident_with_fingerprint_dedup,
            create_investigation_session,
        )

        incident, _created = await create_incident_with_fingerprint_dedup(
            db_session, fingerprint="fp-sess", severity="critical",
        )
        session = await create_investigation_session(
            db_session, incident_id=incident.id, metadata_={"trigger": "alert"},
        )
        assert session.id is not None
        assert session.incident_id == incident.id
        assert session.status == "pending"
        assert session.metadata_ == {"trigger": "alert"}


# ---------------------------------------------------------------------------
# Tests: append_tool_call
# ---------------------------------------------------------------------------


class TestAppendToolCall:
    async def test_appends_tool_call_to_investigation(self, db_session: AsyncSession):
        from oncallpilot_api.db.repositories import (
            append_tool_call,
            create_incident_with_fingerprint_dedup,
            create_investigation_session,
        )

        incident, _created = await create_incident_with_fingerprint_dedup(
            db_session, fp="fp-tc", severity="high",
        )
        inv = await create_investigation_session(db_session, incident_id=incident.id)
        tc = await append_tool_call(
            db_session,
            investigation_session_id=inv.id,
            tool_name="kubectl_get_pods",
            input_data={"namespace": "prod"},
            output_data={"pods": [{"name": "api-1", "status": "CrashLoop"}]},
        )
        assert tc.id is not None
        assert tc.tool_name == "kubectl_get_pods"
        assert tc.status == "success"
        assert tc.investigation_session_id == inv.id

    async def test_appends_tool_call_to_chat_session(self, db_session: AsyncSession):
        from oncallpilot_api.db.repositories import (
            append_tool_call,
            create_chat_session,
            create_incident_with_fingerprint_dedup,
            create_investigation_session,
        )

        incident, _created = await create_incident_with_fingerprint_dedup(
            db_session, fp="fp-tc-chat", severity="high",
        )
        inv = await create_investigation_session(db_session, incident_id=incident.id)
        chat = await create_chat_session(db_session, investigation_session_id=inv.id)
        tc = await append_tool_call(
            db_session,
            chat_session_id=chat.id,
            tool_name="search_logs",
            input_data={"query": "error"},
        )
        assert tc.chat_session_id == chat.id
        assert tc.investigation_session_id is None


# ---------------------------------------------------------------------------
# Tests: mark_incident_resolved
# ---------------------------------------------------------------------------


class TestMarkIncidentResolved:
    async def test_marks_resolved(self, db_session: AsyncSession):
        from oncallpilot_api.db.repositories import (
            create_incident_with_fingerprint_dedup,
            mark_incident_resolved,
        )

        incident, _created = await create_incident_with_fingerprint_dedup(
            db_session, fp="fp-res", severity="critical",
        )
        result = await mark_incident_resolved(db_session, incident.id)
        assert result is not None
        assert result.status == "resolved"
        assert result.resolved_at is not None

    async def test_returns_none_for_nonexistent(self, db_session: AsyncSession):
        from oncallpilot_api.db.repositories import mark_incident_resolved

        result = await mark_incident_resolved(db_session, uuid.uuid4())
        assert result is None


# ---------------------------------------------------------------------------
# Tests: list_recent_incidents
# ---------------------------------------------------------------------------


class TestListRecentIncidents:
    async def test_lists_ordered_by_created_at(self, db_session: AsyncSession):
        from oncallpilot_api.db.repositories import (
            create_incident_with_fingerprint_dedup,
            list_recent_incidents,
        )

        await create_incident_with_fingerprint_dedup(db_session, fp="fp-1", severity="low")
        await create_incident_with_fingerprint_dedup(db_session, fp="fp-2", severity="high")
        await create_incident_with_fingerprint_dedup(db_session, fp="fp-3", severity="critical")

        results = await list_recent_incidents(db_session, limit=10)
        assert len(results) == 3

    async def test_respects_limit(self, db_session: AsyncSession):
        from oncallpilot_api.db.repositories import (
            create_incident_with_fingerprint_dedup,
            list_recent_incidents,
        )

        for i in range(5):
            await create_incident_with_fingerprint_dedup(
                db_session, fp=f"fp-limit-{i}", severity="low",
            )

        results = await list_recent_incidents(db_session, limit=2)
        assert len(results) == 2


# ---------------------------------------------------------------------------
# Tests: get_investigation_detail
# ---------------------------------------------------------------------------


class TestGetInvestigationDetail:
    async def test_returns_detail_with_relations(self, db_session: AsyncSession):
        from oncallpilot_api.db.repositories import (
            append_tool_call,
            append_chat_message,
            create_chat_session,
            create_incident_with_fingerprint_dedup,
            create_investigation_session,
            get_investigation_detail,
        )

        incident, _created = await create_incident_with_fingerprint_dedup(
            db_session, fp="fp-detail", severity="critical", service="payments",
        )
        inv = await create_investigation_session(db_session, incident_id=incident.id)
        await append_tool_call(
            db_session, investigation_session_id=inv.id, tool_name="kubectl_logs",
        )
        chat = await create_chat_session(db_session, investigation_session_id=inv.id)
        await append_chat_message(db_session, chat_session_id=chat.id, role="user", content="Why is it failing?")

        detail = await get_investigation_detail(db_session, inv.id)
        assert detail is not None
        assert detail.id == inv.id
        assert detail.incident is not None
        assert detail.incident.fingerprint == "fp-detail"
        assert len(detail.tool_calls) == 1
        assert len(detail.chat_sessions) == 1

    async def test_returns_none_for_nonexistent(self, db_session: AsyncSession):
        from oncallpilot_api.db.repositories import get_investigation_detail

        result = await get_investigation_detail(db_session, uuid.uuid4())
        assert result is None


# ---------------------------------------------------------------------------
# Tests: create_chat_session / append_chat_message
# ---------------------------------------------------------------------------


class TestChatSessionAndMessages:
    async def test_creates_chat_session(self, db_session: AsyncSession):
        from oncallpilot_api.db.repositories import (
            create_chat_session,
            create_incident_with_fingerprint_dedup,
            create_investigation_session,
        )

        incident, _created = await create_incident_with_fingerprint_dedup(
            db_session, fp="fp-chat", severity="high",
        )
        inv = await create_investigation_session(db_session, incident_id=incident.id)
        chat = await create_chat_session(db_session, investigation_session_id=inv.id)
        assert chat.id is not None
        assert chat.status == "active"
        assert chat.investigation_session_id == inv.id

    async def test_appends_chat_message(self, db_session: AsyncSession):
        from oncallpilot_api.db.repositories import (
            append_chat_message,
            create_chat_session,
            create_incident_with_fingerprint_dedup,
            create_investigation_session,
        )

        incident, _created = await create_incident_with_fingerprint_dedup(
            db_session, fp="fp-msg", severity="high",
        )
        inv = await create_investigation_session(db_session, incident_id=incident.id)
        chat = await create_chat_session(db_session, investigation_session_id=inv.id)
        msg = await append_chat_message(
            db_session, chat_session_id=chat.id, role="user", content="What's wrong?",
        )
        assert msg.id is not None
        assert msg.role == "user"
        assert msg.content == "What's wrong?"

    async def test_multiple_messages_ordered(self, db_session: AsyncSession):
        from oncallpilot_api.db.repositories import (
            append_chat_message,
            create_chat_session,
            create_incident_with_fingerprint_dedup,
            create_investigation_session,
        )

        incident, _created = await create_incident_with_fingerprint_dedup(
            db_session, fp="fp-multi", severity="high",
        )
        inv = await create_investigation_session(db_session, incident_id=incident.id)
        chat = await create_chat_session(db_session, investigation_session_id=inv.id)

        await append_chat_message(db_session, chat_session_id=chat.id, role="user", content="First")
        await append_chat_message(db_session, chat_session_id=chat.id, role="assistant", content="Second")
        await append_chat_message(db_session, chat_session_id=chat.id, role="user", content="Third")

        await db_session.refresh(chat, attribute_names=["messages"])
        assert len(chat.messages) == 3
        assert chat.messages[0].content == "First"
        assert chat.messages[2].content == "Third"
