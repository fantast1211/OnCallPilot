from __future__ import annotations

import pytest

from oncallpilot_api.tools.registry import ToolRegistry


def _noop():
    return None


def _noop2():
    return None


class TestRegisterAndGet:
    def test_register_and_get(self):
        reg = ToolRegistry()
        reg.register("kubectl_get_pods", "kubectl", _noop)
        assert reg.get("kubectl_get_pods") is _noop

    def test_get_unknown_returns_none(self):
        reg = ToolRegistry()
        assert reg.get("nonexistent") is None

    def test_register_overwrites_existing(self):
        reg = ToolRegistry()
        reg.register("tool_a", "fam", _noop)
        reg.register("tool_a", "fam", _noop2)
        assert reg.get("tool_a") is _noop2

    def test_multiple_tools(self):
        reg = ToolRegistry()
        reg.register("a", "f1", _noop)
        reg.register("b", "f2", _noop2)
        assert reg.get("a") is _noop
        assert reg.get("b") is _noop2


class TestNames:
    def test_empty_registry(self):
        reg = ToolRegistry()
        assert reg.names() == []

    def test_lists_all_names(self):
        reg = ToolRegistry()
        reg.register("alpha", "f", _noop)
        reg.register("beta", "f", _noop)
        assert sorted(reg.names()) == ["alpha", "beta"]

    def test_names_excludes_disabled(self):
        reg = ToolRegistry()
        reg.register("a", "fam", _noop)
        reg.disable_family("fam")
        assert reg.names() == []


class TestFamilies:
    def test_empty_registry(self):
        reg = ToolRegistry()
        assert reg.families() == []

    def test_lists_unique_families(self):
        reg = ToolRegistry()
        reg.register("a", "kubectl", _noop)
        reg.register("b", "kubectl", _noop)
        reg.register("c", "loki", _noop)
        assert sorted(reg.families()) == ["kubectl", "loki"]


class TestDisableFamily:
    def test_disable_removes_family_from_available(self):
        reg = ToolRegistry()
        reg.register("a", "kubectl", _noop)
        reg.disable_family("kubectl")
        assert "kubectl" not in reg.available_families()

    def test_disable_makes_tools_inaccessible(self):
        reg = ToolRegistry()
        reg.register("a", "kubectl", _noop)
        reg.disable_family("kubectl")
        assert reg.get("a") is None

    def test_disable_nonexistent_family_no_error(self):
        reg = ToolRegistry()
        reg.disable_family("nope")  # should not raise

    def test_disable_preserves_other_families(self):
        reg = ToolRegistry()
        reg.register("a", "kubectl", _noop)
        reg.register("b", "loki", _noop)
        reg.disable_family("kubectl")
        assert reg.get("b") is _noop
        assert sorted(reg.available_families()) == ["loki"]

    def test_disable_only_affects_names_for_that_family(self):
        reg = ToolRegistry()
        reg.register("a", "kubectl", _noop)
        reg.register("b", "loki", _noop)
        reg.disable_family("kubectl")
        assert reg.names() == ["b"]


class TestAvailableFamilies:
    def test_empty_registry(self):
        reg = ToolRegistry()
        assert reg.available_families() == []

    def test_all_available_initially(self):
        reg = ToolRegistry()
        reg.register("a", "kubectl", _noop)
        reg.register("b", "loki", _noop)
        assert sorted(reg.available_families()) == ["kubectl", "loki"]

    def test_available_after_disable(self):
        reg = ToolRegistry()
        reg.register("a", "kubectl", _noop)
        reg.register("b", "loki", _noop)
        reg.disable_family("kubectl")
        assert reg.available_families() == ["loki"]
