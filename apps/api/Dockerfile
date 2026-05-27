# ---- build stage ----
FROM python:3.12-slim AS builder

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
RUN uv sync --frozen --no-dev

COPY . .

# ---- runtime stage ----
FROM python:3.12-slim AS runtime

RUN groupadd --gid 1000 app && useradd --uid 1000 --gid app --create-home app

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/apps/api/oncallpilot_api /app/oncallpilot_api

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

USER app

EXPOSE 8080

CMD ["uvicorn", "oncallpilot_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
