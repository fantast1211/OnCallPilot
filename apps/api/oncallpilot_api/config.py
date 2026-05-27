"""YAML-based configuration loader using pydantic-settings."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, HttpUrl, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource


# ---------------------------------------------------------------------------
# Nested models
# ---------------------------------------------------------------------------


class ApiConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080


class AppConfig(BaseModel):
    log_level: str = "info"
    api: ApiConfig = ApiConfig()


class PostgresDatasource(BaseModel):
    url_env: str | None = None
    url: str | None = None

    @model_validator(mode="before")
    @classmethod
    def resolve_env(cls, data: Any) -> Any:
        if isinstance(data, dict):
            env_key = data.get("url_env")
            if env_key:
                val = os.environ.get(env_key)
                if not val:
                    raise ValueError(f"Environment variable '{env_key}' is not set")
                data["url"] = val
        return data


class RedisDatasource(BaseModel):
    url_env: str | None = None
    url: str | None = None

    @model_validator(mode="before")
    @classmethod
    def resolve_env(cls, data: Any) -> Any:
        if isinstance(data, dict):
            env_key = data.get("url_env")
            if env_key:
                val = os.environ.get(env_key)
                if not val:
                    raise ValueError(f"Environment variable '{env_key}' is not set")
                data["url"] = val
        return data


class SimpleDatasource(BaseModel):
    url: str


class DatasourcesConfig(BaseModel):
    postgres: PostgresDatasource
    redis: RedisDatasource
    prometheus: SimpleDatasource
    loki: SimpleDatasource


class LlmConfig(BaseModel):
    base_url: str = "https://api.openai.com/v1"
    api_key_env: str | None = None
    api_key: str | None = None
    model: str = "gpt-4.1"

    @model_validator(mode="before")
    @classmethod
    def resolve_api_key_env(cls, data: Any) -> Any:
        if isinstance(data, dict):
            env_key = data.get("api_key_env")
            if env_key:
                val = os.environ.get(env_key)
                if not val:
                    raise ValueError(f"Environment variable '{env_key}' is not set")
                data["api_key"] = val
        return data


class AgentConfig(BaseModel):
    max_tool_steps: int = 10
    hard_step_cap: int = 20
    tool_failure_disable_threshold: int = 3


class ArqWorkerConfig(BaseModel):
    queue: str = "oncallpilot:jobs"
    job_timeout_seconds: int = 600
    max_jobs: int = 10


class WorkerConfig(BaseModel):
    arq: ArqWorkerConfig = ArqWorkerConfig()


# ---------------------------------------------------------------------------
# Root settings
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    app: AppConfig = AppConfig()
    datasources: DatasourcesConfig
    llm: LlmConfig
    agent: AgentConfig = AgentConfig()
    worker: WorkerConfig = WorkerConfig()

    model_config = {"env_prefix": "ONCALLPILOT_"}

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        **kwargs: Any,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (YamlConfigSettingsSource(settings_cls),)


# ---------------------------------------------------------------------------
# YAML settings source (~50 lines as specified)
# ---------------------------------------------------------------------------


class YamlConfigSettingsSource(PydanticBaseSettingsSource):
    """Read settings from the YAML file pointed to by ONCALLPILOT_CONFIG."""

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        self._yaml_path: Path | None = None
        raw = os.environ.get("ONCALLPILOT_CONFIG")
        if raw:
            self._yaml_path = Path(raw).expanduser().resolve()

    def get_field_value(self, field: Any) -> tuple[Any, str, bool]:
        return (None, "", False)

    def __call__(self) -> dict[str, Any]:
        if self._yaml_path is None:
            raise FileNotFoundError(
                "ONCALLPILOT_CONFIG environment variable is not set. "
                "Point it to a YAML config file."
            )
        if not self._yaml_path.is_file():
            raise FileNotFoundError(
                f"Config file not found: {self._yaml_path}"
            )
        with self._yaml_path.open() as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            raise ValueError(f"Config file must contain a YAML mapping, got {type(data).__name__}")
        return data


# ---------------------------------------------------------------------------
# Loader helper
# ---------------------------------------------------------------------------


def load_settings() -> Settings:
    """Load and validate settings from the YAML config file."""
    try:
        return Settings()
    except Exception:
        raise
