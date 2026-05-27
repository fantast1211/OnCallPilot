"""EventBus protocol and NoOp implementation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable


@runtime_checkable
class EventBus(Protocol):
    async def publish(self, channel: str, event: dict) -> None: ...
    def subscribe(self, channel: str, last_event_id: str | None) -> AsyncIterator[dict]: ...


class NoOpEventBus:
    """An event bus that does nothing — suitable for testing and local dev."""

    async def publish(self, channel: str, event: dict) -> None:
        pass

    async def subscribe(self, channel: str, last_event_id: str | None) -> AsyncIterator[dict]:
        # Yield nothing — no events in NoOp mode
        return
        yield  # pragma: no cover — makes this an async generator
