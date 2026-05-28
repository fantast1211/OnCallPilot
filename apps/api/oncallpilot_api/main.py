"""FastAPI application entry point."""

from fastapi import FastAPI

from oncallpilot_api.api.routes_alerts import router as alerts_router
from oncallpilot_api.api.routes_chat import router as chat_router
from oncallpilot_api.api.routes_datasources import router as datasources_router
from oncallpilot_api.api.routes_events import router as events_router
from oncallpilot_api.api.routes_health import router as health_router
from oncallpilot_api.api.routes_incidents import router as incidents_router
from oncallpilot_api.api.routes_investigations import router as investigations_router


def create_app() -> FastAPI:
    app = FastAPI(title="OnCallPilot API", version="0.1.0")
    app.include_router(health_router)
    app.include_router(datasources_router)
    app.include_router(alerts_router)
    app.include_router(incidents_router)
    app.include_router(investigations_router)
    app.include_router(events_router)
    app.include_router(chat_router)
    return app
