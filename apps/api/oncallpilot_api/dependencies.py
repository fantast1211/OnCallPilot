"""FastAPI dependency injection for config and services."""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends

from oncallpilot_api.config import Settings, load_settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


def get_config(settings: Settings = Depends(get_settings)) -> Settings:
    return settings
