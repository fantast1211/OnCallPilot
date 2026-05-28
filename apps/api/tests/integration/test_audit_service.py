"""Integration tests for audit_service."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import event, text, JSON, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from oncallpilot_api.db.models import Base, ToolCall


# ---------------------------------------------------------------------------
# SQLite-compatible session fixture (same pattern as test_repositories.py)
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

    test_metadata = Base.metadata
    async with engine.begin() as conn:
        await conn.run_sync(test_metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(test_metadata.drop_all)
    await engine.dispose()


# ---------------------------------------------------------------------------
# Tests: record_tool_call
# ---------------------------------------------------------------------------


class TestRecordToolCall:
    async def test_records_tool_call_to_investigation_session(self, db_session: AsyncSession):
        from oncallpilot_api.db.repositories import (
            create_incident_with_fingerprint_dedup,
            create_investigation_session,
        )
        from oncallpilot_api.services.audit_service import record_tool_call

        incident = await create_incident_with_fingerprint_dedup(
            db_session, fp="fp-audit-inv", severity="critical",
        )
        inv = await create_investigation_session(db_session, incident_id=incident.id)

        tc = await record_tool_call(
            db_session,
            investigation_session_id=inv.id,
            tool_name="query_error_logs",
            input_data={"service": "api", "start": "1h"},
            output_data={"logs": ["error1"]},
            status="success",
            step_index=0,
        )
        assert tc.id is not None
        assert tc.tool_name == "query_error_logs"
        assert tc.investigation_session_id == inv.id
        assert tc.chat_session_id is None
        assert tc.status == "success"
        assert tc.step_index == 0

    async def test_records_tool_call_to_chat_session(self, db_session: AsyncSession):
        from oncallpilot_api.db.repositories import (
            create_chat_session,
            create_incident_with_fingerprint_dedup,
            create_investigation_session,
        )
        from oncallpilot_api.services.audit_service import record_tool_call

        incident = await create_incident_with_fingerprint_dedup(
            db_session, fp="fp-audit-chat", severity="critical",
        )
        inv = await create_investigation_session(db_session, incident_id=incident.id)
        chat = await create_chat_session(db_session, investigation_session_id=inv.id)

        tc = await record_tool_call(
            db_session,
            chat_session_id=chat.id,
            tool_name="instant_query",
            input_data={"query": "up"},
            status="success",
            step_index=2,
        )
        assert tc.chat_session_id == chat.id
        assert tc.investigation_session_id is None
        assert tc.step_index == 2

    async def test_records_tool_call_without_step_index(self, db_session: AsyncSession):
        from oncallpilot_api.db.repositories import (
            create_incident_with_fingerprint_dedup,
            create_investigation_session,
        )
        from oncallpilot_api.services.audit_service import record_tool_call

        incident = await create_incident_with_fingerprint_dedup(
            db_session, fp="fp-audit-nostep", severity="high",
        )
        inv = await create_investigation_session(db_session, incident_id=incident.id)

        tc = await record_tool_call(
            db_session,
            investigation_session_id=inv.id,
            tool_name="check_tcp_port",
            status="failed",
        )
        assert tc.step_index is None
        assert tc.status == "failed"

    async def test_raises_when_both_session_ids_provided(self, db_session: AsyncSession):
        from oncallpilot_api.services.audit_service import record_tool_call

        with pytest.raises(ValueError, match="mutually exclusive"):
            await record_tool_call(
                db_session,
                investigation_session_id=uuid.uuid4(),
                chat_session_id=uuid.uuid4(),
                tool_name="test",
            )

    async def test_raises_when_no_session_id_provided(self, db_session: AsyncSession):
        from oncallpilot_api.services.audit_service import record_tool_call

        with pytest.raises(ValueError, match="Exactly one"):
            await record_tool_call(
                db_session,
                tool_name="test",
            )

    async def test_records_complete_call_chain(self, db_session: AsyncSession):
        """Verify multiple tool calls are recorded in order with step_index."""
        from oncallpilot_api.db.repositories import (
            create_incident_with_fingerprint_dedup,
            create_investigation_session,
        )
        from oncallpilot_api.services.audit_service import record_tool_call

        incident = await create_incident_with_fingerprint_dedup(
            db_session, fp="fp-audit-chain", severity="critical",
        )
        inv = await create_investigation_session(db_session, incident_id=incident.id)

        steps = [
            ("query_error_logs", {"service": "api"}, {"logs": ["e1"]}, "success"),
            ("instant_query", {"query": "rate(errors[5m])"}, {"value": 42}, "success"),
            ("check_tcp_port", {"host": "db", "port": 5432}, {"ok": True}, "success"),
        ]
        recorded = []
        for i, (name, inp, out, status) in enumerate(steps):
            tc = await record_tool_call(
                db_session,
                investigation_session_id=inv.id,
                tool_name=name,
                input_data=inp,
                output_data=out,
                status=status,
                step_index=i,
            )
            recorded.append(tc)

        assert len(recorded) == 3
        for i, tc in enumerate(recorded):
            assert tc.step_index == i
            assert tc.tool_name == steps[i][0]

        # Verify all tool calls are linked to the investigation session
        await db_session.refresh(inv, attribute_names=["tool_calls"])
        assert len(inv.tool_calls) == 3
