"""Unit tests for the Alertmanager webhook endpoint."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from oncallpilot_api.db.session import get_db_session

# ---------------------------------------------------------------------------
# Minimal YAML config for the test app
# ---------------------------------------------------------------------------

MINIMAL_VALID_YAML = (
    "app:\n"
    "  log_level: info\n"
    "datasources:\n"
    "  postgres:\n"
    '    url: "sqlite+aiosqlite://"\n'
    "  redis:\n"
    '    url: ""\n'
    "  prometheus:\n"
    '    url: "http://localhost:9090"\n'
    "  loki:\n"
    '    url: "http://localhost:3100"\n'
    "llm:\n"
    '  api_key: "test-key"\n'
    '  model: "gpt-4.1"\n'
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def configured_env(tmp_path, monkeypatch):
    cfg = tmp_path / "oncallpilot.yaml"
    cfg.write_text(MINIMAL_VALID_YAML)
    monkeypatch.setenv("ONCALLPILOT_CONFIG", str(cfg))


@pytest.fixture
def app(configured_env):
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


def _make_incident(**overrides) -> MagicMock:
    """Build a mock Incident ORM object."""
    inc = MagicMock()
    inc.id = overrides.get("id", uuid.uuid4())
    inc.fingerprint = overrides.get("fingerprint", "abc123")
    inc.status = overrides.get("status", "open")
    inc.severity = overrides.get("severity", "critical")
    inc.service = overrides.get("service", "my-svc")
    inc.description = overrides.get("description", "something broke")
    inc.started_at = overrides.get("started_at", datetime.now(timezone.utc))
    inc.resolved_at = overrides.get("resolved_at", None)
    inc.closed_at = None
    inc.closed_reason = None
    inc.reopen_count = 0
    inc.created_at = datetime.now(timezone.utc)
    inc.updated_at = datetime.now(timezone.utc)
    return inc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIRING_PAYLOAD = {
    "alerts": [
        {
            "status": "firing",
            "labels": {
                "service": "payment-svc",
                "severity": "critical",
                "alertname": "HighErrorRate",
            },
            "annotations": {
                "summary": "High error rate detected",
                "description": "Error rate > 5% for 5m",
            },
            "fingerprint": "fp-001",
            "startsAt": "2026-05-29T10:00:00Z",
        }
    ]
}


RESOLVED_PAYLOAD = {
    "alerts": [
        {
            "status": "resolved",
            "labels": {
                "service": "payment-svc",
                "severity": "critical",
                "alertname": "HighErrorRate",
            },
            "annotations": {
                "summary": "High error rate detected",
            },
            "fingerprint": "fp-001",
            "startsAt": "2026-05-29T10:00:00Z",
        }
    ]
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_firing_creates_new_incident_and_enqueues(client, app):
    """Firing alert → new incident, enqueue, created=True."""
    mock_incident = _make_incident(fingerprint="fp-001")
    session_id = str(uuid.uuid4())

    async def _override_db():
        yield AsyncMock()

    app.dependency_overrides[get_db_session] = _override_db

    with (
        patch(
            "oncallpilot_api.api.routes_alerts.create_incident_with_fingerprint_dedup",
            new_callable=AsyncMock,
            return_value=(mock_incident, True),
        ) as mock_dedup,
        patch(
            "oncallpilot_api.api.routes_alerts.InvestigationService",
        ) as mock_svc_cls,
    ):
        mock_svc = AsyncMock()
        mock_svc.enqueue = AsyncMock(return_value=session_id)
        mock_svc_cls.return_value = mock_svc

        resp = await client.post("/api/v1/alerts/alertmanager", json=FIRING_PAYLOAD)

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["incident_id"] == str(mock_incident.id)
    assert body["session_id"] == session_id
    assert body["created"] is True
    mock_dedup.assert_awaited_once()
    mock_svc.enqueue.assert_awaited_once()


@pytest.mark.asyncio
async def test_firing_same_fingerprint_dedup_no_enqueue(client, app):
    """Same fingerprint firing → created=False, no enqueue."""
    mock_incident = _make_incident(fingerprint="fp-001")

    async def _override_db():
        yield AsyncMock()

    app.dependency_overrides[get_db_session] = _override_db

    with (
        patch(
            "oncallpilot_api.api.routes_alerts.create_incident_with_fingerprint_dedup",
            new_callable=AsyncMock,
            return_value=(mock_incident, False),
        ),
        patch(
            "oncallpilot_api.api.routes_alerts.InvestigationService",
        ) as mock_svc_cls,
    ):
        mock_svc = AsyncMock()
        mock_svc_cls.return_value = mock_svc

        resp = await client.post("/api/v1/alerts/alertmanager", json=FIRING_PAYLOAD)

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] is False
    assert body["session_id"] is None
    mock_svc.enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolved_marks_incident_resolved(client, app):
    """Resolved alert → incident set to resolved, no enqueue."""
    mock_incident = _make_incident(fingerprint="fp-001", status="open")
    mock_resolved = _make_incident(fingerprint="fp-001", status="resolved")
    mock_resolved.resolved_at = datetime.now(timezone.utc)

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_incident
    mock_db.execute = AsyncMock(return_value=mock_result)

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db_session] = _override_db

    with (
        patch(
            "oncallpilot_api.api.routes_alerts.mark_incident_resolved",
            new_callable=AsyncMock,
            return_value=mock_resolved,
        ) as mock_resolve,
        patch(
            "oncallpilot_api.api.routes_alerts.InvestigationService",
        ) as mock_svc_cls,
    ):
        mock_svc = AsyncMock()
        mock_svc_cls.return_value = mock_svc

        resp = await client.post("/api/v1/alerts/alertmanager", json=RESOLVED_PAYLOAD)

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["incident_id"] == str(mock_incident.id)
    assert body["created"] is False
    assert body["session_id"] is None
    mock_resolve.assert_awaited_once()
    mock_svc.enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolved_then_firing_creates_new_incident(client, app):
    """After resolved, a new firing with same fingerprint → new incident."""
    new_incident = _make_incident(fingerprint="fp-001", status="open")
    session_id = str(uuid.uuid4())

    async def _override_db():
        yield AsyncMock()

    app.dependency_overrides[get_db_session] = _override_db

    with (
        patch(
            "oncallpilot_api.api.routes_alerts.create_incident_with_fingerprint_dedup",
            new_callable=AsyncMock,
            return_value=(new_incident, True),
        ) as mock_dedup,
        patch(
            "oncallpilot_api.api.routes_alerts.InvestigationService",
        ) as mock_svc_cls,
    ):
        mock_svc = AsyncMock()
        mock_svc.enqueue = AsyncMock(return_value=session_id)
        mock_svc_cls.return_value = mock_svc

        resp = await client.post("/api/v1/alerts/alertmanager", json=FIRING_PAYLOAD)

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] is True
    assert body["session_id"] == session_id


@pytest.mark.asyncio
async def test_missing_service_label_returns_400(client, app):
    """Alert without service label → 400."""
    payload = {
        "alerts": [
            {
                "status": "firing",
                "labels": {"severity": "critical"},
                "annotations": {},
                "fingerprint": "fp-no-svc",
                "startsAt": "2026-05-29T10:00:00Z",
            }
        ]
    }

    resp = await client.post("/api/v1/alerts/alertmanager", json=payload)
    assert resp.status_code == 400
    assert "service" in resp.json()["detail"].lower()
