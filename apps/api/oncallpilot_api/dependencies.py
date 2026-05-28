"""FastAPI dependency injection for config and services."""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends

from oncallpilot_api.config import Settings, load_settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


def get_config(settings: Settings = Depends(get_settings)) -> Settings:
    return settings


def get_event_bus():
    """Factory for EventBus — uses Redis when configured, otherwise NoOp."""
    settings = get_settings()
    redis_url = settings.datasources.redis.url
    if redis_url:
        from oncallpilot_api.services.event_bus import RedisPubSubEventBus
        return RedisPubSubEventBus(redis_url)
    from oncallpilot_api.services.event_bus import NoOpEventBus
    return NoOpEventBus()


def get_tracer():
    """Factory for Tracer — defaults to NoOp, Phase 7 swaps in Langfuse."""
    from oncallpilot_api.observability.tracer import NoOpTracer
    return NoOpTracer()
