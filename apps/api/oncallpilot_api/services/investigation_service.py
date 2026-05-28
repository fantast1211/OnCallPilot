"""InvestigationService — enqueue investigation jobs via arq."""

from __future__ import annotations

import uuid

import arq
import structlog
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import AsyncSession

from oncallpilot_api.config import Settings
from oncallpilot_api.db.repositories import create_investigation_session
from oncallpilot_api.services.event_bus import EventBus

logger = structlog.get_logger()


class InvestigationService:
    """Orchestrates investigation sessions: persist + enqueue to arq."""

    def __init__(self, db: AsyncSession, event_bus: EventBus, settings: Settings) -> None:
        self._db = db
        self._event_bus = event_bus
        self._settings = settings

    async def enqueue(
        self,
        incident_id: str,
        source: str = "manual",
        query: str | None = None,
    ) -> str:
        """Create a pending investigation session and enqueue it to arq.

        Returns the session_id as a string.
        """
        redis_url = self._settings.datasources.redis.url
        queue_name = self._settings.worker.arq.queue

        # Persist session row (status=pending)
        metadata_ = {"source": source}
        if query is not None:
            metadata_["query"] = query

        session = await create_investigation_session(
            self._db,
            incident_id=uuid.UUID(incident_id),
            metadata_=metadata_,
        )
        await self._db.commit()

        session_id = str(session.id)
        log = logger.bind(session_id=session_id, incident_id=incident_id)
        log.info("investigation.enqueued", source=source)

        # Enqueue to arq (idempotent via _job_id)
        redis_settings = RedisSettings.from_dsn(redis_url)
        pool = await arq.create_pool(redis_settings)
        try:
            await pool.enqueue_job(
                "run_investigation",
                session_id,
                _job_id=f"investigation:{session_id}",
                _queue_name=queue_name,
            )
        finally:
            await pool.close()

        return session_id
