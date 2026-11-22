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


class ProfileSchema(BaseModel):
    """Профиль клиента из стейта графа: по нему считаются фильтры и шаг."""

    debt_amount: int | None = None
    region: str | None = None
    phone: str | None = None
    consultation_time: str | None = None
    facts: dict[str, str] = Field(default_factory=dict)


class ChunkSchema(BaseModel):
    """Фрагмент, поданный модели: адрес в документе, текст и скор поиска."""

    id: str
    source: str
    paragraph_start: int
    paragraph_end: int
    score: float
    text: str


class LlmMessageSchema(BaseModel):
    """Сообщение запроса к модели: роль и полный текст."""

    role: str
    content: str


class LlmCallSchema(BaseModel):
    """Один вызов модели, разложенный по частям: промпт, история, вход, отправка, ответ."""

    purpose: str
    model: str
    stage: str | None = None
    system: str | None = None
    history: list[LlmMessageSchema] = Field(default_factory=list)
    inputs: dict[str, str] = Field(default_factory=dict)
    messages: list[LlmMessageSchema]
    output: str | None = None


class StateSchema(BaseModel):
    """Стейт, на котором построен ответ: фронтенд пишет его в консоль браузера."""

    kind: str | None = None
    step: str | None = None
    filters_passed: bool
    search_query: str | None = None
    retrieved: int = Field(ge=0)
    chunks: list[ChunkSchema] = Field(default_factory=list)
    profile: ProfileSchema
    llm: list[LlmCallSchema] = Field(default_factory=list)


class ChatResponse(BaseModel):
    """Ответ чата: текст, источники, признак опоры на документ, лучший скор и стейт."""

    answer: str
    sources: list[SourceSchema]
    grounded: bool
    top_score: float = Field(ge=0.0, le=1.0)
    state: StateSchema
