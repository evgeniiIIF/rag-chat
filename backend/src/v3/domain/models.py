"""Доменные модели v3: фрагмент документа, выдача поиска, источник, ответ.

Граница типов (rules/types.md): pydantic v2, валидация инвариантов из
`specs/001-v3-langgraph-rag/data-model.md`. Никакой логики поиска и LLM здесь нет.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.behavior import REFUSAL_TEXTS, RefusalReason


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


class SourceRef(BaseModel):
    """Ссылка на источник в HTTP-ответе (то, что видит фронтенд)."""

    model_config = ConfigDict(frozen=True)

    source: str = Field(min_length=1)
    paragraph_start: int = Field(ge=1)
    paragraph_end: int = Field(ge=1)
    text: str = Field(min_length=1)


class Answer(BaseModel):
    """Ответ графа: текст, признак опоры на контекст, использованные фрагменты."""

    model_config = ConfigDict(frozen=True)

    answer: str = Field(min_length=1)
    grounded: bool
    used_chunk_ids: list[str] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def _refusal_is_empty(self) -> Self:
        if not self.grounded and (self.used_chunk_ids or self.sources):
            raise ValueError("при grounded=false ответ не ссылается на фрагменты")
        return self


def refusal(reason: RefusalReason = "no_answer") -> Answer:
    """Честный отказ без источников и фактов; текст зависит от причины."""
    return Answer(answer=REFUSAL_TEXTS[reason], grounded=False)
