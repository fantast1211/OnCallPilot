"""Unit tests for audit_service.record_tool_call validation."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import event, JSON, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from oncallpilot_api.db.models import Base


@pytest.fixture()
async def db_session():
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


class TestRecordToolCallValidation:
    async def test_raises_when_both_ids_given(self, db_session: AsyncSession):
        from oncallpilot_api.services.audit_service import record_tool_call

        with pytest.raises(ValueError, match="mutually exclusive"):
            await record_tool_call(
                db_session,
                investigation_session_id=uuid.uuid4(),
                chat_session_id=uuid.uuid4(),
                tool_name="test",
            )

    async def test_raises_when_no_id_given(self, db_session: AsyncSession):
        from oncallpilot_api.services.audit_service import record_tool_call

        with pytest.raises(ValueError, match="Exactly one"):
            await record_tool_call(db_session, tool_name="test")

    async def test_records_to_investigation_session(self, db_session: AsyncSession):
        from oncallpilot_api.db.repositories import (
            create_incident_with_fingerprint_dedup,
            create_investigation_session,
        )
        from oncallpilot_api.services.audit_service import record_tool_call

        incident = await create_incident_with_fingerprint_dedup(
            db_session, fp="fp-unit-audit", severity="critical",
        )
        inv = await create_investigation_session(db_session, incident_id=incident.id)

        tc = await record_tool_call(
            db_session,
            investigation_session_id=inv.id,
            tool_name="query_logs",
            input_data={"q": "error"},
            output_data={"lines": 5},
            status="success",
            step_index=1,
        )
        assert tc.tool_name == "query_logs"
        assert tc.investigation_session_id == inv.id
        assert tc.chat_session_id is None
        assert tc.step_index == 1

    async def test_records_to_chat_session(self, db_session: AsyncSession):
        from oncallpilot_api.db.repositories import (
            create_chat_session,
            create_incident_with_fingerprint_dedup,
            create_investigation_session,
        )
        from oncallpilot_api.services.audit_service import record_tool_call

        incident = await create_incident_with_fingerprint_dedup(
            db_session, fp="fp-unit-chat", severity="high",
        )
        inv = await create_investigation_session(db_session, incident_id=incident.id)
        chat = await create_chat_session(db_session, investigation_session_id=inv.id)

        tc = await record_tool_call(
            db_session,
            chat_session_id=chat.id,
            tool_name="instant_query",
            status="success",
        )
        assert tc.chat_session_id == chat.id
        assert tc.investigation_session_id is None
        assert tc.step_index is None
