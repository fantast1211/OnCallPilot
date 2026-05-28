from __future__ import annotations

import re
from collections import Counter
from typing import Any

import httpx

from oncallpilot_api.tools.base import ToolResult

TOOL_FAMILY = "loki"

_DEFAULT_TIMEOUT = 30.0

# Matches error/exception/fatal (case-insensitive) in log lines.
_ERROR_PATTERN = r"(?i)(error|exception|fatal)"

# Parses duration strings like "2m", "30s", "1h" into seconds.
_DURATION_RE = re.compile(r"^(\d+)(s|m|h)$")
_DURATION_MULTIPLIERS = {"s": 1, "m": 60, "h": 3600}


class LokiClient:
    """Thin async wrapper around the Loki HTTP API."""

    def __init__(self, base_url: str = "http://localhost:3100") -> None:
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


def _parse_duration(duration: str) -> int:
    """Parse a duration string like '2m', '30s', '1h' into seconds."""
    m = _DURATION_RE.match(duration)
    if not m:
        raise ValueError(f"Invalid duration format: {duration!r} (expected Ns/Nm/Nh)")
    return int(m.group(1)) * _DURATION_MULTIPLIERS[m.group(2)]


def _check_loki_response(body: dict[str, Any], tool_name: str) -> ToolResult | None:
    """Return an error ToolResult if Loki reported a failure, else None."""
    if body.get("status") == "error":
        error = body.get("error", "unknown Loki error")
        return ToolResult(
            status="error",
            data=body,
            summary=f"Loki error: {error}",
            tool_name=tool_name,
            error_message=error,
        )
    return None


async def _query_range(
    client: LokiClient,
    query: str,
    start: str,
    end: str,
    limit: int = 100,
    tool_name: str = "loki.query_range",
) -> ToolResult:
    """Shared helper: execute a Loki query_range and return a ToolResult."""
    params: dict[str, str] = {
        "query": query,
        "start": start,
        "end": end,
        "limit": str(limit),
        "direction": "backward",
    }

    try:
        body = await client._get("/loki/api/v1/query_range", params)
    except httpx.HTTPError as exc:
        return ToolResult(
            status="error",
            data=None,
            summary=f"Loki request failed: {str(exc)[:200]}",
            tool_name=tool_name,
            error_message=str(exc),
        )

    if err := _check_loki_response(body, tool_name):
        return err

    data = body.get("data")
    return ToolResult(
        status="success",
        data=data,
        summary=_build_stream_summary(data),
        tool_name=tool_name,
    )


def _build_stream_summary(data: Any) -> str:
    """Build a short summary from Loki response data."""
    if not isinstance(data, dict):
        return "Loki returned no data"
    result = data.get("result", [])
    stream_count = len(result)
    total_lines = sum(len(s.get("values", [])) for s in result)
    return f"Loki returned {stream_count} stream(s), {total_lines} line(s)"


# ── Tool functions ──────────────────────────────────────────────────


async def query_logs_by_service(
    client: LokiClient,
    service: str,
    start: str,
    end: str,
    limit: int = 100,
    loki_label: str = "service",
) -> ToolResult:
    """Query logs for a service (GET /loki/api/v1/query_range).

    Args:
        client: LokiClient instance.
        service: Service name to filter by.
        start: Start timestamp (Unix seconds or RFC3339).
        end: End timestamp (Unix seconds or RFC3339).
        limit: Max number of log lines to return.
        loki_label: Label name used in the LogQL selector (default "service").

    Returns:
        ToolResult with Loki streams data.
    """
    query = f'{{{loki_label}="{service}"}}'
    return await _query_range(client, query, start, end, limit, tool_name="loki.query_logs_by_service")


async def query_error_logs(
    client: LokiClient,
    service: str,
    start: str,
    end: str,
    limit: int = 100,
    loki_label: str = "service",
) -> ToolResult:
    """Query error-level logs for a service.

    Uses a regex line filter matching error/exception/fatal (case-insensitive).

    Args:
        client: LokiClient instance.
        service: Service name to filter by.
        start: Start timestamp.
        end: End timestamp.
        limit: Max number of log lines to return.
        loki_label: Label name used in the LogQL selector (default "service").

    Returns:
        ToolResult with filtered Loki streams data.
    """
    query = f'{{{loki_label}="{service}"}} |~ "{_ERROR_PATTERN}"'
    return await _query_range(client, query, start, end, limit, tool_name="loki.query_error_logs")


async def query_logs_around_time(
    client: LokiClient,
    service: str,
    ts: str,
    before: str = "2m",
    after: str = "2m",
    limit: int = 100,
    loki_label: str = "service",
) -> ToolResult:
    """Query logs around a specific timestamp.

    Computes a time window [ts - before, ts + after].

    Args:
        client: LokiClient instance.
        service: Service name to filter by.
        ts: Center timestamp (Unix seconds).
        before: Duration to look back (e.g. "2m", "30s").
        after: Duration to look ahead (e.g. "2m", "30s").
        limit: Max number of log lines to return.
        loki_label: Label name used in the LogQL selector (default "service").

    Returns:
        ToolResult with Loki streams data around the given time.
    """
    ts_int = int(ts)
    before_s = _parse_duration(before)
    after_s = _parse_duration(after)
    start = str(ts_int - before_s)
    end = str(ts_int + after_s)

    query = f'{{{loki_label}="{service}"}}'
    return await _query_range(client, query, start, end, limit, tool_name="loki.query_logs_around_time")


async def summarize_log_patterns(
    client: LokiClient,
    service: str,
    start: str,
    end: str,
    limit: int = 1000,
    top_n: int = 10,
    loki_label: str = "service",
) -> ToolResult:
    """Summarize log patterns by frequency (simple top-N clustering).

    Fetches up to *limit* log lines, normalizes each line by stripping
    digits and UUIDs, then returns the *top_n* most common patterns.

    Args:
        client: LokiClient instance.
        service: Service name to filter by.
        start: Start timestamp.
        end: End timestamp.
        limit: Max log lines to fetch for analysis.
        top_n: Number of top patterns to return.
        loki_label: Label name used in the LogQL selector (default "service").

    Returns:
        ToolResult with data=list[dict] containing count and sample per pattern.
    """
    query = f'{{{loki_label}="{service}"}}'
    result = await _query_range(client, query, start, end, limit)

    if result.status != "success":
        return result

    data = result.data
    if not isinstance(data, dict):
        return ToolResult(status="success", data=[], summary="No log lines to analyze")

    # Collect all log lines from all streams.
    lines: list[str] = []
    for stream in data.get("result", []):
        for _, line in stream.get("values", []):
            lines.append(line)

    if not lines:
        return ToolResult(status="success", data=[], summary="No log lines to analyze")

    # Normalize: strip digits and UUIDs so similar lines cluster together.
    _UUID_RE = re.compile(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        re.IGNORECASE,
    )
    _DIGIT_RE = re.compile(r"\d+")

    def _normalize(line: str) -> str:
        line = _UUID_RE.sub("<UUID>", line)
        line = _DIGIT_RE.sub("<N>", line)
        return line

    counter: Counter[str] = Counter()
    for line in lines:
        counter[_normalize(line)] += 1

    patterns = [
        {"count": count, "sample": sample}
        for sample, count in counter.most_common(top_n)
    ]

    return ToolResult(
        status="success",
        data=patterns,
        summary=f"Top {len(patterns)} patterns from {len(lines)} log lines",
    )
