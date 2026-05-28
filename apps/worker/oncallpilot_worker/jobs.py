"""arq job definitions for OnCallPilot worker."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from oncallpilot_api.config import load_settings
from oncallpilot_api.db.models import InvestigationSession
from oncallpilot_api.services.event_bus import NoOpEventBus, RedisPubSubEventBus

logger = structlog.get_logger()


def _make_session_factory() -> async_sessionmaker[AsyncSession]:
    settings = load_settings()
    engine = create_async_engine(settings.datasources.postgres.url, echo=False)
    return async_sessionmaker(engine, expire_on_commit=False)


def _make_event_bus():
    """Create EventBus based on config — Redis when available, NoOp otherwise."""
    settings = load_settings()
    redis_url = settings.datasources.redis.url
    if redis_url:
        return RedisPubSubEventBus(redis_url)
    return NoOpEventBus()


async def run_investigation(ctx: dict, session_id: str) -> None:
    """Execute an investigation session (stub — replaced by LangGraph in Phase 7).

    State machine: pending -> running -> completed | failed
    Publishes events to Redis stream ``oncallpilot:events:investigation:<session_id>``.
    """
    log = logger.bind(session_id=session_id)
    log.info("investigation.start")

    session_factory = _make_session_factory()
    event_bus = _make_event_bus()

    channel = f"oncallpilot:events:investigation:{session_id}"

    try:
        async with session_factory() as db:
            session = await db.get(InvestigationSession, uuid.UUID(session_id))
            if session is None:
                log.error("investigation.session_not_found")
                return

            # -- transition: pending -> running ---------------------------------
            session.status = "running"
            await db.commit()
            log.info("investigation.status", status="running")

            await event_bus.publish(channel, {
                "type": "session.started",
                "session_id": session_id,
                "started_at": datetime.now(timezone.utc).isoformat(),
            })

            # -- simulate work (Phase 7: LangGraph agent loop) -----------------
            await asyncio.sleep(5)

            # -- transition: running -> completed ------------------------------
            session.status = "completed"
            session.ended_at = datetime.now(timezone.utc)
            await db.commit()
            log.info("investigation.status", status="completed")

        await event_bus.publish(channel, {
            "type": "session.completed",
            "session_id": session_id,
            "verdict": "healthy",
            "confidence": 1.0,
        })
        log.info("investigation.done")

    except Exception as exc:
        log.error("investigation.failed", error=str(exc))
        try:
            async with session_factory() as db:
                session = await db.get(InvestigationSession, uuid.UUID(session_id))
                if session is not None:
                    session.status = "failed"
                    session.ended_at = datetime.now(timezone.utc)
                    await db.commit()

            await event_bus.publish(channel, {
                "type": "session.failed",
                "session_id": session_id,
                "error": str(exc),
            })
        except Exception:
            log.error("investigation.failed_cleanup_error", error=str(exc))
        raise
    finally:
        if hasattr(event_bus, "close"):
            await event_bus.close()
