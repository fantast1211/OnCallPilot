"""Alembic environment configuration for async PostgreSQL migrations."""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import all models so Base.metadata is populated
from oncallpilot_api.db.models import Base  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# URL resolution: read from ONCALLPILOT_DATABASE_URL env var
# ---------------------------------------------------------------------------


def _get_url() -> str:
    # Priority 1: ONCALLPILOT_DATABASE_URL (backward compat / explicit override)
    url = os.environ.get("ONCALLPILOT_DATABASE_URL", "")
    if url:
        return url

    # Priority 2: Read from ONCALLPILOT_CONFIG YAML
    config_path = os.environ.get("ONCALLPILOT_CONFIG", "")
    if config_path:
        import yaml
        from pathlib import Path
        with Path(config_path).open() as fh:
            data = yaml.safe_load(fh)
        pg_url = (data.get("datasources", {}).get("postgres", {}).get("url", ""))
        if pg_url:
            return pg_url

    raise RuntimeError(
        "Cannot determine database URL. Set ONCALLPILOT_DATABASE_URL or "
        "ensure ONCALLPILOT_CONFIG points to a YAML with datasources.postgres.url"
    )


# ---------------------------------------------------------------------------
# Offline mode (generates SQL scripts, no live connection)
# ---------------------------------------------------------------------------


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL to stdout."""
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online mode (runs against a live database)
# ---------------------------------------------------------------------------


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with a given synchronous connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations."""
    url = _get_url()
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online migrations — delegates to async runner."""
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
