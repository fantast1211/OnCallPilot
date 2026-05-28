"""Tests for /healthz and /readyz endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient


MINIMAL_VALID_YAML = (
    "app:\n"
    "  log_level: info\n"
    "datasources:\n"
    "  postgres:\n"
    '    url: "sqlite+aiosqlite://"\n'
    "  redis:\n"
    '    url: "redis://localhost"\n'
    "  prometheus:\n"
    '    url: "http://localhost:9090"\n'
    "  loki:\n"
    '    url: "http://localhost:3100"\n'
    "llm:\n"
    '  api_key: "test-key"\n'
    '  model: "gpt-4.1"\n'
)


@pytest.fixture
def configured_env(tmp_path, monkeypatch):
    cfg = tmp_path / "oncallpilot.yaml"
    cfg.write_text(MINIMAL_VALID_YAML)
    monkeypatch.setenv("ONCALLPILOT_CONFIG", str(cfg))


@pytest.fixture
def app(configured_env):
    from oncallpilot_api.main import create_app
    from oncallpilot_api.dependencies import get_settings
    get_settings.cache_clear()
    yield create_app()
    get_settings.cache_clear()


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
async def test_readyz_returns_ok_when_config_valid(client):
    resp = await client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


@pytest.mark.asyncio
async def test_readyz_returns_503_when_config_missing(monkeypatch):
    monkeypatch.delenv("ONCALLPILOT_CONFIG", raising=False)
    from oncallpilot_api.dependencies import get_settings
    get_settings.cache_clear()
    from oncallpilot_api.main import create_app
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/readyz")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "error"
    get_settings.cache_clear()
