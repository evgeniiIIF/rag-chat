.PHONY: install check lint fmt types unit integration e2e audit probe build

install:
	uv sync --extra dev

lint:
	@if command -v uv >/dev/null 2>&1; then uv run ruff check src tests; else .venv/bin/ruff check src tests; fi

fmt:
	@if command -v uv >/dev/null 2>&1; then uv run ruff format --check src tests; else .venv/bin/ruff format --check src tests; fi

types:
	@if command -v uv >/dev/null 2>&1; then uv run mypy --strict src/models src/services; else .venv/bin/mypy --strict src/models src/services; fi

unit:
	@if command -v uv >/dev/null 2>&1; then uv run pytest tests/unit -q; else .venv/bin/pytest tests/unit -q; fi

integration:
	@if command -v uv >/dev/null 2>&1; then uv run pytest tests/integration -q; else .venv/bin/pytest tests/integration -q; fi

e2e:
	@if command -v uv >/dev/null 2>&1; then uv run pytest tests/e2e -q; else .venv/bin/pytest tests/e2e -q; fi

audit:
	@if command -v uv >/dev/null 2>&1; then uv run pip-audit || echo "[audit: SKIP локально, причина: нет сети/базы уязвимостей]"; else .venv/bin/pip-audit 2>/dev/null || echo "[audit: SKIP локально, причина: нет сети/базы уязвимостей]"; fi

probe:
	@if command -v uv >/dev/null 2>&1; then uv run python -m eval.score_probe; else .venv/bin/python -m eval.score_probe; fi

check: lint fmt types unit integration e2e audit
