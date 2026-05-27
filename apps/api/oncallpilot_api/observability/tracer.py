"""Tracer protocol and NoOp implementation."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Tracer(Protocol):
    def start_session(self, session_id: str, attrs: dict) -> None: ...
    def start_step(self, name: str, attrs: dict) -> None: ...
    def record_llm(self, model: str, prompt: str, completion: str, usage: dict) -> None: ...
    def record_tool(
        self, tool: str, args: dict, result_summary: str, latency_ms: int, error: str | None
    ) -> None: ...
    def end_session(self, status: str, attrs: dict) -> None: ...


class NoOpTracer:
    """A tracer that does nothing — suitable for testing and local dev."""

    def start_session(self, session_id: str, attrs: dict) -> None:
        pass

    def start_step(self, name: str, attrs: dict) -> None:
        pass

    def record_llm(self, model: str, prompt: str, completion: str, usage: dict) -> None:
        pass

    def record_tool(
        self, tool: str, args: dict, result_summary: str, latency_ms: int, error: str | None
    ) -> None:
        pass

    def end_session(self, status: str, attrs: dict) -> None:
        pass
