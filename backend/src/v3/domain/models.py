"""Доменные модели: фрагмент документа, попадание в поиск и ответ модели за один ход. Логики здесь нет."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.behavior import (
    DEBT_HINT,
    FACTS_HINT,
    FOCUS_HINT,
    KIND_HINT,
    PHONE_HINT,
    REGION_HINT,
    TEXT_HINT,
    TIME_HINT,
)


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


class TurnDraft(BaseModel):
    """Ответ модели за один запрос: сначала разбор реплики, потом текст клиенту.

    Это вход и выход адаптера модели: слоты применяет код (`domain/intake.py`), поэтому любое
    значение здесь — только предложение, а не факт профиля.
    """

    kind: Literal["question", "situation"] | None = Field(default=None, description=KIND_HINT)
    debt_amount: int | None = Field(default=None, description=DEBT_HINT)
    region: str | None = Field(default=None, description=REGION_HINT)
    phone: str | None = Field(default=None, description=PHONE_HINT)
    consultation_time: str | None = Field(default=None, description=TIME_HINT)
    facts: dict[str, str] = Field(default_factory=dict, description=FACTS_HINT)
    focus: str = Field(default="", description=FOCUS_HINT)
    text: str = Field(default="", description=TEXT_HINT)
