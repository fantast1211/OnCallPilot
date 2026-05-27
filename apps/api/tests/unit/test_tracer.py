"""Tests for Tracer protocol and NoOpTracer."""

import pytest

from oncallpilot_api.observability.tracer import NoOpTracer, Tracer


def test_noop_tracer_implements_protocol():
    tracer: Tracer = NoOpTracer()
    assert isinstance(tracer, Tracer)


def test_noop_start_session():
    tracer = NoOpTracer()
    tracer.start_session("sess-1", {"env": "prod"})  # no error


def test_noop_start_step():
    tracer = NoOpTracer()
    tracer.start_step("fetch_logs", {"source": "loki"})  # no error


def test_noop_record_llm():
    tracer = NoOpTracer()
    tracer.record_llm("gpt-4.1", "hello", "world", {"tokens": 10})  # no error


def test_noop_record_tool():
    tracer = NoOpTracer()
    tracer.record_tool(
        tool="query_prometheus",
        args={"query": "up"},
        result_summary="3 series returned",
        latency_ms=120,
        error=None,
    )


def test_noop_record_tool_with_error():
    tracer = NoOpTracer()
    tracer.record_tool(
        tool="query_prometheus",
        args={"query": "bad"},
        result_summary="",
        latency_ms=50,
        error="timeout",
    )


def test_noop_end_session():
    tracer = NoOpTracer()
    tracer.end_session("completed", {"duration_ms": 500})
