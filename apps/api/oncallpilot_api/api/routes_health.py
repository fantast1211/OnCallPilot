"""Health and readiness endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz() -> dict[str, str]:
    from oncallpilot_api.config import load_settings

    try:
        load_settings()
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}
