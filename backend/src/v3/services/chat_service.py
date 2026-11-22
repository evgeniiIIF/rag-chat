"""Сценарий чата: граф запроса → артефакты → контракт фронтенда."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

from core.config import Settings
from core.formatting import normalize_answer
from domain.graph_state import GraphState
from domain.models import refusal
from domain.profile import ClientProfile, filter_question
from domain.social import Intent, detect
from graph.build import build_graph
from graph.nodes.retrieve import SearchFn
from infrastructure.artifacts import write_json
from infrastructure.llm import CondenseFn, IntakeFn, StructuredInvoke
from schemas.chat import ChatRequest, ChatResponse, SourceSchema, Turn


class ChatService:
    """Вопрос клиента → проход графа; история и профиль живут в чекпойнтере по thread_id."""

    def __init__(
        self,
        settings: Settings,
        *,
        model: BaseChatModel,
        search: SearchFn,
        invoke: StructuredInvoke,
        condense: CondenseFn | None = None,
        intake: IntakeFn | None = None,
        artifacts_dir: Path | None = None,
    ) -> None:
        self._settings = settings
        self._model = model
        self._condense = condense
        self._intake = intake
        self._artifacts_dir = artifacts_dir if artifacts_dir is not None else settings.artifacts_dir
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self._artifacts_dir / "checkpoints.sqlite"),
            check_same_thread=False,
        )
        self._checkpointer = SqliteSaver(
            self._conn,
            serde=JsonPlusSerializer(pickle_fallback=True, 
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
            model=self._model,
            search=search,
            threshold=settings.score_threshold,
            invoke=invoke,
            artifacts_dir=self._artifacts_dir,
            condense=self._condense,
            intake=self._intake,
            checkpointer=self._checkpointer,
        )

    def reset_session(self, session_id: str) -> None:
        """Удалить состояние сессии из чекпойнтера (кнопка «Очистить чат»)."""
        self._conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (session_id,))
        self._conn.execute("DELETE FROM writes WHERE thread_id = ?", (session_id,))
        self._conn.commit()

    def _restore(self, config: dict[str, Any], history: list[Turn]) -> tuple[list, ClientProfile]:
        stored_state = self._graph.get_state(config).values
        stored_msgs = stored_state.get("messages") or []
        stored_profile = stored_state.get("profile")
        if stored_msgs:
            return [], stored_profile if isinstance(stored_profile, ClientProfile) else ClientProfile()
        if not history:
            return [], stored_profile if isinstance(stored_profile, ClientProfile) else ClientProfile()
        msgs = [
            HumanMessage(content=turn.content) if turn.role == "user" else AIMessage(content=turn.content)
            for turn in history
        ]
        return msgs, stored_profile if isinstance(stored_profile, ClientProfile) else ClientProfile()

    def ask(self, request: ChatRequest) -> ChatResponse:
        request_id = uuid4().hex[:12]
        thread_id = request.session_id or request_id
        config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}

        restored_messages, restored_profile = self._restore(config, request.history)
        state = GraphState(
            request_id=request_id,
            question=request.question,
            messages=[*restored_messages, HumanMessage(content=request.question)],
            profile=restored_profile,
        )
        result = self._graph.invoke(state, config=config)
        retrieved = result.get("retrieved") or []
        write_json(
            self._artifacts_dir / request_id / "retrieved.json",
            [hit.model_dump(mode="json") for hit in retrieved],
        )
        answer = result.get("answer") or refusal()
        text = answer.answer
        profile = result.get("profile")
        if isinstance(profile, ClientProfile) and detect(request.question) is Intent.QUESTION:
            next_question = filter_question(profile)
            if next_question and not text.rstrip().endswith(("?", "?**")):
                text = f"{text.rstrip()}\n\n**{next_question}**"
        top_score = float(result.get("top_score") or 0.0)
        return ChatResponse(
            answer=normalize_answer(text),
            sources=[
                SourceSchema(
                    source=s.source,
                    paragraph_start=s.paragraph_start,
                    paragraph_end=s.paragraph_end,
                    text=s.text,
                )
                for s in answer.sources
            ],
            grounded=answer.grounded,
            top_score=min(1.0, max(0.0, top_score)),
        )
