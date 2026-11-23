"""Тесты доменных моделей: инварианты Chunk и RetrievedChunk."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.models import Chunk, RetrievedChunk


def make_chunk(**overrides: object) -> Chunk:
    params: dict[str, object] = {
        "id": "doc.docx-0000",
        "source": "doc.docx",
        "order": 0,
        "paragraph_start": 1,
        "paragraph_end": 3,
        "text": "В процедуру берём с суммой от 350 000 рублей.",
    }
    params.update(overrides)
    return Chunk(**params)  # type: ignore[arg-type]


def test_chunk_builds_and_is_frozen() -> None:
    chunk = make_chunk()

    assert chunk.id == "doc.docx-0000"
    assert chunk.paragraph_end - chunk.paragraph_start == 2
    with pytest.raises(ValidationError):
        chunk.text = "другое"


def test_chunk_rejects_id_not_matching_source_and_order() -> None:
    with pytest.raises(ValidationError):
        make_chunk(id="doc.docx-0001")


def test_chunk_rejects_reversed_paragraphs() -> None:
    with pytest.raises(ValidationError):
        make_chunk(paragraph_start=5, paragraph_end=2)


def test_chunk_rejects_empty_text() -> None:
    with pytest.raises(ValidationError):
        make_chunk(text="")


def test_retrieved_chunk_bounds() -> None:
    chunk = make_chunk()
    retrieved = RetrievedChunk(chunk=chunk, score=0.5, rank=1)

    assert retrieved.chunk.id == chunk.id
    with pytest.raises(ValidationError):
        RetrievedChunk(chunk=chunk, score=1.5, rank=1)
    with pytest.raises(ValidationError):
        RetrievedChunk(chunk=chunk, score=0.5, rank=0)
