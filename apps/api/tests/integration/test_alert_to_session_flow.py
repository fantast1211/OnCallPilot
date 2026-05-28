"""Integration test: Alertmanager webhook → incident → investigation session.

Requires real PostgreSQL and Redis via ONCALLPILOT_CONFIG.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

import pytest
import yaml
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from oncallpilot_api.db.models import Incident, InvestigationSession


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def config() -> dict:
    config_path = os.environ.get("ONCALLPILOT_CONFIG")
    if not config_path:
        pytest.skip("ONCALLPILOT_CONFIG not set")
    with Path(config_path).open() as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="module")
def pg_url(config: dict) -> str:
    return config["datasources"]["postgres"]["url"]


@pytest.fixture(scope="module")
def settings(config: dict):
    from oncallpilot_api.config import Settings
    from unittest.mock import patch

    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key-for-integration"}):
        return Settings()


@pytest.fixture
async def session_factory(pg_url: str):
    engine = create_async_engine(pg_url, echo=False, pool_pre_ping=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def app(config):
    """Create a FastAPI app wired to the real config."""
    from oncallpilot_api.dependencies import get_settings
    from oncallpilot_api.main import create_app

    get_settings.cache_clear()
    yield create_app()
    get_settings.cache_clear()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _firing_payload(fingerprint: str | None = None) -> dict:
    fp = fingerprint or f"fp-integ-{uuid.uuid4().hex[:8]}"
    return {
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "service": "integration-test-svc",
                    "severity": "warning",
                    "alertname": "TestAlert",
                },
                "annotations": {
                    "summary": "integration test alert",
                    "description": "auto-generated for e2e test",
                },
                "fingerprint": fp,
                "startsAt": "2026-05-29T10:00:00Z",
            }
        ]
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_firing_alert_creates_incident_and_session(
    client: AsyncClient,
    session_factory: async_sessionmaker,
):
    """End-to-end: firing alert → incident row → investigation session row."""
    payload = _firing_payload()

    resp = await client.post("/api/v1/alerts/alertmanager", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] is True
    incident_id = body["incident_id"]
    session_id = body["session_id"]
    assert session_id is not None

    # Verify incident row
    async with session_factory() as db:
        inc = await db.get(Incident, uuid.UUID(incident_id))
        assert inc is not None
        assert inc.fingerprint == payload["alerts"][0]["fingerprint"]
        assert inc.status == "open"
        assert inc.service == "integration-test-svc"
        assert inc.severity == "warning"

    # Verify investigation session row
    async with session_factory() as db:
        sess = await db.get(InvestigationSession, uuid.UUID(session_id))
        assert sess is not None
        assert sess.incident_id == uuid.UUID(incident_id)
        assert sess.status == "pending"


@pytest.mark.asyncio
async def test_duplicate_firing_is_idempotent(
    client: AsyncClient,
    session_factory: async_sessionmaker,
):
    """Second firing with same fingerprint → created=False, same incident."""
    fp = f"fp-integ-dup-{uuid.uuid4().hex[:8]}"
    payload = _firing_payload(fingerprint=fp)

    # First firing
    resp1 = await client.post("/api/v1/alerts/alertmanager", json=payload)
    assert resp1.status_code == 200
    body1 = resp1.json()
    assert body1["created"] is True

    # Second firing with same fingerprint
    resp2 = await client.post("/api/v1/alerts/alertmanager", json=payload)
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["created"] is False
    assert body2["incident_id"] == body1["incident_id"]
    assert body2["session_id"] is None


@pytest.mark.asyncio
async def test_resolved_alert_marks_incident(
    client: AsyncClient,
    session_factory: async_sessionmaker,
):
    """Firing then resolved → incident status changes to resolved."""
    fp = f"fp-integ-res-{uuid.uuid4().hex[:8]}"

    # Fire
    firing = _firing_payload(fingerprint=fp)
    resp = await client.post("/api/v1/alerts/alertmanager", json=firing)
    assert resp.status_code == 200
    incident_id = resp.json()["incident_id"]

    # Resolve
    resolved = {
        "alerts": [
            {
                **firing["alerts"][0],
                "status": "resolved",
            }
        ]
    }
    resp2 = await client.post("/api/v1/alerts/alertmanager", json=resolved)
    assert resp2.status_code == 200
    assert resp2.json()["incident_id"] == incident_id
    assert resp2.json()["created"] is False

    # Verify in DB
    async with session_factory() as db:
        inc = await db.get(Incident, uuid.UUID(incident_id))
        assert inc is not None
        assert inc.status == "resolved"
        assert inc.resolved_at is not None
        assert inc.closed_reason == "alertmanager: resolved"
