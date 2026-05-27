"""Tests for /healthz and /readyz endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from oncallpilot_api.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_healthz_returns_ok(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readyz_returns_config_status(client):
    resp = await client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert "status" in body
