# ---- build stage ----
FROM python:3.12-slim AS builder

WORKDIR /app

RUN pip install --no-cache-dir uv

# copy workspace manifests (build context = repo root)
COPY apps/worker/pyproject.toml ./apps/worker/
COPY apps/api/pyproject.toml ./apps/api/

WORKDIR /app/apps/worker
RUN uv sync --frozen --no-dev

# ---- runtime stage ----
FROM python:3.12-slim AS runtime

RUN groupadd --gid 1000 app && useradd --uid 1000 --gid app --create-home app

WORKDIR /app

COPY --from=builder /app/apps/worker/.venv /app/.venv

COPY apps/worker/oncallpilot_worker /app/oncallpilot_worker
COPY apps/api/oncallpilot_api /app/oncallpilot_api

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app"

USER app

CMD ["arq", "oncallpilot_worker.main.WorkerSettings"]
