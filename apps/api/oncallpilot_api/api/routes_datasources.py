"""Datasource status and health-check endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from oncallpilot_api.db.session import get_db_session
from oncallpilot_api.db.repositories import get_all_datasource_statuses
from oncallpilot_api.dependencies import get_config
from oncallpilot_api.config import Settings
from oncallpilot_api.services.datasource_service import check_all_datasources

router = APIRouter(prefix="/api/v1/datasources", tags=["datasources"])


def _serialize(ds) -> dict:
    return {
        "name": ds.name,
        "kind": ds.kind,
        "status": ds.status,
        "latency_ms": ds.latency_ms,
        "detail": ds.detail,
        "last_checked_at": ds.last_checked_at.isoformat() if ds.last_checked_at else None,
    }


@router.get("/status")
async def datasource_status(
    db: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    """Return persisted status for all tracked datasources."""
    rows = await get_all_datasource_statuses(db)
    return [_serialize(r) for r in rows]


@router.post("/check")
async def datasource_check(
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_config),
) -> list[dict]:
    """Trigger health checks for all configured datasources and return results."""
    prom_url = settings.datasources.prometheus.url
    loki_url = settings.datasources.loki.url

    rows = await check_all_datasources(
        db,
        prometheus_url=prom_url,
        loki_url=loki_url,
    )
    return [_serialize(r) for r in rows]
