from __future__ import annotations

from collections.abc import Callable
from typing import Any


class ToolRegistry:
    """Dynamic registry for investigation tools, designed for LangGraph integration."""

    def __init__(self) -> None:
        self._tools: dict[str, tuple[str, Callable[..., Any]]] = {}
        self._disabled_families: set[str] = set()

    def register(self, tool_name: str, tool_family: str, tool_func: Callable[..., Any]) -> None:
        """Register a tool function under *tool_name* in *tool_family*."""
        self._tools[tool_name] = (tool_family, tool_func)

    def get(self, tool_name: str) -> Callable[..., Any] | None:
        """Return the tool callable, or ``None`` if missing or disabled."""
        entry = self._tools.get(tool_name)
        if entry is None:
            return None
        family, func = entry
        if family in self._disabled_families:
            return None
        return func

    def names(self) -> list[str]:
        """Return names of all registered (non-disabled) tools."""
        return [name for name, (family, _) in self._tools.items() if family not in self._disabled_families]

    def families(self) -> list[str]:
        """Return all unique family names (regardless of disabled state)."""
        return list({family for family, _ in self._tools.values()})

    def disable_family(self, family: str) -> None:
        """Disable all tools in *family*.  No-op if family unknown."""
        self._disabled_families.add(family)

    def available_families(self) -> list[str]:
        """Return families that are NOT disabled."""
        all_families = {family for family, _ in self._tools.values()}
        return sorted(all_families - self._disabled_families)
