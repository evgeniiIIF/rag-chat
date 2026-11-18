#!/usr/bin/env bash
# One-command RAGAS run: ensures the API is up, then evaluates the golden set.
# Usage: ./ragas.sh [--no-serve]   (--no-serve = fail instead of docker compose up)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

START=1
for arg in "$@"; do
  [[ "$arg" == "--no-serve" ]] && START=0
done

# 1. env: judge LLM credentials come from the same .env as the backend
env_get() { [[ -f .env ]] && grep -E "^$1=" .env | tail -1 | cut -d= -f2- | tr -d "\"'\r" || true; }
export OPENAI_API_KEY="${OPENAI_API_KEY:-$(env_get BACKEND_API_KEY)}"
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-$(env_get BACKEND_BASE_URL)}"
[[ -n "$OPENAI_API_KEY" ]] || { echo "✗ Нет BACKEND_API_KEY в .env"; exit 1; }
[[ -n "$OPENAI_BASE_URL" ]] || export OPENAI_BASE_URL="https://polza.ai/api/v1"

PORT="${NGINX_HTTP_PORT:-$(env_get NGINX_HTTP_PORT)}"; PORT="${PORT:-8081}"
HEALTH="http://localhost:${PORT}/api/health"

# 2. API must be alive, otherwise we would score the "Не знаю" fallback
if ! curl -sf -m 5 "$HEALTH" >/dev/null; then
  [[ "$START" == 1 ]] || { echo "✗ API на $HEALTH недоступен"; exit 1; }
  echo "▶ Backend не запущен — поднимаю docker compose (первый старт ~1.5–2 мин, индекс)..."
  docker compose up -d --build
  echo -n "⏳ Жду готовности индекса "
  for _ in $(seq 1 120); do
    if curl -sf -m 5 "$HEALTH" >/dev/null; then echo " ✓"; break; fi
    echo -n "."; sleep 5
  done
  curl -sf -m 5 "$HEALTH" >/dev/null || { echo "✗ Таймаут: API так и не поднялся (смотри: docker compose logs -f backend)"; exit 1; }
fi

# 3. run ragas with the already-installed venv (uv not required)
PY="eval/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  command -v uv >/dev/null 2>&1 || { echo "✗ Нет eval/.venv и нет uv. Собери окружение: cd eval && uv sync"; exit 1; }
  (cd eval && uv run python ../backend/eval/run_ragas.py)
else
  "$PY" backend/eval/run_ragas.py
fi
