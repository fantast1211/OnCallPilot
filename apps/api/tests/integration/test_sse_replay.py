"""Integration test: SSE event stream replay for investigation sessions.

Requires real PostgreSQL and Redis via ONCALLPILOT_CONFIG.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest
import yaml
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from oncallpilot_api.db.models import InvestigationSession
from oncallpilot_api.db.repositories import (
    append_tool_call,
    create_incident_with_fingerprint_dedup,
    create_investigation_session,
)


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


@pytest.fixture
async def session_factory(pg_url: str):
    engine = create_async_engine(pg_url, echo=False, pool_pre_ping=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def app(config):
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


def _parse_sse_events(raw: str) -> list[dict]:
    """Parse SSE text into a list of dicts with keys: id, event, data."""
    events = []
    current: dict = {}
    for line in raw.split("\n"):
        if line.startswith("id:"):
            current["id"] = line[len("id:"):].strip()
        elif line.startswith("event:"):
            current["event"] = line[len("event:"):].strip()
        elif line.startswith("data:"):
            current["data"] = json.loads(line[len("data:"):].strip())
        elif line == "" and current:
            events.append(current)
            current = {}
    if current:
        events.append(current)
    return events


async def _create_completed_session_with_tool_calls(
    factory: async_sessionmaker,
) -> uuid.UUID:
    """Create a completed investigation session with two tool calls."""
    async with factory() as db:
        incident, _ = await create_incident_with_fingerprint_dedup(
            db,
            fp=f"sse-test-{uuid.uuid4().hex[:8]}",
            severity="info",
            service="sse-test-svc",
            description="SSE replay test",
        )
        session = await create_investigation_session(
            db,
            incident_id=incident.id,
            metadata_={"source": "test"},
        )
        # Mark as completed
        session.status = "completed"
        db.add(session)

        # Add two tool calls
        await append_tool_call(
            db,
            investigation_session_id=session.id,
            tool_name="query_metrics",
            input_data={"query": "cpu_usage"},
            output_data={"result": 42},
            status="success",
            step_index=0,
        )
        await append_tool_call(
            db,
            investigation_session_id=session.id,
            tool_name="query_logs",
            input_data={"query": "error logs"},
            output_data={"result": "no errors"},
            status="success",
            step_index=1,
        )

        await db.commit()
        return session.id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_completed_session_replays_all_events(
    client: AsyncClient,
    session_factory: async_sessionmaker,
):
    """A completed session should emit all tool.started + tool.completed events then close."""
    session_id = await _create_completed_session_with_tool_calls(session_factory)

    chunks = []
    async with client.stream(
        "GET",
        f"/api/v1/investigations/{session_id}/events",
        headers={"Accept": "text/event-stream"},
    ) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        async for chunk in resp.aiter_text():
            chunks.append(chunk)

    raw = "".join(chunks)
    events = _parse_sse_events(raw)

    # 2 tool calls × 2 events each = 4 events
    assert len(events) == 4

    # First tool call
    assert events[0]["event"] == "tool.started"
    assert events[0]["data"]["tool_name"] == "query_metrics"
    assert events[0]["data"]["step_index"] == 0
    assert events[0]["id"] == "1"

    assert events[1]["event"] == "tool.completed"
    assert events[1]["data"]["tool_name"] == "query_metrics"
    assert events[1]["data"]["status"] == "success"
    assert events[1]["id"] == "2"

    # Second tool call
    assert events[2]["event"] == "tool.started"
    assert events[2]["data"]["tool_name"] == "query_logs"
    assert events[2]["data"]["step_index"] == 1
    assert events[2]["id"] == "3"

    assert events[3]["event"] == "tool.completed"
    assert events[3]["data"]["tool_name"] == "query_logs"
    assert events[3]["data"]["status"] == "success"
    assert events[3]["id"] == "4"


@pytest.mark.asyncio
async def test_last_event_id_skips_already_seen(
    client: AsyncClient,
    session_factory: async_sessionmaker,
):
    """Reconnecting with Last-Event-ID should skip events up to that id."""
    session_id = await _create_completed_session_with_tool_calls(session_factory)

    chunks = []
    async with client.stream(
        "GET",
        f"/api/v1/investigations/{session_id}/events",
        headers={
            "Accept": "text/event-stream",
            "Last-Event-ID": "2",
        },
    ) as resp:
        assert resp.status_code == 200
        async for chunk in resp.aiter_text():
            chunks.append(chunk)

    raw = "".join(chunks)
    events = _parse_sse_events(raw)

    # Should only see events 3 and 4
    assert len(events) == 2
    assert events[0]["id"] == "3"
    assert events[0]["event"] == "tool.started"
    assert events[0]["data"]["tool_name"] == "query_logs"

    assert events[1]["id"] == "4"
    assert events[1]["event"] == "tool.completed"
    assert events[1]["data"]["tool_name"] == "query_logs"


@pytest.mark.asyncio
async def test_last_event_id_beyond_history_returns_empty(
    client: AsyncClient,
    session_factory: async_sessionmaker,
):
    """Last-Event-ID beyond the last event should return no events for a completed session."""
    session_id = await _create_completed_session_with_tool_calls(session_factory)

    chunks = []
    async with client.stream(
        "GET",
        f"/api/v1/investigations/{session_id}/events",
        headers={
            "Accept": "text/event-stream",
            "Last-Event-ID": "999",
        },
    ) as resp:
        assert resp.status_code == 200
        async for chunk in resp.aiter_text():
            chunks.append(chunk)

    raw = "".join(chunks)
    events = _parse_sse_events(raw)
    assert len(events) == 0


@pytest.mark.asyncio
async def test_nonexistent_session_returns_404(
    client: AsyncClient,
):
    """Requesting events for a nonexistent session should return 404."""
    fake_id = uuid.uuid4()
    resp = await client.get(
        f"/api/v1/investigations/{fake_id}/events",
        headers={"Accept": "text/event-stream"},
    )
    assert resp.status_code == 404
