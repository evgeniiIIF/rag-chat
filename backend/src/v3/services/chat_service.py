"""Сценарий чата: граф запроса → артефакты → контракт фронтенда."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

from core.config import Settings
from core.formatting import normalize_answer
from domain.graph_state import GraphState
from domain.models import refusal
from domain.profile import ClientProfile
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
        # память диалога переживает рестарт: sqlite-файл рядом с артефактами
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self._artifacts_dir / "checkpoints.sqlite"),
            check_same_thread=False,
        )
        self._checkpointer = SqliteSaver(
            self._conn,
            serde=JsonPlusSerializer(
                allowed_msgpack_modules=(
                    ("domain.profile", "ClientProfile"),
                    ("domain.models", "Answer"),
                    ("domain.models", "RetrievedChunk"),
                    ("domain.models", "SourceRef"),
                    ("domain.models", "Chunk"),
                )
            ),
        )
        self._graph = build_graph(
            search=search,
            threshold=settings.score_threshold,
            invoke=invoke,
            artifacts_dir=self._artifacts_dir,
            condense=self._condense,
            intake=self._intake,
            min_debt_rub=settings.min_debt_rub,
            excluded_regions=settings.excluded_region_list,
            checkpointer=self._checkpointer,
        )

    def _restore(self, config: dict[str, Any], history: list[Turn]) -> tuple[list[BaseMessage], ClientProfile | None]:
        """История и профиль из чекпойнтера; если пуст (рестарт) — из history запроса.

        Профиль при рестарте не восстанавливаем из реплик (это работа intake),
        но если чекпойнтер жив — возвращаем его, чтобы «да» видело invited.
        """
        stored_state = self._graph.get_state(config).values
        stored_msgs = stored_state.get("messages") or []
        stored_profile = stored_state.get("profile")
        if stored_msgs:
            return [], stored_profile
        if not history:
            return [], stored_profile
        messages = [
            HumanMessage(content=turn.content) if turn.role == "user" else AIMessage(content=turn.content)
            for turn in history
        ]
        return messages, stored_profile

    def ask(self, request: ChatRequest) -> ChatResponse:
        """Выполнить запрос: вернуть ответ по документу или честный отказ."""
        request_id = uuid4().hex[:12]
        # thread_id = сессия клиента: по нему LangGraph достаёт историю из чекпойнтера
        thread_id = request.session_id or request_id
        config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
        restored_messages, restored_profile = self._restore(config, request.history)
        state: GraphState = {
            "request_id": request_id,
            "question": request.question,
            "k": request.k or self._settings.retriever_k,
            "messages": [*restored_messages, HumanMessage(content=request.question)],
        }
        if restored_profile is not None:
            state["profile"] = restored_profile
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
