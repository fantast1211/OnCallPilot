"""Datasource health-check service."""

from __future__ import annotations

import time

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from oncallpilot_api.db.models import DatasourceStatus
from oncallpilot_api.db.repositories import (
    get_all_datasource_statuses,
    upsert_datasource_status,
)


async def _check_http(url: str, *, timeout: float = 5.0) -> tuple[str, float | None, str | None]:
    """Ping an HTTP endpoint and return (status, latency_ms, detail)."""
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            resp = await client.get(url)
            latency = (time.monotonic() - start) * 1000
            if resp.status_code < 400:
                return "healthy", latency, None
            return "degraded", latency, f"HTTP {resp.status_code}"
    except Exception as exc:
        latency = (time.monotonic() - start) * 1000
        return "unreachable", latency, str(exc)


async def check_all_datasources(
    db: AsyncSession,
    *,
    prometheus_url: str | None = None,
    loki_url: str | None = None,
) -> list[DatasourceStatus]:
    """Check health of configured datasources and persist results.

    Returns the full list of datasource status rows after upserting.
    """
    checks: list[tuple[str, str, str]] = []  # (name, kind, url)

    if prometheus_url:
        checks.append(("prometheus", "prometheus", prometheus_url))
    if loki_url:
        checks.append(("loki", "loki", loki_url))

    for name, kind, url in checks:
        status, latency, detail = await _check_http(url)
        await upsert_datasource_status(
            db,
            name=name,
            kind=kind,
            status=status,
            latency_ms=latency,
            detail=detail,
        )

    return await get_all_datasource_statuses(db)
