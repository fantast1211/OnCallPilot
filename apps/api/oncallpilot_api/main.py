"""FastAPI application entry point."""

from fastapi import FastAPI

from oncallpilot_api.api.routes_health import router as health_router
from oncallpilot_api.api.routes_datasources import router as datasources_router


def create_app() -> FastAPI:
    app = FastAPI(title="OnCallPilot API", version="0.1.0")
    app.include_router(health_router)
    app.include_router(datasources_router)
    return app
