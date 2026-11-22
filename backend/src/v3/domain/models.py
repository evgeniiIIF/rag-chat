"""Доменные модели: фрагмент документа и попадание в выдачу поиска. Логики здесь нет."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Chunk(BaseModel):
    """Фрагмент документа: адрес в источнике + текст."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    order: int = Field(ge=0)
    paragraph_start: int = Field(ge=1)
    paragraph_end: int = Field(ge=1)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_invariants(self) -> Self:
        if self.paragraph_start > self.paragraph_end:
            raise ValueError("paragraph_start не может быть больше paragraph_end")
        expected = f"{self.source}-{self.order:04d}"
        if self.id != expected:
            raise ValueError(f"id должен быть '{expected}'")
        return self


class RetrievedChunk(BaseModel):
    """Фрагмент, попавший в выдачу поиска."""

    model_config = ConfigDict(frozen=True)

    chunk: Chunk
    score: float = Field(ge=0.0, le=1.0)
    rank: int = Field(ge=1)
