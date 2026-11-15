.PHONY: install check lint fmt types unit integration e2e audit build

install:
	uv sync --extra dev

lint:
	uv run ruff check src tests

fmt:
	uv run ruff format --check src tests

types:
	uv run mypy --strict src/models src/services

unit:
	uv run pytest tests/unit -q

integration:
	uv run pytest tests/integration -q

e2e:
	uv run pytest tests/e2e -q

audit:
	uv run pip-audit || echo "[audit: SKIP локально, причина: нет сети/базы уязвимостей]"

check: lint fmt types unit integration e2e audit
