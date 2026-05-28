"""arq worker entry point."""

from arq.connections import RedisSettings

from oncallpilot_api.config import load_settings


def _build_worker_settings():
    """Build WorkerSettings at import time with real config."""
    settings = load_settings()

    from oncallpilot_worker.jobs import run_investigation

    redis_url = settings.datasources.redis.url
    assert redis_url, "Redis URL must be configured for worker"

    class WorkerSettings:
        functions = [run_investigation]
        queue_name = settings.worker.arq.queue
        redis_settings = RedisSettings.from_dsn(redis_url)

    return WorkerSettings


WorkerSettings = _build_worker_settings()
