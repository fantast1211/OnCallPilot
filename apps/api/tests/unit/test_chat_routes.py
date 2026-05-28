"""Unit tests for the Chat API routes."""

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


def _mock_db():
    db = AsyncMock()
    return db


def _make_chat_session(**overrides):
    session = MagicMock()
    session.id = overrides.get("id", uuid.uuid4())
    session.investigation_session_id = overrides.get(
        "investigation_session_id", uuid.uuid4()
    )
    session.status = overrides.get("status", "active")
    now = datetime.now(timezone.utc)
    session.created_at = overrides.get("created_at", now)
    session.updated_at = overrides.get("updated_at", now)
    return session


def _make_chat_message(**overrides):
    msg = MagicMock()
    msg.id = overrides.get("id", uuid.uuid4())
    msg.chat_session_id = overrides.get("chat_session_id", uuid.uuid4())
    msg.role = overrides.get("role", "user")
    msg.content = overrides.get("content", "hello")
    msg.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    return msg


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_sessions_creates_session(client, app):
    """POST /api/v1/chat/sessions creates a chat session and returns session_id."""
    investigation_id = str(uuid.uuid4())
    mock_session = _make_chat_session(
        investigation_session_id=uuid.UUID(investigation_id)
    )

    mock_db = _mock_db()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db_session] = _override_db

    with patch(
        "oncallpilot_api.api.routes_chat.ChatService"
    ) as mock_svc_cls:
        mock_svc = AsyncMock()
        mock_svc.create_session = AsyncMock(return_value=str(mock_session.id))
        mock_svc_cls.return_value = mock_svc

        resp = await client.post(
            "/api/v1/chat/sessions",
            json={"investigation_session_id": investigation_id},
        )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == str(mock_session.id)
    mock_svc.create_session.assert_awaited_once_with(investigation_id)


@pytest.mark.asyncio
async def test_post_messages_appends_and_returns_echo(client, app):
    """POST /api/v1/chat/sessions/{id}/messages appends user msg and returns assistant echo."""
    session_id = str(uuid.uuid4())
    mock_session = _make_chat_session(id=uuid.UUID(session_id))
    assistant_msg = _make_chat_message(
        role="assistant", content="chat graph 在 Phase 7 接入"
    )

    mock_db = _mock_db()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db_session] = _override_db

    with patch(
        "oncallpilot_api.api.routes_chat.ChatService"
    ) as mock_svc_cls:
        mock_svc = AsyncMock()
        mock_svc.get_session = AsyncMock(return_value=mock_session)
        mock_svc.append_message = AsyncMock(return_value=assistant_msg)
        mock_svc.respond = AsyncMock(return_value="chat graph 在 Phase 7 接入")
        mock_svc_cls.return_value = mock_svc

        resp = await client.post(
            f"/api/v1/chat/sessions/{session_id}/messages",
            json={"role": "user", "content": "what happened?"},
        )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "assistant"
    assert body["content"] == "chat graph 在 Phase 7 接入"


@pytest.mark.asyncio
async def test_get_messages_returns_history(client, app):
    """GET /api/v1/chat/sessions/{id}/messages returns message history."""
    session_id = str(uuid.uuid4())
    mock_session = _make_chat_session(id=uuid.UUID(session_id))
    messages = [
        _make_chat_message(role="user", content="hello"),
        _make_chat_message(role="assistant", content="chat graph 在 Phase 7 接入"),
    ]

    mock_db = _mock_db()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db_session] = _override_db

    with patch(
        "oncallpilot_api.api.routes_chat.ChatService"
    ) as mock_svc_cls:
        mock_svc = AsyncMock()
        mock_svc.get_session = AsyncMock(return_value=mock_session)
        mock_svc.get_messages = AsyncMock(return_value=messages)
        mock_svc_cls.return_value = mock_svc

        resp = await client.get(f"/api/v1/chat/sessions/{session_id}/messages")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["role"] == "user"
    assert body[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_get_sessions_returns_list(client, app):
    """GET /api/v1/chat/sessions returns recent sessions."""
    sessions = [_make_chat_session() for _ in range(3)]

    mock_db = _mock_db()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db_session] = _override_db

    with patch(
        "oncallpilot_api.api.routes_chat.ChatService"
    ) as mock_svc_cls:
        mock_svc = AsyncMock()
        mock_svc.list_sessions = AsyncMock(return_value=sessions)
        mock_svc_cls.return_value = mock_svc

        resp = await client.get("/api/v1/chat/sessions")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 3


@pytest.mark.asyncio
async def test_get_session_by_id(client, app):
    """GET /api/v1/chat/sessions/{id} returns session metadata."""
    session_id = str(uuid.uuid4())
    mock_session = _make_chat_session(id=uuid.UUID(session_id))

    mock_db = _mock_db()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db_session] = _override_db

    with patch(
        "oncallpilot_api.api.routes_chat.ChatService"
    ) as mock_svc_cls:
        mock_svc = AsyncMock()
        mock_svc.get_session = AsyncMock(return_value=mock_session)
        mock_svc_cls.return_value = mock_svc

        resp = await client.get(f"/api/v1/chat/sessions/{session_id}")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == session_id
    assert body["status"] == "active"


@pytest.mark.asyncio
async def test_get_session_not_found(client, app):
    """GET /api/v1/chat/sessions/{id} returns 404 when session doesn't exist."""
    session_id = str(uuid.uuid4())

    mock_db = _mock_db()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db_session] = _override_db

    with patch(
        "oncallpilot_api.api.routes_chat.ChatService"
    ) as mock_svc_cls:
        mock_svc = AsyncMock()
        mock_svc.get_session = AsyncMock(return_value=None)
        mock_svc_cls.return_value = mock_svc

        resp = await client.get(f"/api/v1/chat/sessions/{session_id}")

    app.dependency_overrides.clear()
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_messages_session_not_found(client, app):
    """POST /api/v1/chat/sessions/{id}/messages returns 404 when session doesn't exist."""
    session_id = str(uuid.uuid4())

    mock_db = _mock_db()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db_session] = _override_db

    with patch(
        "oncallpilot_api.api.routes_chat.ChatService"
    ) as mock_svc_cls:
        mock_svc = AsyncMock()
        mock_svc.get_session = AsyncMock(return_value=None)
        mock_svc_cls.return_value = mock_svc

        resp = await client.post(
            f"/api/v1/chat/sessions/{session_id}/messages",
            json={"role": "user", "content": "hello"},
        )

    app.dependency_overrides.clear()
    assert resp.status_code == 404
