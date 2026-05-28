from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from oncallpilot_api.tools.base import ToolResult

TOOL_FAMILY = "connectivity"

_DEFAULT_TIMEOUT = 10.0


async def check_http_endpoint(
    url: str,
    method: str = "GET",
    timeout: float = _DEFAULT_TIMEOUT,
    expected_status: int | None = None,
    headers: dict[str, str] | None = None,
) -> ToolResult:
    """Check reachability and response of an HTTP endpoint.

    Args:
        url: Full URL to check (e.g. "http://api:8080/health").
        method: HTTP method (default GET).
        timeout: Request timeout in seconds.
        expected_status: If set, treat any other status code as an error.
        headers: Optional request headers.

    Returns:
        ToolResult with status_code, response_time_ms, and body snippet.
    """
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method, url, headers=headers)
        elapsed_ms = round((time.monotonic() - start) * 1000, 2)
    except httpx.TimeoutException:
        elapsed_ms = round((time.monotonic() - start) * 1000, 2)
        return ToolResult(
            status="error",
            data={"url": url, "response_time_ms": elapsed_ms},
            summary=f"HTTP {method} {url} timed out after {timeout}s",
            error_message="timeout",
        )
    except httpx.HTTPError as exc:
        elapsed_ms = round((time.monotonic() - start) * 1000, 2)
        return ToolResult(
            status="error",
            data={"url": url, "response_time_ms": elapsed_ms},
            summary=f"HTTP {method} {url} failed: {exc}",
            error_message=str(exc),
        )

    data: dict[str, Any] = {
        "url": url,
        "status_code": resp.status_code,
        "response_time_ms": elapsed_ms,
        "body_snippet": resp.text[:500],
    }

    if expected_status is not None and resp.status_code != expected_status:
        return ToolResult(
            status="error",
            data=data,
            summary=f"HTTP {method} {url} returned {resp.status_code}, expected {expected_status}",
            error_message=f"unexpected status {resp.status_code}",
        )

    if resp.status_code >= 400:
        return ToolResult(
            status="error",
            data=data,
            summary=f"HTTP {method} {url} returned {resp.status_code}",
            error_message=f"HTTP {resp.status_code}",
        )

    return ToolResult(
        status="success",
        data=data,
        summary=f"HTTP {method} {url} returned {resp.status_code} in {elapsed_ms}ms",
    )


async def check_tcp_port(
    host: str,
    port: int,
    timeout: float = _DEFAULT_TIMEOUT,
) -> ToolResult:
    """Check if a TCP port is accepting connections.

    Args:
        host: Hostname or IP address.
        port: TCP port number.
        timeout: Connection timeout in seconds.

    Returns:
        ToolResult with connect time and success/failure status.
    """
    start = time.monotonic()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        elapsed_ms = round((time.monotonic() - start) * 1000, 2)
        writer.close()
        await writer.wait_closed()
    except asyncio.TimeoutError:
        elapsed_ms = round((time.monotonic() - start) * 1000, 2)
        return ToolResult(
            status="error",
            data={"host": host, "port": port, "response_time_ms": elapsed_ms},
            summary=f"TCP {host}:{port} timed out after {timeout}s",
            error_message="timeout",
        )
    except OSError as exc:
        elapsed_ms = round((time.monotonic() - start) * 1000, 2)
        return ToolResult(
            status="error",
            data={"host": host, "port": port, "response_time_ms": elapsed_ms},
            summary=f"TCP {host}:{port} connection refused: {exc}",
            error_message=str(exc),
        )

    return ToolResult(
        status="success",
        data={"host": host, "port": port, "response_time_ms": elapsed_ms},
        summary=f"TCP {host}:{port} reachable in {elapsed_ms}ms",
    )


async def check_service_connectivity(
    name: str,
    http_url: str | None = None,
    tcp_host: str | None = None,
    tcp_port: int | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> ToolResult:
    """Run a comprehensive connectivity check for a service.

    Runs HTTP and/or TCP checks in parallel and aggregates the results.

    Args:
        name: Human-readable service name.
        http_url: URL for HTTP check (skipped if None).
        tcp_host: Host for TCP check (skipped if None or if tcp_port is None).
        tcp_port: Port for TCP check.
        timeout: Timeout per check in seconds.

    Returns:
        ToolResult with aggregated results from all checks.
    """
    if http_url is None and (tcp_host is None or tcp_port is None):
        return ToolResult(
            status="error",
            data=None,
            summary=f"No endpoints specified for service '{name}'",
            error_message="at least one of http_url or tcp_host+tcp_port required",
        )

    tasks: list[asyncio.Task[ToolResult]] = []
    labels: list[str] = []

    if http_url is not None:
        tasks.append(asyncio.create_task(check_http_endpoint(http_url, timeout=timeout)))
        labels.append("http")

    if tcp_host is not None and tcp_port is not None:
        tasks.append(asyncio.create_task(check_tcp_port(tcp_host, tcp_port, timeout=timeout)))
        labels.append("tcp")

    results = await asyncio.gather(*tasks, return_exceptions=True)

    check_results: dict[str, Any] = {}
    all_ok = True
    for label, res in zip(labels, results):
        if isinstance(res, BaseException):
            check_results[label] = {"status": "error", "error": str(res)}
            all_ok = False
        else:
            check_results[label] = res.model_dump()
            if res.status != "success":
                all_ok = False

    data = {"service": name, "checks": check_results}

    if all_ok:
        return ToolResult(
            status="success",
            data=data,
            summary=f"Service '{name}': all connectivity checks passed",
        )

    failed = [label for label, r in check_results.items() if r.get("status") != "success"]
    return ToolResult(
        status="error",
        data=data,
        summary=f"Service '{name}': {', '.join(failed)} check(s) failed",
        error_message=f"failed: {', '.join(failed)}",
    )
