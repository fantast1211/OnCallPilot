"""Integration tests for Alembic database migrations.

Requires:
  - ONCALLPILOT_DATABASE_URL pointing to a real PostgreSQL database
  - ONCALLPILOT_CONFIG pointing to a valid YAML config file
"""

from __future__ import annotations

import pathlib

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

# All application tables (excluding alembic_version)
EXPECTED_APP_TABLES: list[str] = [
    "incidents",
    "investigation_sessions",
    "chat_sessions",
    "chat_messages",
    "tool_calls",
    "runbook_documents",
    "incident_memories",
    "remediation_actions",
    "service_catalog_entries",
]

MIGRATIONS_DIR = (
    pathlib.Path(__file__).resolve().parents[2]
    / "oncallpilot_api"
    / "db"
    / "migrations"
)


@pytest.fixture()
def alembic_cfg(db_url: str) -> Config:
    """Build an Alembic Config pointed at the test database."""
    cfg = Config(str(MIGRATIONS_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


async def _table_names(engine) -> set[str]:
    """Return the set of table names in the database."""
    async with engine.connect() as conn:
        names = await conn.run_sync(
            lambda sync_conn: set(inspect(sync_conn).get_table_names())
        )
    return names


@pytest.mark.asyncio
async def test_upgrade_head_creates_all_tables(alembic_cfg: Config, engine):
    """`alembic upgrade head` should create every expected application table."""
    # Ensure clean starting state
    command.downgrade(alembic_cfg, "base")

    command.upgrade(alembic_cfg, "head")

    tables = await _table_names(engine)
    for name in EXPECTED_APP_TABLES:
        assert name in tables, f"Table '{name}' missing after upgrade head"
    assert "alembic_version" in tables


@pytest.mark.asyncio
async def test_downgrade_base_drops_application_tables(alembic_cfg: Config, engine):
    """`alembic downgrade base` should drop all application tables."""
    # Ensure we start from head
    command.upgrade(alembic_cfg, "head")

    command.downgrade(alembic_cfg, "base")

    tables = await _table_names(engine)
    for name in EXPECTED_APP_TABLES:
        assert name not in tables, f"Table '{name}' still present after downgrade base"


@pytest.mark.asyncio
async def test_roundtrip_upgrade_downgrade_upgrade(alembic_cfg: Config, engine):
    """A full upgrade->downgrade->upgrade cycle should be idempotent."""
    # Downgrade to clean state
    command.downgrade(alembic_cfg, "base")

    # First upgrade
    command.upgrade(alembic_cfg, "head")
    tables_after_first = await _table_names(engine)

    # Downgrade
    command.downgrade(alembic_cfg, "base")
    tables_mid = await _table_names(engine)
    for name in EXPECTED_APP_TABLES:
        assert name not in tables_mid

    # Second upgrade
    command.upgrade(alembic_cfg, "head")
    tables_after_second = await _table_names(engine)

    assert tables_after_first == tables_after_second


@pytest.mark.asyncio
async def test_migration_creates_pgcrypto_extension(alembic_cfg: Config, engine):
    """The migration should enable the pgcrypto extension."""
    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")

    async with engine.connect() as conn:
        result = await conn.run_sync(
            lambda sync_conn: sync_conn.execute(
                __import__("sqlalchemy").text(
                    "SELECT extname FROM pg_extension WHERE extname = 'pgcrypto'"
                )
            ).fetchone()
        )
    assert result is not None, "pgcrypto extension not installed"


@pytest.mark.asyncio
async def test_migration_creates_expected_indexes(alembic_cfg: Config, engine):
    """Key indexes should exist after migration."""
    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")

    async with engine.connect() as conn:
        index_names = await conn.run_sync(lambda sync_conn: {
            idx["name"]
            for idx in inspect(sync_conn).get_indexes("incidents")
        })

    # The partial unique index on fingerprint
    assert "ix_incidents_fingerprint_open" in index_names


@pytest.mark.asyncio
async def test_migration_creates_check_constraint_on_tool_calls(
    alembic_cfg: Config, engine
):
    """Tool calls table should have the single-session-ref check constraint."""
    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")

    async with engine.connect() as conn:
        constraints = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_check_constraints("tool_calls")
        )

    names = {c["name"] for c in constraints}
    assert "ck_tool_call_single_session_ref" in names
