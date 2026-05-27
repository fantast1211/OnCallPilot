"""Tests for EventBus protocol and NoOpEventBus."""

import pytest

from oncallpilot_api.services.event_bus import EventBus, NoOpEventBus


def test_noop_event_bus_implements_protocol():
    bus: EventBus = NoOpEventBus()
    assert isinstance(bus, EventBus)


@pytest.mark.asyncio
async def test_noop_publish():
    bus = NoOpEventBus()
    await bus.publish("investigations", {"id": "inv-1", "status": "started"})  # no error


@pytest.mark.asyncio
async def test_noop_subscribe_yields_nothing():
    bus = NoOpEventBus()
    events = []
    async for event in bus.subscribe("investigations", None):
        events.append(event)
    assert events == []
