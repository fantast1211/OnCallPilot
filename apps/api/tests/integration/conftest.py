"""Shared fixtures for integration tests."""

from __future__ import annotations

import os

import pytest
from sqlalchemy.ext.asyncio import create_async_engine


def _db_url() -> str | None:
    """Return the database URL from ONCALLPILOT_DATABASE_URL or None."""
    return os.environ.get("ONCALLPILOT_DATABASE_URL")


@pytest.fixture(scope="session")
def db_url() -> str:
    """Return the database URL, skipping the entire session if unavailable."""
    url = _db_url()
    if not url:
        pytest.skip("ONCALLPILOT_DATABASE_URL not set — skipping integration tests")
    return url


@pytest.fixture(scope="session")
def config_path() -> str:
    """Return the config file path, skipping if unavailable."""
    path = os.environ.get("ONCALLPILOT_CONFIG")
    if not path:
        pytest.skip("ONCALLPILOT_CONFIG not set — skipping integration tests")
    return path


@pytest.fixture(scope="session")
async def engine(db_url: str):
    """Create an async engine for the test session."""
    eng = create_async_engine(db_url, echo=False, pool_pre_ping=True)
    yield eng
    await eng.dispose()
