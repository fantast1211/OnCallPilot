from __future__ import annotations

import httpx
import pytest
import respx

from oncallpilot_api.tools.base import ToolResult
from oncallpilot_api.tools.loki import (
    TOOL_FAMILY,
    LokiClient,
    query_logs_by_service,
    query_error_logs,
    query_logs_around_time,
    summarize_log_patterns,
)


LOKI_BASE = "http://loki:3100"

LOGS_SUCCESS_BODY = {
    "status": "success",
    "data": {
        "resultType": "streams",
        "result": [
            {
                "stream": {"service": "payment-api", "level": "info"},
                "values": [
                    ["1716900000000000000", "GET /health 200"],
                    ["1716900001000000000", "POST /charge 201"],
                ],
            },
            {
                "stream": {"service": "payment-api", "level": "error"},
                "values": [
                    ["1716900002000000000", "connection timeout to db"],
                ],
            },
        ],
    },
}

ERROR_BODY = {
    "status": "error",
    "errorType": "bad_data",
    "error": "invalid LogQL query",
}


# ── LokiClient unit tests ───────────────────────────────────────────


class TestLokiClientInit:
    def test_default_base_url(self):
        client = LokiClient()
        assert client._base_url == "http://localhost:3100"

    def test_custom_base_url(self):
        client = LokiClient(base_url="http://loki:3100")
        assert client._base_url == "http://loki:3100"

    def test_trailing_slash_stripped(self):
        client = LokiClient(base_url="http://loki:3100/")
        assert client._base_url == "http://loki:3100"


class TestLokiClientClose:
    async def test_close_no_error(self):
        client = LokiClient()
        await client.close()


# ── query_logs_by_service tests ─────────────────────────────────────


class TestQueryLogsByServiceSuccess:
    @respx.mock
    async def test_returns_success_tool_result(self):
        respx.get(f"{LOKI_BASE}/loki/api/v1/query_range").mock(
            return_value=httpx.Response(200, json=LOGS_SUCCESS_BODY)
        )
        client = LokiClient(base_url=LOKI_BASE)
        result = await query_logs_by_service(
            client, service="payment-api", start="1716900000", end="1716900060"
        )

        assert isinstance(result, ToolResult)
        assert result.status == "success"
        assert result.data == LOGS_SUCCESS_BODY["data"]
        assert result.error_message is None
        await client.close()

    @respx.mock
    async def test_sends_correct_params(self):
        route = respx.get(f"{LOKI_BASE}/loki/api/v1/query_range").mock(
            return_value=httpx.Response(200, json=LOGS_SUCCESS_BODY)
        )
        client = LokiClient(base_url=LOKI_BASE)
        await query_logs_by_service(
            client, service="payment-api", start="1716900000", end="1716900060", limit=50
        )

        request = route.calls.last.request
        assert request.url.params["query"] == '{service="payment-api"}'
        assert request.url.params["start"] == "1716900000"
        assert request.url.params["end"] == "1716900060"
        assert request.url.params["limit"] == "50"
        assert request.url.params["direction"] == "backward"
        await client.close()

    @respx.mock
    async def test_custom_loki_label(self):
        route = respx.get(f"{LOKI_BASE}/loki/api/v1/query_range").mock(
            return_value=httpx.Response(200, json=LOGS_SUCCESS_BODY)
        )
        client = LokiClient(base_url=LOKI_BASE)
        await query_logs_by_service(
            client, service="payment-api", start="1716900000", end="1716900060", loki_label="app"
        )

        request = route.calls.last.request
        assert request.url.params["query"] == '{app="payment-api"}'
        await client.close()

    @respx.mock
    async def test_summary_includes_stream_count(self):
        respx.get(f"{LOKI_BASE}/loki/api/v1/query_range").mock(
            return_value=httpx.Response(200, json=LOGS_SUCCESS_BODY)
        )
        client = LokiClient(base_url=LOKI_BASE)
        result = await query_logs_by_service(
            client, service="payment-api", start="1716900000", end="1716900060"
        )

        assert "2" in result.summary  # 2 streams
        assert "stream" in result.summary.lower()
        await client.close()


class TestQueryLogsByServiceError:
    @respx.mock
    async def test_loki_error_response(self):
        respx.get(f"{LOKI_BASE}/loki/api/v1/query_range").mock(
            return_value=httpx.Response(200, json=ERROR_BODY)
        )
        client = LokiClient(base_url=LOKI_BASE)
        result = await query_logs_by_service(
            client, service="payment-api", start="0", end="0"
        )

        assert result.status == "error"
        assert result.error_message is not None
        assert "invalid LogQL" in result.error_message
        await client.close()

    @respx.mock
    async def test_network_error(self):
        respx.get(f"{LOKI_BASE}/loki/api/v1/query_range").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        client = LokiClient(base_url=LOKI_BASE)
        result = await query_logs_by_service(
            client, service="payment-api", start="0", end="0"
        )

        assert result.status == "error"
        assert result.error_message is not None
        await client.close()

    @respx.mock
    async def test_http_500_error(self):
        respx.get(f"{LOKI_BASE}/loki/api/v1/query_range").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        client = LokiClient(base_url=LOKI_BASE)
        result = await query_logs_by_service(
            client, service="payment-api", start="0", end="0"
        )

        assert result.status == "error"
        assert result.error_message is not None
        await client.close()


# ── query_error_logs tests ──────────────────────────────────────────


class TestQueryErrorLogsSuccess:
    @respx.mock
    async def test_returns_success_tool_result(self):
        respx.get(f"{LOKI_BASE}/loki/api/v1/query_range").mock(
            return_value=httpx.Response(200, json=LOGS_SUCCESS_BODY)
        )
        client = LokiClient(base_url=LOKI_BASE)
        result = await query_error_logs(
            client, service="payment-api", start="1716900000", end="1716900060"
        )

        assert isinstance(result, ToolResult)
        assert result.status == "success"
        assert result.data == LOGS_SUCCESS_BODY["data"]
        await client.close()

    @respx.mock
    async def test_sends_error_filter_query(self):
        route = respx.get(f"{LOKI_BASE}/loki/api/v1/query_range").mock(
            return_value=httpx.Response(200, json=LOGS_SUCCESS_BODY)
        )
        client = LokiClient(base_url=LOKI_BASE)
        await query_error_logs(
            client, service="payment-api", start="1716900000", end="1716900060"
        )

        request = route.calls.last.request
        query = request.url.params["query"]
        assert '{service="payment-api"}' in query
        assert "error" in query.lower()
        await client.close()

    @respx.mock
    async def test_custom_loki_label(self):
        route = respx.get(f"{LOKI_BASE}/loki/api/v1/query_range").mock(
            return_value=httpx.Response(200, json=LOGS_SUCCESS_BODY)
        )
        client = LokiClient(base_url=LOKI_BASE)
        await query_error_logs(
            client, service="payment-api", start="1716900000", end="1716900060", loki_label="app"
        )

        request = route.calls.last.request
        query = request.url.params["query"]
        assert '{app="payment-api"}' in query
        await client.close()


class TestQueryErrorLogsError:
    @respx.mock
    async def test_loki_error_response(self):
        respx.get(f"{LOKI_BASE}/loki/api/v1/query_range").mock(
            return_value=httpx.Response(200, json=ERROR_BODY)
        )
        client = LokiClient(base_url=LOKI_BASE)
        result = await query_error_logs(
            client, service="payment-api", start="0", end="0"
        )

        assert result.status == "error"
        await client.close()

    @respx.mock
    async def test_network_error(self):
        respx.get(f"{LOKI_BASE}/loki/api/v1/query_range").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        client = LokiClient(base_url=LOKI_BASE)
        result = await query_error_logs(
            client, service="payment-api", start="0", end="0"
        )

        assert result.status == "error"
        await client.close()


# ── query_logs_around_time tests ────────────────────────────────────


class TestQueryLogsAroundTimeSuccess:
    @respx.mock
    async def test_returns_success_tool_result(self):
        respx.get(f"{LOKI_BASE}/loki/api/v1/query_range").mock(
            return_value=httpx.Response(200, json=LOGS_SUCCESS_BODY)
        )
        client = LokiClient(base_url=LOKI_BASE)
        result = await query_logs_around_time(
            client, service="payment-api", ts="1716900000"
        )

        assert isinstance(result, ToolResult)
        assert result.status == "success"
        await client.close()

    @respx.mock
    async def test_computes_window_from_ts(self):
        route = respx.get(f"{LOKI_BASE}/loki/api/v1/query_range").mock(
            return_value=httpx.Response(200, json=LOGS_SUCCESS_BODY)
        )
        client = LokiClient(base_url=LOKI_BASE)
        # ts=1716900000, before=2m=120s, after=2m=120s
        await query_logs_around_time(
            client, service="payment-api", ts="1716900000"
        )

        request = route.calls.last.request
        assert request.url.params["start"] == "1716899880"  # 1716900000 - 120
        assert request.url.params["end"] == "1716900120"    # 1716900000 + 120
        assert request.url.params["query"] == '{service="payment-api"}'
        await client.close()

    @respx.mock
    async def test_custom_before_after(self):
        route = respx.get(f"{LOKI_BASE}/loki/api/v1/query_range").mock(
            return_value=httpx.Response(200, json=LOGS_SUCCESS_BODY)
        )
        client = LokiClient(base_url=LOKI_BASE)
        await query_logs_around_time(
            client, service="payment-api", ts="1716900000", before="5m", after="1m"
        )

        request = route.calls.last.request
        assert request.url.params["start"] == "1716899700"  # 1716900000 - 300
        assert request.url.params["end"] == "1716900060"    # 1716900000 + 60
        await client.close()

    @respx.mock
    async def test_custom_loki_label(self):
        route = respx.get(f"{LOKI_BASE}/loki/api/v1/query_range").mock(
            return_value=httpx.Response(200, json=LOGS_SUCCESS_BODY)
        )
        client = LokiClient(base_url=LOKI_BASE)
        await query_logs_around_time(
            client, service="payment-api", ts="1716900000", loki_label="app"
        )

        request = route.calls.last.request
        assert request.url.params["query"] == '{app="payment-api"}'
        await client.close()


class TestQueryLogsAroundTimeError:
    @respx.mock
    async def test_network_error(self):
        respx.get(f"{LOKI_BASE}/loki/api/v1/query_range").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        client = LokiClient(base_url=LOKI_BASE)
        result = await query_logs_around_time(
            client, service="payment-api", ts="1716900000"
        )

        assert result.status == "error"
        await client.close()


# ── summarize_log_patterns tests ────────────────────────────────────


PATTERNS_BODY = {
    "status": "success",
    "data": {
        "resultType": "streams",
        "result": [
            {
                "stream": {"service": "payment-api"},
                "values": [
                    ["1716900000000000000", "GET /health 200"],
                    ["1716900001000000000", "GET /health 200"],
                    ["1716900002000000000", "GET /health 200"],
                    ["1716900003000000000", "POST /charge 500 timeout"],
                    ["1716900004000000000", "POST /charge 500 timeout"],
                    ["1716900005000000000", "connection reset"],
                ],
            }
        ],
    },
}


class TestSummarizeLogPatternsSuccess:
    @respx.mock
    async def test_returns_success_with_patterns(self):
        respx.get(f"{LOKI_BASE}/loki/api/v1/query_range").mock(
            return_value=httpx.Response(200, json=PATTERNS_BODY)
        )
        client = LokiClient(base_url=LOKI_BASE)
        result = await summarize_log_patterns(
            client, service="payment-api", start="1716900000", end="1716900060"
        )

        assert isinstance(result, ToolResult)
        assert result.status == "success"
        patterns = result.data
        assert isinstance(patterns, list)
        assert len(patterns) > 0
        # First pattern should be the most frequent
        assert patterns[0]["count"] >= patterns[-1]["count"]
        await client.close()

    @respx.mock
    async def test_patterns_have_count_and_sample(self):
        respx.get(f"{LOKI_BASE}/loki/api/v1/query_range").mock(
            return_value=httpx.Response(200, json=PATTERNS_BODY)
        )
        client = LokiClient(base_url=LOKI_BASE)
        result = await summarize_log_patterns(
            client, service="payment-api", start="1716900000", end="1716900060"
        )

        for pattern in result.data:
            assert "count" in pattern
            assert "sample" in pattern
            assert isinstance(pattern["count"], int)
            assert isinstance(pattern["sample"], str)
        await client.close()

    @respx.mock
    async def test_respects_top_n(self):
        respx.get(f"{LOKI_BASE}/loki/api/v1/query_range").mock(
            return_value=httpx.Response(200, json=PATTERNS_BODY)
        )
        client = LokiClient(base_url=LOKI_BASE)
        result = await summarize_log_patterns(
            client, service="payment-api", start="1716900000", end="1716900060", top_n=2
        )

        assert len(result.data) <= 2
        await client.close()

    @respx.mock
    async def test_custom_loki_label(self):
        route = respx.get(f"{LOKI_BASE}/loki/api/v1/query_range").mock(
            return_value=httpx.Response(200, json=PATTERNS_BODY)
        )
        client = LokiClient(base_url=LOKI_BASE)
        await summarize_log_patterns(
            client, service="payment-api", start="1716900000", end="1716900060", loki_label="app"
        )

        request = route.calls.last.request
        assert request.url.params["query"] == '{app="payment-api"}'
        await client.close()


class TestSummarizeLogPatternsError:
    @respx.mock
    async def test_loki_error_response(self):
        respx.get(f"{LOKI_BASE}/loki/api/v1/query_range").mock(
            return_value=httpx.Response(200, json=ERROR_BODY)
        )
        client = LokiClient(base_url=LOKI_BASE)
        result = await summarize_log_patterns(
            client, service="payment-api", start="0", end="0"
        )

        assert result.status == "error"
        await client.close()

    @respx.mock
    async def test_network_error(self):
        respx.get(f"{LOKI_BASE}/loki/api/v1/query_range").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        client = LokiClient(base_url=LOKI_BASE)
        result = await summarize_log_patterns(
            client, service="payment-api", start="0", end="0"
        )

        assert result.status == "error"
        await client.close()


# ── empty result handling ───────────────────────────────────────────


class TestEmptyResults:
    @respx.mock
    async def test_empty_streams_returns_success(self):
        empty_body = {
            "status": "success",
            "data": {"resultType": "streams", "result": []},
        }
        respx.get(f"{LOKI_BASE}/loki/api/v1/query_range").mock(
            return_value=httpx.Response(200, json=empty_body)
        )
        client = LokiClient(base_url=LOKI_BASE)
        result = await query_logs_by_service(
            client, service="unknown-svc", start="1716900000", end="1716900060"
        )

        assert result.status == "success"
        assert result.data == empty_body["data"]
        assert "0" in result.summary
        await client.close()

    @respx.mock
    async def test_empty_streams_summarize_returns_empty_patterns(self):
        empty_body = {
            "status": "success",
            "data": {"resultType": "streams", "result": []},
        }
        respx.get(f"{LOKI_BASE}/loki/api/v1/query_range").mock(
            return_value=httpx.Response(200, json=empty_body)
        )
        client = LokiClient(base_url=LOKI_BASE)
        result = await summarize_log_patterns(
            client, service="unknown-svc", start="1716900000", end="1716900060"
        )

        assert result.status == "success"
        assert result.data == []
        await client.close()


# ── Tool family constant ────────────────────────────────────────────


class TestToolFamily:
    def test_family_is_loki(self):
        assert TOOL_FAMILY == "loki"


# ── helpers ─────────────────────────────────────────────────────────


def request_url_params(route: respx.Route) -> dict[str, str]:
    request = route.calls.last.request
    return dict(request.url.params)
