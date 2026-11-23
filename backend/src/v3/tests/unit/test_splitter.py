"""Тесты нарезки: один абзац — один фрагмент, список идёт с заголовком, абзацы не режутся."""

from __future__ import annotations

import pytest

from domain.models import Chunk
from infrastructure.loader import LoadedDocument
from infrastructure.splitter import Splitter, chunk_id, split_documents


def make_document(text: str, source: str = "doc.docx") -> LoadedDocument:
    return LoadedDocument(source=source, text=text, sha256="0" * 64)


def test_every_paragraph_is_a_whole_chunk() -> None:
    document = make_document("Первый абзац.\n\nВторой абзац.")

    chunks = Splitter().split(document)

    assert [chunk.text for chunk in chunks] == ["Первый абзац.", "Второй абзац."]
    assert [(chunk.paragraph_start, chunk.paragraph_end) for chunk in chunks] == [(1, 1), (2, 2)]


def test_long_paragraph_is_not_cut() -> None:
    long_paragraph = " ".join(["слово"] * 200)
    document = make_document(long_paragraph)

    chunks = Splitter().split(document)

    assert len(chunks) == 1
    assert chunks[0].text == long_paragraph
    assert len(chunks[0].text) > 200


def test_list_goes_with_its_heading() -> None:
    document = make_document(
        "На консультации важно держать фокус на нескольких вещах:\n\nкакие долги есть и перед кем;\n\n"
        "есть ли имущество, ипотека, залог;"
    )

    chunks = Splitter().split(document)

    assert len(chunks) == 1
    assert chunks[0].paragraph_start == 1
    assert chunks[0].paragraph_end == 3
    assert chunks[0].text.startswith("На консультации важно")
    assert "какие долги есть и перед кем;" in chunks[0].text
    assert "есть ли имущество, ипотека, залог;" in chunks[0].text


def test_heading_without_items_stays_alone() -> None:
    document = make_document(
        "Что важно знать:\n\nАбзац с длинным текстом, который уже не пункт списка, а обычная мысль."
    )

    chunks = Splitter().split(document)

    assert [chunk.text for chunk in chunks] == [
        "Что важно знать:",
        "Абзац с длинным текстом, который уже не пункт списка, а обычная мысль.",
    ]


def test_ids_and_order_are_sequential() -> None:
    document = make_document("Первый.\n\nВторой.\n\nТретий.")

    chunks = Splitter().split(document)

    assert [chunk.order for chunk in chunks] == [0, 1, 2]
    assert [chunk.id for chunk in chunks] == [chunk_id("doc.docx", index) for index in range(3)]
    assert chunk_id("doc.docx", 7) == "doc.docx-0007"


def test_empty_document_raises() -> None:
    with pytest.raises(ValueError, match="не содержит текста"):
        Splitter().split(make_document("\n\n   \n\n"))


def test_split_documents_covers_every_source() -> None:
    documents = [make_document("Текст один.", source="a.docx"), make_document("Текст два.", source="b.docx")]

    chunks = split_documents(documents)

    assert isinstance(chunks[0], Chunk)
    assert [chunk.source for chunk in chunks] == ["a.docx", "b.docx"]
