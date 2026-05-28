from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from oncallpilot_api.tools.base import ToolResult
from oncallpilot_api.tools.connectivity import (
    TOOL_FAMILY,
    check_http_endpoint,
    check_service_connectivity,
    check_tcp_port,
)


# ── Constants ────────────────────────────────────────────────────────


TOOL_FAMILY_NAME = "connectivity"


# ── TOOL_FAMILY ──────────────────────────────────────────────────────


class TestToolFamily:
    def test_family_is_connectivity(self):
        assert TOOL_FAMILY == TOOL_FAMILY_NAME


# ── check_http_endpoint ──────────────────────────────────────────────


class TestCheckHttpEndpointSuccess:
    @respx.mock
    async def test_returns_success_for_200(self):
        url = "http://api:8080/health"
        respx.get(url).mock(return_value=httpx.Response(200, json={"status": "ok"}))

        result = await check_http_endpoint(url)

        assert isinstance(result, ToolResult)
        assert result.status == "success"
        assert result.data["status_code"] == 200
        assert "response_time_ms" in result.data
        assert result.error_message is None

    @respx.mock
    async def test_includes_body_snippet(self):
        url = "http://api:8080/status"
        respx.get(url).mock(return_value=httpx.Response(200, text="alive"))

        result = await check_http_endpoint(url)

        assert result.data["body_snippet"] == "alive"

    @respx.mock
    async def test_custom_method(self):
        url = "http://api:8080/health"
        respx.head(url).mock(return_value=httpx.Response(200))

        result = await check_http_endpoint(url, method="HEAD")

        assert result.status == "success"
        assert "HEAD" in result.summary

    @respx.mock
    async def test_expected_status_matches(self):
        url = "http://api:8080/created"
        respx.post(url).mock(return_value=httpx.Response(201))

        result = await check_http_endpoint(url, method="POST", expected_status=201)

        assert result.status == "success"

    @respx.mock
    async def test_custom_headers_sent(self):
        url = "http://api:8080/auth"
        route = respx.get(url).mock(return_value=httpx.Response(200))

        await check_http_endpoint(url, headers={"Authorization": "Bearer tok"})

        request = route.calls.last.request
        assert request.headers["Authorization"] == "Bearer tok"


class TestCheckHttpEndpointError:
    @respx.mock
    async def test_returns_error_for_500(self):
        url = "http://api:8080/broken"
        respx.get(url).mock(return_value=httpx.Response(500, text="oops"))

        result = await check_http_endpoint(url)

        assert result.status == "error"
        assert result.data["status_code"] == 500
        assert result.error_message is not None

    @respx.mock
    async def test_expected_status_mismatch(self):
        url = "http://api:8080/health"
        respx.get(url).mock(return_value=httpx.Response(200))

        result = await check_http_endpoint(url, expected_status=201)

        assert result.status == "error"
        assert "expected 201" in result.summary

    @respx.mock
    async def test_timeout(self):
        url = "http://api:8080/slow"
        respx.get(url).mock(side_effect=httpx.ReadTimeout("read timeout"))

        result = await check_http_endpoint(url, timeout=1.0)

        assert result.status == "error"
        assert "timed out" in result.summary
        assert result.error_message == "timeout"

    @respx.mock
    async def test_connection_error(self):
        url = "http://api:8080/down"
        respx.get(url).mock(side_effect=httpx.ConnectError("connection refused"))

        result = await check_http_endpoint(url)

        assert result.status == "error"
        assert result.error_message is not None

    @respx.mock
    async def test_404_returns_error(self):
        url = "http://api:8080/missing"
        respx.get(url).mock(return_value=httpx.Response(404))

        result = await check_http_endpoint(url)

        assert result.status == "error"
        assert result.data["status_code"] == 404


class TestCheckHttpEndpointResponseTime:
    @respx.mock
    async def test_response_time_is_numeric(self):
        url = "http://api:8080/fast"
        respx.get(url).mock(return_value=httpx.Response(200))

        result = await check_http_endpoint(url)

        assert isinstance(result.data["response_time_ms"], float)
        assert result.data["response_time_ms"] >= 0


# ── check_tcp_port ───────────────────────────────────────────────────


class TestCheckTcpPortSuccess:
    async def test_open_port_returns_success(self, unused_tcp_port):
        server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", unused_tcp_port)
        try:
            result = await check_tcp_port("127.0.0.1", unused_tcp_port, timeout=2.0)
            assert result.status == "success"
            assert result.data["host"] == "127.0.0.1"
            assert result.data["port"] == unused_tcp_port
            assert "response_time_ms" in result.data
        finally:
            server.close()
            await server.wait_closed()

    async def test_response_time_is_numeric(self, unused_tcp_port):
        server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", unused_tcp_port)
        try:
            result = await check_tcp_port("127.0.0.1", unused_tcp_port, timeout=2.0)
            assert isinstance(result.data["response_time_ms"], float)
            assert result.data["response_time_ms"] >= 0
        finally:
            server.close()
            await server.wait_closed()


class TestCheckTcpPortError:
    async def test_closed_port_returns_error(self):
        # Port 1 is almost certainly not listening.
        result = await check_tcp_port("127.0.0.1", 1, timeout=2.0)

        assert result.status == "error"
        assert result.error_message is not None

    async def test_unreachable_host_returns_error(self):
        # 192.0.2.0/24 is TEST-NET, guaranteed unroutable.
        result = await check_tcp_port("192.0.2.1", 80, timeout=1.0)

        assert result.status == "error"
        assert result.error_message is not None


# ── check_service_connectivity ───────────────────────────────────────


class TestCheckServiceConnectivity:
    @respx.mock
    async def test_http_only(self):
        url = "http://api:8080/health"
        respx.get(url).mock(return_value=httpx.Response(200))

        result = await check_service_connectivity("my-api", http_url=url)

        assert result.status == "success"
        assert result.data["service"] == "my-api"
        assert "http" in result.data["checks"]
        assert "tcp" not in result.data["checks"]

    async def test_tcp_only(self, unused_tcp_port):
        server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", unused_tcp_port)
        try:
            result = await check_service_connectivity(
                "redis", tcp_host="127.0.0.1", tcp_port=unused_tcp_port, timeout=2.0,
            )
            assert result.status == "success"
            assert "tcp" in result.data["checks"]
            assert "http" not in result.data["checks"]
        finally:
            server.close()
            await server.wait_closed()

    @respx.mock
    async def test_both_http_and_tcp(self, unused_tcp_port):
        url = "http://api:8080/health"
        respx.get(url).mock(return_value=httpx.Response(200))
        server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", unused_tcp_port)
        try:
            result = await check_service_connectivity(
                "full-service",
                http_url=url,
                tcp_host="127.0.0.1",
                tcp_port=unused_tcp_port,
                timeout=2.0,
            )
            assert result.status == "success"
            assert "http" in result.data["checks"]
            assert "tcp" in result.data["checks"]
        finally:
            server.close()
            await server.wait_closed()

    async def test_no_endpoints_returns_error(self):
        result = await check_service_connectivity("empty")

        assert result.status == "error"
        assert "No endpoints specified" in result.summary

    @respx.mock
    async def test_partial_failure_aggregated(self):
        url = "http://api:8080/health"
        respx.get(url).mock(return_value=httpx.Response(500))

        result = await check_service_connectivity("flaky", http_url=url)

        assert result.status == "error"
        assert "http" in result.error_message

    @respx.mock
    async def test_http_fails_tcp_passes(self, unused_tcp_port):
        url = "http://api:8080/health"
        respx.get(url).mock(side_effect=httpx.ConnectError("refused"))
        server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", unused_tcp_port)
        try:
            result = await check_service_connectivity(
                "mixed",
                http_url=url,
                tcp_host="127.0.0.1",
                tcp_port=unused_tcp_port,
                timeout=2.0,
            )
            assert result.status == "error"
            assert "http" in result.data["checks"]
            assert result.data["checks"]["http"]["status"] == "error"
            assert result.data["checks"]["tcp"]["status"] == "success"
        finally:
            server.close()
            await server.wait_closed()


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def unused_tcp_port():
    """Find an unused TCP port on localhost."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
