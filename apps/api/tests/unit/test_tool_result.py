from __future__ import annotations

import pytest
from pydantic import ValidationError

from oncallpilot_api.tools.base import ToolResult


class TestToolResultCreation:
    def test_success_result(self):
        result = ToolResult(status="success", data={"pods": 3}, summary="Found 3 pods")
        assert result.status == "success"
        assert result.data == {"pods": 3}
        assert result.summary == "Found 3 pods"
        assert result.error_message is None
        assert result.raw_output_ref is None

    def test_error_result(self):
        result = ToolResult(
            status="error",
            data=None,
            summary="kubectl timed out",
            error_message="connection refused",
        )
        assert result.status == "error"
        assert result.error_message == "connection refused"

    def test_partial_result_rejected(self):
        with pytest.raises(ValidationError, match="status"):
            ToolResult(
                status="partial",
                data={"logs": ["line1"]},
                summary="Retrieved 1 of 5 log lines before timeout",
            )

    def test_raw_output_ref(self):
        result = ToolResult(
            status="success",
            data=None,
            summary="done",
            raw_output_ref="s3://bucket/output.json",
        )
        assert result.raw_output_ref == "s3://bucket/output.json"

    def test_data_accepts_any_type(self):
        for data in [None, 42, [1, 2], "text", {"nested": {"deep": True}}]:
            result = ToolResult(status="success", data=data, summary="ok")
            assert result.data == data


class TestToolResultValidation:
    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError, match="status"):
            ToolResult(status="running", data=None, summary="bad")

    def test_summary_max_length(self):
        with pytest.raises(ValidationError):
            ToolResult(status="success", data=None, summary="x" * 281)

    def test_summary_exactly_280_chars_accepted(self):
        result = ToolResult(status="success", data=None, summary="x" * 280)
        assert len(result.summary) == 280

    def test_empty_summary_accepted(self):
        result = ToolResult(status="success", data=None, summary="")
        assert result.summary == ""

    def test_status_must_be_string(self):
        with pytest.raises(ValidationError):
            ToolResult(status=123, data=None, summary="bad")


class TestToolResultSerialization:
    def test_model_dump_roundtrip(self):
        original = ToolResult(
            status="success",
            data={"key": "value"},
            summary="all good",
            error_message=None,
            raw_output_ref="ref-123",
        )
        dumped = original.model_dump()
        restored = ToolResult(**dumped)
        assert restored == original

    def test_model_dump_excludes_none_error_message(self):
        result = ToolResult(status="success", data={}, summary="ok")
        dumped = result.model_dump()
        assert "error_message" in dumped
        assert dumped["error_message"] is None

    def test_json_roundtrip(self):
        original = ToolResult(
            status="error",
            data={"code": 500},
            summary="server error",
            error_message="internal",
        )
        json_str = original.model_dump_json()
        restored = ToolResult.model_validate_json(json_str)
        assert restored == original


class TestToolResultEquality:
    def test_equal_instances(self):
        kwargs = {"status": "success", "data": [1], "summary": "x"}
        assert ToolResult(**kwargs) == ToolResult(**kwargs)

    def test_unequal_on_status(self):
        a = ToolResult(status="success", data=None, summary="x")
        b = ToolResult(status="error", data=None, summary="x")
        assert a != b
