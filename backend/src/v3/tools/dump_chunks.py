"""Снимок нарезки для чтения глазами: artifacts/index/chunks.jsonl -> docs/chunks.md.

Нарезка уже лежит в JSONL, но это машинный формат (кириллица в \\uXXXX, вся нарезка
одной строкой файла). Здесь она переписывается в один читаемый файл: все фрагменты
целиком, каждый с id, источником, адресом абзацев и размером.

Обычно файл обновляет сам сервис при старте; эта команда нужна, чтобы пересобрать
снимок без запуска индекса (например, посмотреть старую нарезку).

Запуск: `uv run python tools/dump_chunks.py` или `make chunks`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from domain.models import Chunk
from infrastructure.artifacts import write_chunks_markdown

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "artifacts" / "index" / "chunks.jsonl"
DEFAULT_TARGET = ROOT.parents[2] / "docs" / "chunks.md"


def load_chunks(path: Path) -> list[Chunk]:
    """Фрагменты из chunks.jsonl (та же модель, что и в индексе)."""
    if not path.is_file():
        raise SystemExit(f"нет файла нарезки: {path} (сначала постройте индекс)")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [Chunk.model_validate(row) for row in rows]


def dump(source: Path, target: Path) -> int:
    """Переписать нарезку в читаемый target; вернуть число фрагментов."""
    chunks = load_chunks(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    write_chunks_markdown(chunks, target)
    return len(chunks)


def main() -> None:
    parser = argparse.ArgumentParser(description="Снимок нарезки в читаемом виде")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    args = parser.parse_args()
    total = dump(args.source, args.target)
    print(f"{args.target}: {total} фрагментов")


if __name__ == "__main__":
    main()
