"""Verify arq worker wiring — job function and WorkerSettings."""

from __future__ import annotations

import inspect
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture()
def _config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "app:\n"
        "  log_level: info\n"
        "datasources:\n"
        "  postgres:\n"
        '    url: "postgresql+asyncpg://test:test@localhost:5432/test"\n'
        "  redis:\n"
        '    url: "redis://localhost:6379"\n'
        "  prometheus:\n"
        '    url: "http://localhost:9090"\n'
        "  loki:\n"
        '    url: "http://localhost:3100"\n'
        "llm:\n"
        '  base_url: "https://api.openai.com/v1"\n'
        '  api_key: "sk-test"\n'
        '  model: "gpt-4.1"\n'
        "worker:\n"
        "  arq:\n"
        '    queue: "oncallpilot:jobs"\n'
    )
    monkeypatch.setenv("ONCALLPILOT_CONFIG", str(cfg))
    return cfg


@pytest.fixture(autouse=True)
def _clean_imports() -> None:
    for mod_name in (
        "oncallpilot_worker.main",
        "oncallpilot_worker.jobs",
    ):
        sys.modules.pop(mod_name, None)


def test_run_investigation_is_async_callable(_config_file: Path) -> None:
    from oncallpilot_worker.jobs import run_investigation

    assert callable(run_investigation)
    assert inspect.iscoroutinefunction(run_investigation)


def test_worker_settings_has_correct_attributes(_config_file: Path) -> None:
    from oncallpilot_worker.main import WorkerSettings

    assert WorkerSettings.queue_name == "oncallpilot:jobs"
    assert len(WorkerSettings.functions) == 1
    assert WorkerSettings.functions[0].__name__ == "run_investigation"


def test_run_investigation_accepts_session_id_string(_config_file: Path) -> None:
    from oncallpilot_worker.jobs import run_investigation

    sig = inspect.signature(run_investigation)
    params = list(sig.parameters.keys())
    assert params[0] == "ctx"
    assert params[1] == "session_id"


@pytest.mark.asyncio
async def test_run_investigation_state_transitions(_config_file: Path) -> None:
    """Verify the state machine transitions: pending -> running -> completed."""
    session_id = str(uuid.uuid4())

    mock_session = MagicMock()
    mock_session.id = uuid.UUID(session_id)
    mock_session.status = "pending"

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_session)
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock(return_value=mock_db)

    mock_event_bus = AsyncMock()

    with (
        patch("oncallpilot_worker.jobs._make_session_factory", return_value=mock_factory),
        patch("oncallpilot_worker.jobs._make_event_bus", return_value=mock_event_bus),
        patch("oncallpilot_worker.jobs.asyncio.sleep", new_callable=AsyncMock),
    ):
        from oncallpilot_worker.jobs import run_investigation

        await run_investigation({}, session_id)

    assert mock_db.commit.call_count == 2

    publish_calls = mock_event_bus.publish.call_args_list
    assert len(publish_calls) == 2

    first_channel, first_event = publish_calls[0][0][0], publish_calls[0][0][1]
    assert f"investigation:{session_id}" in first_channel
    assert first_event["type"] == "session.started"

    second_channel, second_event = publish_calls[1][0][0], publish_calls[1][0][1]
    assert f"investigation:{session_id}" in second_channel
    assert second_event["type"] == "session.completed"
    assert second_event["verdict"] == "healthy"
    assert second_event["confidence"] == 1.0
