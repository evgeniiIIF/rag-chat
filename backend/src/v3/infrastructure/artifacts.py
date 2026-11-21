"""Артефакты этапов: запись и чтение JSON/JSONL (`infrastructure/artifacts.py`).

Файлы нужны для разбора качества (User Story 3): чанки, выдача поиска, промпт, ответ модели.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from domain.models import Chunk


def write_json(path: Path, payload: object) -> None:
    """Записать один JSON-документ (UTF-8, без экранирования кириллицы)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    path.write_text(text + "\n", encoding="utf-8")


def write_jsonl(path: Path, items: Iterable[object]) -> None:
    """Записать последовательность объектов: по одному JSON на строку."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(item, ensure_ascii=False, default=str) for item in items]
    body = "\n".join(lines)
    path.write_text(body + "\n" if body else "", encoding="utf-8")


def read_json(path: Path) -> Any | None:
    """Прочитать JSON; отсутствующий файл — `None` (состояние «артефакта ещё нет»)."""
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Прочитать JSONL в список словарей; отсутствующий файл — пустой список."""
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row: dict[str, Any] = json.loads(line)
            rows.append(row)
    return rows


def write_chunks_markdown(chunks: Iterable[Chunk], path: Path) -> None:
    """Читаемый снимок нарезки: все фрагменты подряд, с адресом абзацев и размером.

    Машинный формат — `chunks.jsonl`, но глазами его не прочитать (кириллица экранирована),
    поэтому тот же список пишется в markdown. Файл обновляется при сборке индекса.
    """
    blocks = [
        f"## {chunk.id}\n\n"
        f"- источник: {chunk.source}\n"
        f"- абзацы: {chunk.paragraph_start}-{chunk.paragraph_end}\n"
        f"- символов: {len(chunk.text)}\n\n"
        f"{chunk.text}\n"
        for chunk in chunks
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n---\n\n".join(blocks), encoding="utf-8")
