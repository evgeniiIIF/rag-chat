.PHONY: check lint fmt-check types test chunks

check: lint fmt-check types test

lint:
	uv run ruff check .

fmt-check:
	uv run ruff format --check .

types:
	uv run mypy

test:
	uv run pytest \
		--cov=core --cov=domain --cov=infrastructure --cov=graph --cov=services \
		--cov=schemas --cov=api --cov=main \
		--cov-report=term-missing --cov-fail-under=80

# читаемый снимок нарезки: artifacts/index/chunks.jsonl -> chunks/
chunks:
	uv run python tools/dump_chunks.py
