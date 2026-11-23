# Прод-сборка v3 (LangGraph RAG): самостоятельный uv-проект в src/v3.
# Контекст сборки — ./backend (см. docker-compose.prod.yml).
FROM python:3.12-slim AS build
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /uvx /usr/local/bin/
COPY src/v3/pyproject.toml src/v3/uv.lock ./
# hatchling собирает пакет `core`, поэтому он нужен до uv sync
COPY src/v3/core ./core
RUN uv sync --frozen --no-dev || uv sync --no-dev

FROM python:3.12-slim AS runtime
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -u 10001 -m app
COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
COPY src/v3/main.py ./
COPY src/v3/api ./api
COPY src/v3/core ./core
COPY src/v3/domain ./domain
COPY src/v3/graph ./graph
COPY src/v3/infrastructure ./infrastructure
COPY src/v3/schemas ./schemas
COPY src/v3/services ./services
RUN mkdir -p /app/data /app/artifacts /app/.chroma && chown -R app:app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=10 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=5)" || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
