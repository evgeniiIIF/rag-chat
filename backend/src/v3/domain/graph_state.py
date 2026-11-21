"""Состояние графа LangGraph (TypedDict, фреймворк-корень).

Узел не мутирует state: он возвращает словарь с изменёнными ключами.
Обязательны только поля, которые пишет entrypoint; остальные появляются по мере
движения по графу (`specs/001-v3-langgraph-rag/data-model.md`).
"""

from __future__ import annotations

from typing import Annotated, NotRequired, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from core.behavior import RefusalReason
from domain.models import Answer, RetrievedChunk
from domain.profile import ClientProfile


class GraphState(TypedDict):
    """Полное состояние запроса: вход, история, выдача поиска, решение об отказе, ответ."""

    request_id: str
    question: str
    k: int
    # история диалога: add_messages дописывает реплики и хранит их в чекпойнтере по thread_id
    messages: Annotated[list[BaseMessage], add_messages]
    # вопрос, переписанный с учётом истории (follow-up); без истории совпадает с question
    search_query: NotRequired[str]
    retrieved: NotRequired[list[RetrievedChunk]]
    top_score: NotRequired[float]
    refused: NotRequired[bool]
    refusal_reason: NotRequired[RefusalReason]
    # профиль клиента из беседы и следующий шаг сценария: retrieve (по документу) или ask (сценарий)
    profile: NotRequired[ClientProfile]
    next_step: NotRequired[str]
    answer: NotRequired[Answer | None]
