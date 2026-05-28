"""Unit tests for audit_service.record_tool_call validation."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Column, MetaData, Table, event, JSON, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
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

    # Clone metadata and adapt PostgreSQL types for SQLite
    test_metadata = MetaData()
    for table in Base.metadata.tables.values():
        new_cols = []
        for col in table.columns:
            col_type = col.type
            type_name = type(col_type).__name__
            if type_name == "UUID":
                col_type = String(36)
            elif type_name == "JSONB":
                col_type = JSON()
            new_cols.append(col.copy())
            new_cols[-1].type = col_type
        Table(table.name, test_metadata, *new_cols)

    # Copy constraints/indexes, skipping partial indexes
    for table_name, table in Base.metadata.tables.items():
        test_table = test_metadata.tables[table_name]
        for idx in table.indexes:
            if idx.dialect_options.get("postgresql", {}).get("where"):
                continue
            idx.copy(target_table=test_table)
        for const in table.constraints:
            if hasattr(const, "copy"):
                try:
                    const.copy(target_table=test_table)
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

        incident, _created = await create_incident_with_fingerprint_dedup(
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

        incident, _created = await create_incident_with_fingerprint_dedup(
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
