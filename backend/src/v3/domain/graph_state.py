"""Состояние графа (pydantic BaseModel).

messages — типизированные сообщения LangChain (System/Human/AI); add_messages склеивает
историю между ходами. Остальные поля — данные текущего хода и профиль клиента.
"""

from __future__ import annotations

from typing import Annotated, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from domain.models import Answer, RetrievedChunk
from domain.profile import ClientProfile


class GraphState(BaseModel):
    """Всё, что путешествует по графу: история, вопрос, профиль, шаг, RAG-поля."""

    # история диалога: LangGraph сам добавляет реплики узлов через add_messages
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)

    # вход текущего хода
    request_id: str = ""
    question: str = ""
    k: int = 3  # сколько фрагментов искать (из ChatRequest.k или Settings.retriever_k)

    # профиль (заполняется extract)
    profile: ClientProfile = Field(default_factory=ClientProfile)

    # маршрут текущего хода (ставит extract + route)
    kind: Literal["situation", "question"] = "situation"
    step: str = ""

    # RAG-ветка
    search_query: str = ""
    retrieved: list[RetrievedChunk] = Field(default_factory=list)
    top_score: float = 0.0
    refused: bool = False
    refusal_reason: str = ""
    answer: Answer | None = None
