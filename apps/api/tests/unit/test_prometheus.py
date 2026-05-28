from __future__ import annotations

import httpx
import pytest
import respx

from oncallpilot_api.tools.base import ToolResult
from oncallpilot_api.tools.prometheus import (
    TOOL_FAMILY,
    PromClient,
    instant_query,
    range_query,
)


PROM_BASE = "http://prometheus:9090"

INSTANT_SUCCESS_BODY = {
    "status": "success",
    "data": {
        "resultType": "vector",
        "result": [
            {
                "metric": {"__name__": "up", "job": "api-server"},
                "value": [1716900000, "1"],
            }
        ],
    },
}

RANGE_SUCCESS_BODY = {
    "status": "success",
    "data": {
        "resultType": "matrix",
        "result": [
            {
                "metric": {"__name__": "up", "job": "api-server"},
                "values": [
                    [1716900000, "1"],
                    [1716900060, "1"],
                ],
            }
        ],
    },
}

ERROR_BODY = {
    "status": "error",
    "errorType": "bad_data",
    "error": "invalid query",
}


# ── PromClient unit tests ────────────────────────────────────────────


class TestPromClientInit:
    def test_default_base_url(self):
        client = PromClient()
        assert client._base_url == "http://localhost:9090"

    def test_custom_base_url(self):
        client = PromClient(base_url="http://prom:9090")
        assert client._base_url == "http://prom:9090"

    def test_trailing_slash_stripped(self):
        client = PromClient(base_url="http://prom:9090/")
        assert client._base_url == "http://prom:9090"


class TestPromClientClose:
    async def test_close_no_error(self):
        client = PromClient()
        await client.close()  # should not raise


# ── instant_query tests ──────────────────────────────────────────────


class TestInstantQuerySuccess:
    @respx.mock
    async def test_returns_success_tool_result(self):
        respx.get(f"{PROM_BASE}/api/v1/query").mock(
            return_value=httpx.Response(200, json=INSTANT_SUCCESS_BODY)
        )
        client = PromClient(base_url=PROM_BASE)
        result = await instant_query(client, query="up", time="1716900000")

        assert isinstance(result, ToolResult)
        assert result.status == "success"
        assert result.data == INSTANT_SUCCESS_BODY["data"]
        assert result.error_message is None
        await client.close()

    @respx.mock
    async def test_sends_query_and_time_params(self):
        route = respx.get(f"{PROM_BASE}/api/v1/query").mock(
            return_value=httpx.Response(200, json=INSTANT_SUCCESS_BODY)
        )
        client = PromClient(base_url=PROM_BASE)
        await instant_query(client, query="up", time="1716900000")

        request = route.calls.last.request
        assert request.url.params["query"] == "up"
        assert request.url.params["time"] == "1716900000"
        await client.close()


class TestInstantQueryError:
    @respx.mock
    async def test_prometheus_error_response(self):
        respx.get(f"{PROM_BASE}/api/v1/query").mock(
            return_value=httpx.Response(200, json=ERROR_BODY)
        )
        client = PromClient(base_url=PROM_BASE)
        result = await instant_query(client, query="bad{query}")

        assert result.status == "error"
        assert result.error_message is not None
        assert "invalid query" in result.error_message
        await client.close()

    @respx.mock
    async def test_network_error(self):
        respx.get(f"{PROM_BASE}/api/v1/query").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        client = PromClient(base_url=PROM_BASE)
        result = await instant_query(client, query="up")

        assert result.status == "error"
        assert result.error_message is not None
        await client.close()

    @respx.mock
    async def test_http_500_error(self):
        respx.get(f"{PROM_BASE}/api/v1/query").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        client = PromClient(base_url=PROM_BASE)
        result = await instant_query(client, query="up")

        assert result.status == "error"
        assert result.error_message is not None
        await client.close()


# ── range_query tests ────────────────────────────────────────────────


class TestRangeQuerySuccess:
    @respx.mock
    async def test_returns_success_tool_result(self):
        respx.get(f"{PROM_BASE}/api/v1/query_range").mock(
            return_value=httpx.Response(200, json=RANGE_SUCCESS_BODY)
        )
        client = PromClient(base_url=PROM_BASE)
        result = await range_query(
            client,
            query="up",
            start="1716900000",
            end="1716900060",
            step="60",
        )

        assert isinstance(result, ToolResult)
        assert result.status == "success"
        assert result.data == RANGE_SUCCESS_BODY["data"]
        assert result.error_message is None
        await client.close()

    @respx.mock
    async def test_sends_all_range_params(self):
        route = respx.get(f"{PROM_BASE}/api/v1/query_range").mock(
            return_value=httpx.Response(200, json=RANGE_SUCCESS_BODY)
        )
        client = PromClient(base_url=PROM_BASE)
        await range_query(
            client,
            query="rate(http_requests_total[5m])",
            start="1716900000",
            end="1716900060",
            step="15",
        )

        request = route.calls.last.request
        assert request.url.params["query"] == "rate(http_requests_total[5m])"
        assert request.url.params["start"] == "1716900000"
        assert request.url.params["end"] == "1716900060"
        assert request.url.params["step"] == "15"
        await client.close()


class TestRangeQueryError:
    @respx.mock
    async def test_prometheus_error_response(self):
        respx.get(f"{PROM_BASE}/api/v1/query_range").mock(
            return_value=httpx.Response(200, json=ERROR_BODY)
        )
        client = PromClient(base_url=PROM_BASE)
        result = await range_query(
            client, query="up", start="0", end="0", step="60"
        )

        assert result.status == "error"
        assert result.error_message is not None
        await client.close()

    @respx.mock
    async def test_network_error(self):
        respx.get(f"{PROM_BASE}/api/v1/query_range").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        client = PromClient(base_url=PROM_BASE)
        result = await range_query(
            client, query="up", start="0", end="0", step="60"
        )

        assert result.status == "error"
        assert result.error_message is not None
        await client.close()


# ── Tool family constant ─────────────────────────────────────────────


class TestToolFamily:
    def test_family_is_prometheus(self):
        assert TOOL_FAMILY == "prometheus"


# ── helpers ──────────────────────────────────────────────────────────


def request_url_params(route: respx.Route) -> dict[str, str]:
    request = route.calls.last.request
    return dict(request.url.params)
