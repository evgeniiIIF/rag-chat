"""Доменная модель чанка: текст + место в исходном документе."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ParagraphSpan(BaseModel):
    """Диапазон абзацев [start, end] в исходном документе (1-based)."""

    start: int = Field(..., ge=1)
    end: int = Field(..., ge=1)


class Chunk(BaseModel):
    """Единица контекста для retrieval и цитирования."""

    source: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)
    span: ParagraphSpan
