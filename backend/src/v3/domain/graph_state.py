"""Состояние графа: история, реплика клиента, профиль и результат текущего хода."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from domain.models import RetrievedChunk
from domain.profile import ClientProfile


class GraphState(BaseModel):
    """Всё, что путешествует по графу."""

    # история диалога: LangGraph сам добавляет реплики узлов через add_messages
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)

    # вход текущего хода
    request_id: str = ""
    question: str = ""
    k: int = 3

    # профиль (заполняет extract) и тип реплики
    profile: ClientProfile = Field(default_factory=ClientProfile)
    kind: Literal["situation", "question"] = "situation"

    # шаг и результат текущего хода; previous_step — шаг прошлого хода (из чекпойнтера)
    step: str = ""
    previous_step: str = ""
    search_query: str = ""
    retrieved: list[RetrievedChunk] = Field(default_factory=list)
    answer: str = ""
    # вопрос клиенту отдельно от консультации: интерфейс показывает его плашкой
    answer_question: str = ""
    # подтверждённая запись: собирается из профиля, а не из ответа модели
    answer_booking: dict[str, Any] | None = None
    # ответ блоками для интерфейса: суть, факты, список, оговорка, вопрос
    answer_blocks: list[dict[str, Any]] = Field(default_factory=list)
    grounded: bool = False
