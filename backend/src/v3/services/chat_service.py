"""Сценарий чата: граф запроса → артефакты → контракт фронтенда."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from core.config import Settings
from core.formatting import normalize_answer
from domain.graph_state import GraphState
from domain.models import refusal
from graph.build import build_graph
from graph.nodes.retrieve import SearchFn
from infrastructure.artifacts import write_json
from infrastructure.llm import CondenseFn, IntakeFn, StructuredInvoke
from schemas.chat import ChatRequest, ChatResponse, SourceSchema, Turn


class ChatService:
    """Вопрос клиента → проход графа; история диалога живёт в чекпойнтере по thread_id."""

    def __init__(
        self,
        settings: Settings,
        *,
        search: SearchFn,
        invoke: StructuredInvoke,
        condense: CondenseFn | None = None,
        intake: IntakeFn | None = None,
        artifacts_dir: Path | None = None,
    ) -> None:
        self._settings = settings
        self._condense = condense
        self._intake = intake
        self._artifacts_dir = artifacts_dir if artifacts_dir is not None else settings.artifacts_dir
        self._graph = build_graph(
            search=search,
            threshold=settings.score_threshold,
            invoke=invoke,
            artifacts_dir=self._artifacts_dir,
            condense=self._condense,
            intake=self._intake,
            min_debt_rub=settings.min_debt_rub,
            excluded_regions=settings.excluded_region_list,
            checkpointer=InMemorySaver(),
        )

    def _restore(self, config: dict[str, Any], history: list[Turn]) -> list[BaseMessage]:
        """История из чекпойнтера; если он пуст (рестарт сервиса) — берём history из запроса."""
        if not history:
            return []
        stored = self._graph.get_state(config).values.get("messages") or []
        if stored:
            return []
        return [
            HumanMessage(content=turn.content) if turn.role == "user" else AIMessage(content=turn.content)
            for turn in history
        ]

    def ask(self, request: ChatRequest) -> ChatResponse:
        """Выполнить запрос: вернуть ответ по документу или честный отказ."""
        request_id = uuid4().hex[:12]
        # thread_id = сессия клиента: по нему LangGraph достаёт историю из чекпойнтера
        thread_id = request.session_id or request_id
        config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
        state: GraphState = {
            "request_id": request_id,
            "question": request.question,
            "k": request.k or self._settings.retriever_k,
            "messages": [*self._restore(config, request.history), HumanMessage(content=request.question)],
        }
        result: dict[str, Any] = self._graph.invoke(state, config=config)
        retrieved = result.get("retrieved") or []
        write_json(
            self._artifacts_dir / request_id / "retrieved.json",
            [hit.model_dump(mode="json") for hit in retrieved],
        )

        answer = result.get("answer") or refusal()
        top_score = float(result.get("top_score") or 0.0)
        return ChatResponse(
            answer=normalize_answer(answer.answer),
            sources=[
                SourceSchema(
                    source=source.source,
                    paragraph_start=source.paragraph_start,
                    paragraph_end=source.paragraph_end,
                    text=source.text,
                )
                for source in answer.sources
            ],
            grounded=answer.grounded,
            top_score=min(1.0, max(0.0, top_score)),
        )
