from __future__ import annotations

from pathlib import Path

import pytest

from src.models.chunk import Chunk, ParagraphSpan
from src.repositories.docx_loader import (
    DocxParagraphLoader,
    merge_adjacent,
    split_long_line,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "mini.docx"


def test_load_keeps_paragraph_spans() -> None:
    chunks = DocxParagraphLoader().load(FIXTURE)
    assert [c.span.start for c in chunks] == [1, 2, 3]
    assert [c.span.end for c in chunks] == [1, 2, 3]
    assert all(c.source == "mini.docx" for c in chunks)
    assert chunks[0].text == "Первый абзац."


def test_load_rejects_non_docx(tmp_path: Path) -> None:
    bad = tmp_path / "x.txt"
    bad.write_text("not a docx")
    with pytest.raises(ValueError, match=r"Ожидался .docx"):
        DocxParagraphLoader().load(bad)


def test_load_rejects_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        DocxParagraphLoader().load(tmp_path / "nope.docx")


def test_merge_adjacent_extends_span() -> None:
    chunks = [
        Chunk(source="a.docx", text="x", span=ParagraphSpan(start=1, end=1)),
        Chunk(source="a.docx", text="y", span=ParagraphSpan(start=2, end=2)),
        Chunk(source="a.docx", text="z", span=ParagraphSpan(start=4, end=4)),
    ]
    merged = merge_adjacent(chunks)
    assert len(merged) == 2
    assert merged[0].span.start == 1 and merged[0].span.end == 2
    assert merged[1].span.start == 4 and merged[1].span.end == 4


def test_split_short_line_returns_same() -> None:
    line = "Короткая строка."
    assert split_long_line(line) == [line]


def test_split_long_line_by_sentences() -> None:
    line = "Первое предложение про долги. Второе — про детей! Третье: алименты? " * 10
    parts = split_long_line(line, max_chars=200, overlap=20)
    assert len(parts) > 1
    for p in parts:
        assert len(p) <= 200 + 20  # перекрытие допускается
    assert any("дет" in p for p in parts)


def test_split_long_line_without_dots_uses_words() -> None:
    line = " ".join(["слово"] * 200)
    parts = split_long_line(line, max_chars=100, overlap=10)
    assert len(parts) > 1
    assert all(len(p) <= 150 for p in parts)


def test_split_respects_max_chars_at_least_once() -> None:
    line = "A" * 400
    parts = split_long_line(line, max_chars=100, overlap=10)
    assert len(parts) >= 4
