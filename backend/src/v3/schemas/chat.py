"""Границы HTTP /api/chat: pydantic v2, контракт из `specs/001-v3-langgraph-rag/contracts`.

Поля повторяют `frontend/src/features/chat/types.ts`: вопрос, история (нужна, если чекпойнтер
пуст — после рестарта сервиса), optional `session_id` (thread_id памяти диалога) и `k`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

HISTORY_MAX_TURNS: int = 30
QUESTION_MAX_LENGTH: int = 2000


class Turn(BaseModel):
    """Реплика истории: восстанавливает контекст, если чекпойнтер пуст."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=QUESTION_MAX_LENGTH)


class SourceSchema(BaseModel):
    """Фрагмент-источник в ответе."""

    source: str = Field(min_length=1)
    paragraph_start: int = Field(ge=0)
    paragraph_end: int = Field(ge=0)
    text: str


class ChatRequest(BaseModel):
    """Запрос чата."""

    question: str = Field(min_length=1, max_length=QUESTION_MAX_LENGTH)
    history: list[Turn] = Field(default_factory=list, max_length=HISTORY_MAX_TURNS)
    session_id: str | None = Field(default=None, min_length=1, max_length=64)
    k: int | None = Field(default=None, ge=1, le=10)


class ChatResponse(BaseModel):
    """Ответ чата: текст, источники, признак опоры на документ, лучший скор."""

    answer: str
    sources: list[SourceSchema]
    grounded: bool
    top_score: float = Field(ge=0.0, le=1.0)
