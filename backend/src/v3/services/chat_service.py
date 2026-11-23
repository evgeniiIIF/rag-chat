"""Сценарий чата: граф запроса → артефакты → контракт фронтенда."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

from core.behavior import FALLBACK_ANSWER
from core.config import Settings
from core.trace import LlmTrace, capture
from domain.graph_state import GraphState
from domain.profile import ClientProfile
from graph.build import build_graph
from graph.nodes import SearchFn
from infrastructure.artifacts import write_json
from infrastructure.llm import TurnFn
from schemas.chat import (
    QUESTION_MAX_LENGTH,
    BlockSchema,
    BookingSchema,
    ChatRequest,
    ChatResponse,
    ChunkSchema,
    HistoryResponse,
    LlmCallSchema,
    LlmMessageSchema,
    ProfileSchema,
    SourceSchema,
    StateSchema,
    Turn,
)


class ChatService:
    """Реплика клиента → проход графа; история и профиль живут в чекпойнтере по thread_id."""

    def __init__(
        self,
        settings: Settings,
        *,
        search: SearchFn,
        turn_fn: TurnFn,
        artifacts_dir: Path | None = None,
    ) -> None:
        self._settings = settings
        self._artifacts_dir = artifacts_dir if artifacts_dir is not None else settings.artifacts_dir
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self._artifacts_dir / "checkpoints.sqlite"),
            check_same_thread=False,
        )
        self._checkpointer = SqliteSaver(
            self._conn,
            serde=JsonPlusSerializer(
                pickle_fallback=True,
                allowed_msgpack_modules=(
                    ("domain.profile", "ClientProfile"),
                    ("domain.models", "Chunk"),
                    ("domain.models", "RetrievedChunk"),
                ),
            ),
        )
        self._graph = build_graph(
            search=search,
            turn_fn=turn_fn,
            threshold=settings.score_threshold,
            artifacts_dir=self._artifacts_dir,
            checkpointer=self._checkpointer,
        )

    @property
    def graph(self) -> Any:
        """Скомпилированный граф — только для просмотра структуры (/api/graph)."""
        return self._graph

    def reset_session(self, session_id: str) -> None:
        """Удалить состояние сессии из чекпойнтера (кнопка «Очистить чат»)."""
        self._conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (session_id,))
        self._conn.execute("DELETE FROM writes WHERE thread_id = ?", (session_id,))
        self._conn.commit()

    def history(self, session_id: str) -> HistoryResponse:
        """Реплики сессии из чекпойнтера — единственный источник истории для фронтенда."""
        config: dict[str, Any] = {"configurable": {"thread_id": session_id}}
        stored = self._graph.get_state(config).values
        messages = [
            Turn(
                role="user" if message.type == "human" else "assistant",
                content=str(message.content)[:QUESTION_MAX_LENGTH],
            )
            for message in stored.get("messages") or []
            if message.type in {"human", "ai"} and str(message.content).strip()
        ]
        return HistoryResponse(messages=messages)

    def _restore(self, config: dict[str, Any], history: list[Turn]) -> tuple[list[BaseMessage], ClientProfile, str]:
        """История, профиль и шаг прошлого хода из чекпойнтера; если его нет — из запроса."""
        stored = self._graph.get_state(config).values
        profile = stored.get("profile")
        known = profile if isinstance(profile, ClientProfile) else ClientProfile()
        previous_step = stored.get("step") if isinstance(stored.get("step"), str) else ""
        if stored.get("messages"):
            return [], known, previous_step
        messages: list[BaseMessage] = [
            HumanMessage(content=turn.content) if turn.role == "user" else AIMessage(content=turn.content)
            for turn in history
        ]
        return messages, known, previous_step

    def _prepare(self, request: ChatRequest) -> tuple[str, GraphState, dict[str, Any]]:
        """Идентификатор хода, стартовое состояние графа и конфиг потока (thread_id сессии)."""
        request_id = uuid4().hex[:12]
        config: dict[str, Any] = {"configurable": {"thread_id": request.session_id or request_id}}
        restored_messages, restored_profile, previous_step = self._restore(config, request.history)
        state = GraphState(
            request_id=request_id,
            question=request.question,
            messages=[*restored_messages, HumanMessage(content=request.question)],
            profile=restored_profile,
            previous_step=previous_step,
            k=request.k or self._settings.retriever_k,
        )
        return request_id, state, config

    def ask(self, request: ChatRequest) -> ChatResponse:
        request_id, state, config = self._prepare(request)
        trace = LlmTrace()
        with capture(trace):
            result = self._graph.invoke(state, config=config)
        return self._response(request_id, result, trace)

    def _response(self, request_id: str, result: dict[str, Any], trace: LlmTrace) -> ChatResponse:
        """Контракт фронтенда: текст, источники, скор и состояние с вызовами модели."""
        retrieved = result.get("retrieved") or []
        profile = result.get("profile")
        this_profile = profile if isinstance(profile, ClientProfile) else ClientProfile()
        write_json(
            self._artifacts_dir / request_id / "retrieved.json",
            [hit.model_dump(mode="json") for hit in retrieved],
        )
        write_json(self._artifacts_dir / request_id / "llm.json", trace.model_dump(mode="json"))

        top_score = max((hit.score for hit in retrieved), default=0.0)
        return ChatResponse(
            answer=result.get("answer") or FALLBACK_ANSWER,
            question=result.get("answer_question") or "",
            known=[],  # осознанно скрыто: клиент видит только ответ и плашки записи
            booking=BookingSchema(**result["answer_booking"]) if result.get("answer_booking") else None,
            blocks=[BlockSchema(**block) for block in result.get("answer_blocks") or []],
            sources=[
                SourceSchema(
                    source=hit.chunk.source,
                    paragraph_start=hit.chunk.paragraph_start,
                    paragraph_end=hit.chunk.paragraph_end,
                    text=hit.chunk.text,
                )
                for hit in retrieved
            ],
            grounded=bool(result.get("grounded")),
            top_score=min(1.0, max(0.0, top_score)),
            state=StateSchema(
                kind=result.get("kind"),
                step=result.get("step") or None,
                filters_passed=this_profile.filters_ok(),
                search_query=result.get("search_query") or None,
                retrieved=len(retrieved),
                chunks=[
                    ChunkSchema(
                        id=hit.chunk.id,
                        source=hit.chunk.source,
                        paragraph_start=hit.chunk.paragraph_start,
                        paragraph_end=hit.chunk.paragraph_end,
                        score=hit.score,
                        text=hit.chunk.text,
                    )
                    for hit in retrieved
                ],
                profile=ProfileSchema(**this_profile.model_dump()),
                llm=[
                    LlmCallSchema(
                        purpose=call.purpose,
                        model=call.model,
                        stage=call.stage,
                        system=call.system,
                        history=[LlmMessageSchema(**message.model_dump()) for message in call.history],
                        inputs=call.inputs,
                        messages=[LlmMessageSchema(**message.model_dump()) for message in call.messages],
                        output=call.output,
                    )
                    for call in trace.calls
                ],
            ),
        )
