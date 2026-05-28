"""EventBus protocol, NoOp implementation, and Redis-backed implementation."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

import redis.asyncio as aioredis


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

    async def close(self) -> None:
        pass


class RedisPubSubEventBus:
    """Redis Streams-backed EventBus for real-time investigation event delivery.

    Stream key convention: ``oncallpilot:events:investigation:<session_id>``
    Each entry stores the event dict as JSON in a single field ``data``.
    """

    def __init__(self, redis_url: str) -> None:
        self._redis: aioredis.Redis = aioredis.from_url(redis_url, decode_responses=True)

    # -- publish -------------------------------------------------------------

    async def publish(self, channel: str, event: dict, event_id: str | None = None) -> str:
        """Append *event* to the Redis Stream at *channel*.

        Returns the stream entry ID assigned by Redis (e.g. ``"1685000000000-0"``).
        """
        entry_id = event_id if event_id is not None else "*"
        raw_id: str = await self._redis.xadd(
            channel,
            {"data": json.dumps(event)},
            id=entry_id,
        )
        return raw_id

    # -- subscribe -----------------------------------------------------------

    async def subscribe(
        self,
        channel: str,
        last_event_id: str | None = None,
        block_ms: int = 5000,
        count: int = 10,
    ) -> AsyncIterator[dict]:
        """Yield events from *channel*, optionally starting after *last_event_id*.

        1. Replay history — all entries when *last_event_id* is None, or only
           those after *last_event_id* when it is provided.
        2. Then ``XREAD BLOCK`` for live events starting after the last replayed id.
        """
        # Phase 1 — history replay
        if last_event_id is not None:
            # Only events strictly after the given id
            entries = await self._redis.xrange(channel, min=f"({last_event_id}", max="+")
        else:
            # All existing events in the stream
            entries = await self._redis.xrange(channel, min="-", max="+")

        last_id = "$"
        for entry_id, fields in entries:
            last_id = entry_id
            yield json.loads(fields["data"])

        # Phase 2 — live tail (start from after the last replayed entry)
        while True:
            streams = await self._redis.xread(
                {channel: last_id},
                block=block_ms,
                count=count,
            )
            if not streams:
                continue
            for _stream_name, messages in streams:
                for entry_id, fields in messages:
                    last_id = entry_id
                    yield json.loads(fields["data"])

    # -- lifecycle -----------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying Redis connection."""
        await self._redis.aclose()
