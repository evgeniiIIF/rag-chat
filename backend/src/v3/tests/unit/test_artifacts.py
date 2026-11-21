"""Тесты артефактов: JSON/JSONL пишутся и читаются без потерь."""

from __future__ import annotations

from pathlib import Path

from domain.models import Chunk
from infrastructure.artifacts import (
    read_json,
    read_jsonl,
    write_chunks_markdown,
    write_json,
    write_jsonl,
)


def test_write_json_creates_parents_and_reads_back(tmp_path: Path) -> None:
    path = tmp_path / "request" / "answer.json"

    write_json(path, {"answer": "От 350 000 рублей.", "grounded": True})

    assert read_json(path) == {"answer": "От 350 000 рублей.", "grounded": True}
    assert "От 350" in path.read_text(encoding="utf-8")


def test_read_json_missing_returns_none(tmp_path: Path) -> None:
    assert read_json(tmp_path / "нет.json") is None


def test_jsonl_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "index" / "chunks.jsonl"

    write_jsonl(path, [{"id": "a-0000"}, {"id": "a-0001"}])

    assert read_jsonl(path) == [{"id": "a-0000"}, {"id": "a-0001"}]


def test_jsonl_empty_and_missing(tmp_path: Path) -> None:
    path = tmp_path / "empty.jsonl"

    write_jsonl(path, [])

    assert path.read_text(encoding="utf-8") == ""
    assert read_jsonl(path) == []
    assert read_jsonl(tmp_path / "нет.jsonl") == []
    assert read_jsonl(tmp_path / "нет.jsonl") == []


def test_write_chunks_markdown_is_readable(tmp_path: Path) -> None:
    """Снимок нарезки: каждый фрагмент с адресом абзацев и полным текстом."""
    chunks = [
        Chunk(id="d.docx-0000", source="d.docx", order=0, paragraph_start=1, paragraph_end=2, text="Первый абзац."),
        Chunk(id="d.docx-0001", source="d.docx", order=1, paragraph_start=3, paragraph_end=3, text="Второй абзац."),
    ]
    path = tmp_path / "chunks" / "chunks.md"

    write_chunks_markdown(chunks, path)

    text = path.read_text(encoding="utf-8")
    assert text.count("## d.docx-") == 2
    assert "- абзацы: 1-2" in text
    assert "- символов: 13" in text
    assert "Первый абзац." in text
    assert text.rstrip().endswith("Второй абзац.")
