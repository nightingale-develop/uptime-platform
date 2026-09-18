FROM python:3.13-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./

RUN uv sync \
    --frozen \
    --no-dev \
    --no-install-project

COPY . .

RUN uv sync \
    --frozen \
    --no-dev


FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip uninstall -y pip

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/alembic.ini /app/alembic.ini
COPY --from=builder /app/migrations /app/migrations

LABEL org.opencontainers.image.title="Uptime Platform"
LABEL org.opencontainers.image.version="1.2.1"
LABEL org.opencontainers.image.description="Self-hosted uptime monitoring and incident management platform"
LABEL org.opencontainers.image.source="https://github.com/nightingale-develop/uptime-platform"

CMD ["fastapi", "run", "src/uptime_platform/main.py", "--host", "0.0.0.0", "--port", "8000"]
