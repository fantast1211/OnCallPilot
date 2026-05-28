"""Unit tests for the Incident and Investigation REST API routes."""

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
    inc.closed_at = overrides.get("closed_at", None)
    inc.closed_reason = overrides.get("closed_reason", None)
    inc.reopen_count = overrides.get("reopen_count", 0)
    inc.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    inc.updated_at = overrides.get("updated_at", datetime.now(timezone.utc))
    inc.investigation_sessions = overrides.get("investigation_sessions", [])
    return inc


def _make_session(**overrides) -> MagicMock:
    """Build a mock InvestigationSession ORM object."""
    s = MagicMock()
    s.id = overrides.get("id", uuid.uuid4())
    s.incident_id = overrides.get("incident_id", uuid.uuid4())
    s.status = overrides.get("status", "pending")
    s.started_at = overrides.get("started_at", datetime.now(timezone.utc))
    s.ended_at = overrides.get("ended_at", None)
    s.tool_calls = overrides.get("tool_calls", [])
    return s


# ---------------------------------------------------------------------------
# Tests: GET /api/v1/incidents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_incidents_returns_list(client, app):
    """GET /api/v1/incidents returns a list of incidents."""
    inc1 = _make_incident(fingerprint="fp-1", service="svc-a")
    inc2 = _make_incident(fingerprint="fp-2", service="svc-b")

    async def _override_db():
        yield AsyncMock()

    app.dependency_overrides[get_db_session] = _override_db

    with (
        patch(
            "oncallpilot_api.api.routes_incidents.list_recent_incidents",
            new_callable=AsyncMock,
            return_value=[inc1, inc2],
        ),
        patch(
            "oncallpilot_api.api.routes_incidents.count_incidents",
            new_callable=AsyncMock,
            return_value=2,
        ),
    ):
        resp = await client.get("/api/v1/incidents")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert body["items"][0]["fingerprint"] == "fp-1"


# ---------------------------------------------------------------------------
# Tests: GET /api/v1/incidents/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_incident_detail(client, app):
    """GET /api/v1/incidents/{id} returns incident with sessions."""
    session = _make_session(status="completed")
    inc = _make_incident(investigation_sessions=[session])

    async def _override_db():
        yield AsyncMock()

    app.dependency_overrides[get_db_session] = _override_db

    with patch(
        "oncallpilot_api.api.routes_incidents.get_incident_detail",
        new_callable=AsyncMock,
        return_value=inc,
    ):
        resp = await client.get(f"/api/v1/incidents/{inc.id}")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(inc.id)
    assert len(body["investigation_sessions"]) == 1
    assert body["investigation_sessions"][0]["status"] == "completed"


@pytest.mark.asyncio
async def test_get_incident_not_found(client, app):
    """GET /api/v1/incidents/{id} returns 404 when not found."""
    async def _override_db():
        yield AsyncMock()

    app.dependency_overrides[get_db_session] = _override_db

    with patch(
        "oncallpilot_api.api.routes_incidents.get_incident_detail",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await client.get(f"/api/v1/incidents/{uuid.uuid4()}")

    app.dependency_overrides.clear()
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: POST /api/v1/incidents/{id}/close
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_incident(client, app):
    """POST close sets closed_at, closed_reason, status=resolved."""
    now = datetime.now(timezone.utc)
    closed_inc = _make_incident(
        status="resolved",
        closed_at=now,
        closed_reason="fixed",
    )

    async def _override_db():
        yield AsyncMock()

    app.dependency_overrides[get_db_session] = _override_db

    with patch(
        "oncallpilot_api.api.routes_incidents.close_incident",
        new_callable=AsyncMock,
        return_value=closed_inc,
    ):
        resp = await client.post(
            f"/api/v1/incidents/{closed_inc.id}/close",
            json={"reason": "fixed"},
        )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "resolved"
    assert body["closed_reason"] == "fixed"
    assert body["closed_at"] is not None


@pytest.mark.asyncio
async def test_close_incident_not_found(client, app):
    """POST close returns 404 when incident not found."""
    async def _override_db():
        yield AsyncMock()

    app.dependency_overrides[get_db_session] = _override_db

    with patch(
        "oncallpilot_api.api.routes_incidents.close_incident",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await client.post(
            f"/api/v1/incidents/{uuid.uuid4()}/close",
            json={"reason": "fixed"},
        )

    app.dependency_overrides.clear()
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: POST /api/v1/incidents/{id}/reopen
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reopen_incident(client, app):
    """POST reopen increments reopen_count, status=open, clears closed fields."""
    reopened = _make_incident(
        status="open",
        reopen_count=1,
        closed_at=None,
        closed_reason=None,
    )

    async def _override_db():
        yield AsyncMock()

    app.dependency_overrides[get_db_session] = _override_db

    with patch(
        "oncallpilot_api.api.routes_incidents.reopen_incident",
        new_callable=AsyncMock,
        return_value=reopened,
    ):
        resp = await client.post(
            f"/api/v1/incidents/{reopened.id}/reopen",
            json={"reason": "regression"},
        )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "open"
    assert body["reopen_count"] == 1
    assert body["closed_at"] is None
    assert body["closed_reason"] is None


@pytest.mark.asyncio
async def test_reopen_incident_not_found(client, app):
    """POST reopen returns 404 when incident not found."""
    async def _override_db():
        yield AsyncMock()

    app.dependency_overrides[get_db_session] = _override_db

    with patch(
        "oncallpilot_api.api.routes_incidents.reopen_incident",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await client.post(
            f"/api/v1/incidents/{uuid.uuid4()}/reopen",
            json={"reason": "regression"},
        )

    app.dependency_overrides.clear()
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: POST /api/v1/incidents/{id}/investigations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_investigation_on_incident(client, app):
    """POST investigations creates session without changing incident status."""
    inc = _make_incident(status="open")
    session_id = str(uuid.uuid4())

    async def _override_db():
        yield AsyncMock()

    app.dependency_overrides[get_db_session] = _override_db

    with (
        patch(
            "oncallpilot_api.api.routes_incidents.get_incident_detail",
            new_callable=AsyncMock,
            return_value=inc,
        ),
        patch(
            "oncallpilot_api.api.routes_incidents.InvestigationService",
        ) as mock_svc_cls,
    ):
        mock_svc = AsyncMock()
        mock_svc.enqueue = AsyncMock(return_value=session_id)
        mock_svc_cls.return_value = mock_svc

        resp = await client.post(
            f"/api/v1/incidents/{inc.id}/investigations",
            json={"extra_context": {"source": "ui"}},
        )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == session_id
    # Incident status must NOT have changed
    assert inc.status == "open"
    mock_svc.enqueue.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_investigation_incident_not_found(client, app):
    """POST investigations returns 404 when incident not found."""
    async def _override_db():
        yield AsyncMock()

    app.dependency_overrides[get_db_session] = _override_db

    with patch(
        "oncallpilot_api.api.routes_incidents.get_incident_detail",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await client.post(
            f"/api/v1/incidents/{uuid.uuid4()}/investigations",
            json={},
        )

    app.dependency_overrides.clear()
    assert resp.status_code == 404
