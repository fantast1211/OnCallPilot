"""Integration tests for InvestigationService.enqueue and worker state machine.

Requires:
  - ONCALLPILOT_CONFIG pointing to a YAML config with real PostgreSQL and Redis
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

import pytest
import yaml
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from oncallpilot_api.db.models import InvestigationSession
from oncallpilot_api.db.repositories import create_incident_with_fingerprint_dedup
from oncallpilot_api.services.event_bus import RedisPubSubEventBus


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
def redis_url(config: dict) -> str:
    return config["datasources"]["redis"]["url"]


@pytest.fixture(scope="module")
def settings(config: dict):
    """Build a Settings object from the YAML config, bypassing env var validation."""
    from oncallpilot_api.config import Settings
    from unittest.mock import patch
    # Provide a dummy OPENAI_API_KEY so Settings validation passes
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key-for-integration"}):
        return Settings()


@pytest.fixture
async def session_factory(pg_url: str):
    engine = create_async_engine(pg_url, echo=False, pool_pre_ping=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def event_bus(redis_url: str):
    bus = RedisPubSubEventBus(redis_url)
    try:
        await asyncio.wait_for(bus._redis.ping(), timeout=5.0)
    except (Exception, asyncio.TimeoutError):
        await bus.close()
        pytest.skip(f"Cannot reach Redis at {redis_url}")
    yield bus
    # Clean up streams created during test
    keys = []
    async for key in bus._redis.scan_iter("oncallpilot:events:*"):
        keys.append(key)
    if keys:
        await bus._redis.delete(*keys)
    await bus.close()


@pytest.fixture
async def incident(session_factory: async_sessionmaker):
    async with session_factory() as db:
        inc, _ = await create_incident_with_fingerprint_dedup(
            db,
            fp=f"fp-test-{uuid.uuid4().hex[:8]}",
            severity="critical",
            service="test-svc",
            description="integration test incident",
        )
        await db.commit()
        yield inc


async def _collect_events(
    bus: RedisPubSubEventBus,
    channel: str,
    count: int = 2,
    timeout: float = 30.0,
) -> list[dict]:
    events: list[dict] = []

    async def _drain() -> None:
        async for ev in bus.subscribe(channel, last_event_id=None):
            events.append(ev)
            if len(events) >= count:
                break

    try:
        await asyncio.wait_for(_drain(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    return events


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_creates_pending_session(
    session_factory: async_sessionmaker,
    incident,
    settings,
):
    """enqueue() should create an investigation_sessions row with status=pending."""
    from oncallpilot_api.services.investigation_service import InvestigationService
    from oncallpilot_api.services.event_bus import NoOpEventBus

    async with session_factory() as db:
        svc = InvestigationService(db=db, event_bus=NoOpEventBus(), settings=settings)
        session_id = await svc.enqueue(
            incident_id=str(incident.id),
            source="manual",
            query="check error rate",
        )

    assert session_id  # non-empty string

    # Verify row exists with status=pending
    async with session_factory() as db:
        row = await db.get(InvestigationSession, uuid.UUID(session_id))
        assert row is not None
        assert row.status == "pending"
        assert row.incident_id == incident.id


@pytest.mark.asyncio
async def test_session_state_machine_pending_running_completed(
    session_factory: async_sessionmaker,
    incident,
    event_bus: RedisPubSubEventBus,
    settings,
):
    """Full state machine: pending -> running -> completed, verified via DB polling."""
    from oncallpilot_api.services.investigation_service import InvestigationService

    async with session_factory() as db:
        svc = InvestigationService(db=db, event_bus=event_bus, settings=settings)
        session_id = await svc.enqueue(
            incident_id=str(incident.id),
            source="manual",
        )

    # Wait for the worker to process the job (max ~15s)
    terminal_statuses = {"completed", "failed"}
    final_row = None
    for _ in range(30):
        await asyncio.sleep(0.5)
        async with session_factory() as db:
            final_row = await db.get(InvestigationSession, uuid.UUID(session_id))
            if final_row and final_row.status in terminal_statuses:
                break

    assert final_row is not None
    assert final_row.status == "completed"
    assert final_row.ended_at is not None


@pytest.mark.asyncio
async def test_event_stream_contains_started_and_completed(
    session_factory: async_sessionmaker,
    incident,
    event_bus: RedisPubSubEventBus,
    settings,
):
    """The event stream for the session should contain session.started and session.completed."""
    from oncallpilot_api.services.investigation_service import InvestigationService

    async with session_factory() as db:
        svc = InvestigationService(db=db, event_bus=event_bus, settings=settings)
        session_id = await svc.enqueue(
            incident_id=str(incident.id),
            source="manual",
        )

    channel = f"oncallpilot:events:investigation:{session_id}"

    # Collect at least 2 events (started + completed)
    events = await _collect_events(event_bus, channel, count=2, timeout=20.0)

    event_types = [e.get("type") for e in events]
    assert "session.started" in event_types, f"Missing session.started, got: {event_types}"
    assert "session.completed" in event_types, f"Missing session.completed, got: {event_types}"

    # Verify completed event has expected fields
    completed_ev = next(e for e in events if e.get("type") == "session.completed")
    assert completed_ev["session_id"] == session_id
    assert "verdict" in completed_ev
    assert "confidence" in completed_ev
