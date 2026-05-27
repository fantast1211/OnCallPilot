"""Tests for YAML config loader."""

import os
import textwrap
from pathlib import Path

import pytest

from oncallpilot_api.config import Settings, load_settings


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
    """Ensure env vars don't leak between tests."""
    for key in ("TEST_PG_URL", "TEST_REDIS_URL", "TEST_LLM_KEY", "ONCALLPILOT_CONFIG"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def config_file(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(MINIMAL_YAML)
    return p


def test_load_settings_from_yaml(config_file, monkeypatch):
    monkeypatch.setenv("TEST_PG_URL", "postgresql+asyncpg://u:p@db:5432/app")
    monkeypatch.setenv("TEST_REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("TEST_LLM_KEY", "sk-test")
    monkeypatch.setenv("ONCALLPILOT_CONFIG", str(config_file))

    settings = load_settings()

    assert isinstance(settings, Settings)
    assert settings.app.log_level == "info"
    assert settings.app.api.port == 8080
    assert str(settings.datasources.postgres.url) == "postgresql+asyncpg://u:p@db:5432/app"
    assert str(settings.datasources.redis.url) == "redis://redis:6379/0"
    assert settings.llm.api_key == "sk-test"
    assert settings.llm.model == "gpt-4.1"
    assert settings.agent.max_tool_steps == 10
    assert settings.worker.arq.queue == "oncallpilot:jobs"


def test_env_resolution(config_file, monkeypatch):
    monkeypatch.setenv("TEST_PG_URL", "postgresql+asyncpg://u:p@db:5432/app")
    monkeypatch.setenv("TEST_REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("TEST_LLM_KEY", "sk-real-key")
    monkeypatch.setenv("ONCALLPILOT_CONFIG", str(config_file))

    settings = load_settings()
    assert settings.llm.api_key == "sk-real-key"


def test_missing_env_var_fails(config_file, monkeypatch):
    """If an *_env field references a missing env var, loading must fail."""
    monkeypatch.setenv("TEST_PG_URL", "postgresql+asyncpg://u:p@db:5432/app")
    monkeypatch.setenv("TEST_REDIS_URL", "redis://redis:6379/0")
    # TEST_LLM_KEY deliberately not set
    monkeypatch.setenv("ONCALLPILOT_CONFIG", str(config_file))

    with pytest.raises(Exception):
        load_settings()


def test_missing_config_file():
    os.environ.pop("ONCALLPILOT_CONFIG", None)
    with pytest.raises(Exception):
        load_settings()


def test_defaults_applied(config_file, monkeypatch):
    monkeypatch.setenv("TEST_PG_URL", "postgresql+asyncpg://u:p@db:5432/app")
    monkeypatch.setenv("TEST_REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("TEST_LLM_KEY", "sk-test")
    monkeypatch.setenv("ONCALLPILOT_CONFIG", str(config_file))

    settings = load_settings()
    assert settings.app.log_level == "info"
    assert settings.agent.hard_step_cap == 20
