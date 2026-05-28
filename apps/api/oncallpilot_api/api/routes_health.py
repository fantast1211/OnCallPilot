"""Health and readiness endpoints."""

from fastapi import APIRouter, Response

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(response: Response) -> dict[str, str]:
    from oncallpilot_api.config import load_settings

    try:
        load_settings()
        return {"status": "ok"}
    except Exception as exc:
        response.status_code = 503
        return {"status": "error", "detail": str(exc)}
