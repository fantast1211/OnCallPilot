"""Tests for dependency injection helpers."""

import textwrap
from pathlib import Path

import pytest

from oncallpilot_api.dependencies import get_config, get_settings


MINIMAL_YAML = textwrap.dedent("""\
    app:
      log_level: info
      api:
        host: "0.0.0.0"
        port: 8080
    datasources:
      postgres:
        url_env: TEST_PG_URL
      redis:
        url_env: TEST_REDIS_URL
      prometheus:
        url: "http://prometheus:9090"
      loki:
        url: "http://loki:3100"
    llm:
      base_url: "https://api.openai.com/v1"
      api_key_env: TEST_LLM_KEY
      model: "gpt-4.1"
    agent:
      max_tool_steps: 10
      hard_step_cap: 20
      tool_failure_disable_threshold: 3
    worker:
      arq:
        queue: "oncallpilot:jobs"
        job_timeout_seconds: 600
        max_jobs: 10
""")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ("TEST_PG_URL", "TEST_REDIS_URL", "TEST_LLM_KEY", "ONCALLPILOT_CONFIG"):
        monkeypatch.delenv(key, raising=False)
    # Clear lru_cache between tests
    get_settings.cache_clear()


@pytest.fixture
def config_file(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(MINIMAL_YAML)
    return p


def test_get_settings_returns_settings(config_file, monkeypatch):
    monkeypatch.setenv("TEST_PG_URL", "postgresql+asyncpg://u:p@db:5432/app")
    monkeypatch.setenv("TEST_REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("TEST_LLM_KEY", "sk-test")
    monkeypatch.setenv("ONCALLPILOT_CONFIG", str(config_file))

    settings = get_settings()
    assert settings.app.log_level == "info"


def test_get_config_returns_settings(config_file, monkeypatch):
    monkeypatch.setenv("TEST_PG_URL", "postgresql+asyncpg://u:p@db:5432/app")
    monkeypatch.setenv("TEST_REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("TEST_LLM_KEY", "sk-test")
    monkeypatch.setenv("ONCALLPILOT_CONFIG", str(config_file))

    settings = get_settings()
    result = get_config(settings)
    assert result is settings
