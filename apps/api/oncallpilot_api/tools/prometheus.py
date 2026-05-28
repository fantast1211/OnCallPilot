from __future__ import annotations

from typing import Any

import httpx

from oncallpilot_api.tools.base import ToolResult

TOOL_FAMILY = "prometheus"

_DEFAULT_TIMEOUT = 30.0


class PromClient:
    """Thin async wrapper around the Prometheus HTTP API."""

    def __init__(self, base_url: str = "http://localhost:9090") -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=_DEFAULT_TIMEOUT,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        resp = await self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()


def _check_prom_response(body: dict[str, Any], tool_name: str) -> ToolResult | None:
    if body.get("status") == "error":
        error = body.get("error", "unknown Prometheus error")
        return ToolResult(
            status="error",
            data=body,
            summary=f"Prometheus error: {error}",
            tool_name=tool_name,
            error_message=error,
        )
    return None


async def instant_query(
    client: PromClient,
    query: str,
    time: str | None = None,
) -> ToolResult:
    """Execute an instant Prometheus query (GET /api/v1/query)."""
    params: dict[str, str] = {"query": query}
    if time is not None:
        params["time"] = time

    try:
        body = await client._get("/api/v1/query", params)
    except httpx.HTTPError as exc:
        return ToolResult(
            status="error",
            data=None,
            summary=f"Prometheus request failed: {exc}",
            tool_name="prometheus.instant_query",
            error_message=str(exc),
        )

    if err := _check_prom_response(body, "prometheus.instant_query"):
        return err

    data = body.get("data")
    result_count = len(data.get("result", [])) if isinstance(data, dict) else 0
    return ToolResult(
        status="success",
        data=data,
        summary=f"Instant query returned {result_count} series",
        tool_name="prometheus.instant_query",
    )


async def range_query(
    client: PromClient,
    query: str,
    start: str,
    end: str,
    step: str,
) -> ToolResult:
    """Execute a Prometheus range query (GET /api/v1/query_range)."""
    params: dict[str, str] = {
        "query": query,
        "start": start,
        "end": end,
        "step": step,
    }

    try:
        body = await client._get("/api/v1/query_range", params)
    except httpx.HTTPError as exc:
        return ToolResult(
            status="error",
            data=None,
            summary=f"Prometheus request failed: {exc}",
            tool_name="prometheus.range_query",
            error_message=str(exc),
        )

    if err := _check_prom_response(body, "prometheus.range_query"):
        return err

    data = body.get("data")
    result_count = len(data.get("result", [])) if isinstance(data, dict) else 0
    return ToolResult(
        status="success",
        data=data,
        summary=f"Range query returned {result_count} series",
        tool_name="prometheus.range_query",
    )
