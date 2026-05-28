"""Integration tests for RedisPubSubEventBus against a real Redis instance."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path

import pytest
import yaml

from oncallpilot_api.services.event_bus import RedisPubSubEventBus


@pytest.fixture(scope="module")
def redis_url() -> str:
    """Return the Redis URL from config, skipping if unavailable."""
    config_path = os.environ.get("ONCALLPILOT_CONFIG")
    if not config_path:
        pytest.skip("ONCALLPILOT_CONFIG not set — skipping Redis integration tests")
    with Path(config_path).open() as fh:
        data = yaml.safe_load(fh)
    url = data.get("datasources", {}).get("redis", {}).get("url")
    if not url:
        pytest.skip("Redis URL not configured — skipping Redis integration tests")
    return url


@pytest.fixture
async def bus(redis_url: str):
    """Create a RedisPubSubEventBus, tear down and clean up streams after test."""
    b = RedisPubSubEventBus(redis_url)
    # Verify Redis is reachable; skip the entire test module if not
    try:
        await asyncio.wait_for(b._redis.ping(), timeout=5.0)
    except (Exception, asyncio.TimeoutError):
        await b.close()
        pytest.skip(f"Cannot reach Redis at {redis_url} — skipping integration tests")

    channels: list[str] = []
    b._test_channels = channels  # type: ignore[attr-defined]
    yield b

    # Cleanup: delete all streams created during this test
    for ch in channels:
        try:
            await b._redis.delete(ch)
        except Exception:
            pass
    await b.close()


@pytest.fixture
def stream_channel(bus: RedisPubSubEventBus):
    """Generate a unique stream channel per test to avoid cross-test pollution."""
    ch = f"oncallpilot:events:investigation:{uuid.uuid4().hex}"
    bus._test_channels.append(ch)  # type: ignore[attr-defined]
    return ch


async def _collect_events(
    channel: str,
    bus: RedisPubSubEventBus,
    last_event_id: str | None = None,
    count: int = 1,
    timeout: float = 10.0,
) -> list[dict]:
    """Collect *count* events from the bus, with a safety timeout."""
    events: list[dict] = []

    async def _drain() -> None:
        async for ev in bus.subscribe(channel, last_event_id=last_event_id):
            events.append(ev)
            if len(events) >= count:
                break

    try:
        await asyncio.wait_for(_drain(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    return events


@pytest.mark.asyncio
async def test_publish_and_subscribe(bus: RedisPubSubEventBus, stream_channel: str):
    """publish several events, subscribe from the beginning, assert order and payload."""
    channel = stream_channel
    payloads = [
        {"session_id": "s1", "started_at": "2026-01-01T00:00:00Z"},
        {"step_index": 0, "planned_tool": "search_logs", "planned_args": {"query": "*"}, "reasoning": "start"},
        {"step_index": 0, "tool_name": "search_logs", "status": "ok", "summary": "found 5", "latency_ms": 120},
    ]

    for p in payloads:
        await bus.publish(channel, p)

    # Subscribe from the very beginning (no last_event_id) — should get all three
    received = await _collect_events(channel, bus, last_event_id=None, count=3)

    assert len(received) == 3
    for original, got in zip(payloads, received):
        assert got == original


@pytest.mark.asyncio
async def test_history_replay_with_last_event_id(bus: RedisPubSubEventBus, stream_channel: str):
    """publish a few events, capture the id of the second, then subscribe from that id."""
    channel = stream_channel
    p1 = {"session_id": "s1", "started_at": "2026-01-01T00:00:00Z"}
    p2 = {"step_index": 0, "planned_tool": "search_logs", "planned_args": {"query": "*"}, "reasoning": "r"}
    p3 = {"step_index": 0, "tool_name": "search_logs", "status": "ok", "summary": "done", "latency_ms": 50}

    id1 = await bus.publish(channel, p1)
    id2 = await bus.publish(channel, p2)
    id3 = await bus.publish(channel, p3)

    # Subscribe starting after id2 — should get only p3 from history
    received = await _collect_events(channel, bus, last_event_id=id2, count=1)

    assert len(received) == 1
    assert received[0] == p3


@pytest.mark.asyncio
async def test_subscribe_receives_new_events_after_history(bus: RedisPubSubEventBus, stream_channel: str):
    """subscribe with last_event_id=None should first yield history, then block for new ones."""
    channel = stream_channel
    p1 = {"type": "session.started", "session_id": "s2", "started_at": "2026-05-01T00:00:00Z"}
    await bus.publish(channel, p1)

    # Start subscribe — collect 1 from history
    received = await _collect_events(channel, bus, last_event_id=None, count=1)
    assert len(received) == 1
    assert received[0] == p1
