"""Тесты разбиения: паковка абзацев, резка длинных абзацев, адреса фрагментов."""

from __future__ import annotations

import pytest

from domain.models import Chunk
from infrastructure.loader import LoadedDocument
from infrastructure.splitter import Splitter, chunk_id, split_documents


def make_document(text: str, source: str = "doc.docx") -> LoadedDocument:
    return LoadedDocument(source=source, text=text, sha256="0" * 64)


def test_packs_short_paragraphs_into_one_chunk() -> None:
    document = make_document("Первый абзац.\n\nВторой абзац.")

    chunks = Splitter(chunk_size=200, chunk_overlap=0).split(document)

    assert len(chunks) == 1
    assert chunks[0].paragraph_start == 1
    assert chunks[0].paragraph_end == 2
    assert chunks[0].text == "Первый абзац.\n\nВторой абзац."


def test_starts_new_chunk_when_size_exceeded() -> None:
    document = make_document("А" * 60 + "\n\n" + "Б" * 60)

    chunks = Splitter(chunk_size=100, chunk_overlap=0).split(document)

    assert [chunk.paragraph_start for chunk in chunks] == [1, 2]
    assert all(len(chunk.text) <= 100 for chunk in chunks)


def test_splits_long_paragraph_with_overlap() -> None:
    document = make_document(" ".join(["слово"] * 60))

    chunks = Splitter(chunk_size=100, chunk_overlap=20).split(document)

    assert len(chunks) > 1
    assert {chunk.paragraph_start for chunk in chunks} == {1}
    assert {chunk.paragraph_end for chunk in chunks} == {1}
    assert all(len(chunk.text) <= 100 for chunk in chunks)


def test_paragraph_range_restarts_after_long_paragraph() -> None:
    """После разрезанного длинного абзаца адрес следующего фрагмента не наследует старый start."""
    document = make_document("А" * 60 + "\n\n" + " ".join(["слово"] * 40) + "\n\n" + "Б" * 60)

    chunks = Splitter(chunk_size=100, chunk_overlap=0).split(document)

    assert (chunks[0].paragraph_start, chunks[0].paragraph_end) == (1, 1)
    assert (chunks[-1].paragraph_start, chunks[-1].paragraph_end) == (3, 3)
    assert {(chunk.paragraph_start, chunk.paragraph_end) for chunk in chunks if chunk.text.startswith("слово")} == {
        (2, 2)
    }


def test_ids_and_order_are_sequential() -> None:
    document = make_document("А" * 60 + "\n\n" + "Б" * 60)

    chunks = Splitter(chunk_size=100, chunk_overlap=0).split(document)

    assert [chunk.order for chunk in chunks] == [0, 1]
    assert [chunk.id for chunk in chunks] == [chunk_id("doc.docx", 0), chunk_id("doc.docx", 1)]
    assert chunk_id("doc.docx", 7) == "doc.docx-0007"


def test_empty_document_raises() -> None:
    with pytest.raises(ValueError, match="не содержит текста"):
        Splitter(chunk_size=100, chunk_overlap=0).split(make_document("\n\n   \n\n"))


def test_split_documents_covers_every_source() -> None:
    documents = [make_document("Текст один.", source="a.docx"), make_document("Текст два.", source="b.docx")]

    chunks = split_documents(documents, chunk_size=200, chunk_overlap=0)

    assert isinstance(chunks[0], Chunk)
    assert [chunk.source for chunk in chunks] == ["a.docx", "b.docx"]
