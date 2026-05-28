from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    """Unified result returned by every investigation tool."""

    status: Literal["success", "error", "partial"]
    data: Any
    summary: str = Field(max_length=280)
    error_message: Optional[str] = None
    raw_output_ref: Optional[str] = None
