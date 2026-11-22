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
from core.trace import LlmTrace, capture
from domain.graph_state import GraphState
from domain.profile import ClientProfile
from graph.build import build_graph
from graph.nodes.retrieve import SearchFn
from infrastructure.artifacts import write_json
from infrastructure.llm import AnswerFn, CondenseFn, IntakeFn
from schemas.chat import (
    ChatRequest,
    ChatResponse,
    ChunkSchema,
    LlmCallSchema,
    LlmMessageSchema,
    ProfileSchema,
    SourceSchema,
    StateSchema,
    Turn,
)

FALLBACK_ANSWER = "Извините, на моей стороне что-то пошло не так. Давайте попробуем ещё раз."


class ChatService:
    """Реплика клиента → проход графа; история и профиль живут в чекпойнтере по thread_id."""

    def __init__(
        self,
        settings: Settings,
        *,
        search: SearchFn,
        answer_fn: AnswerFn,
        condense: CondenseFn | None = None,
        intake: IntakeFn | None = None,
        artifacts_dir: Path | None = None,
    ) -> None:
        self._settings = settings
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
            answer_fn=answer_fn,
            threshold=settings.score_threshold,
            artifacts_dir=self._artifacts_dir,
            condense=self._condense,
            intake=self._intake,
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

    def _restore(self, config: dict[str, Any], history: list[Turn]) -> tuple[list[BaseMessage], ClientProfile]:
        """История и профиль из чекпойнтера; если его нет — из запроса (после рестарта сервиса)."""
        stored = self._graph.get_state(config).values
        profile = stored.get("profile")
        known = profile if isinstance(profile, ClientProfile) else ClientProfile()
        if stored.get("messages"):
            return [], known
        messages: list[BaseMessage] = [
            HumanMessage(content=turn.content) if turn.role == "user" else AIMessage(content=turn.content)
            for turn in history
        ]
        return messages, known

    def ask(self, request: ChatRequest) -> ChatResponse:
        request_id = uuid4().hex[:12]
        config: dict[str, Any] = {"configurable": {"thread_id": request.session_id or request_id}}

        restored_messages, restored_profile = self._restore(config, request.history)
        state = GraphState(
            request_id=request_id,
            question=request.question,
            messages=[*restored_messages, HumanMessage(content=request.question)],
            profile=restored_profile,
            k=request.k or self._settings.retriever_k,
        )
        trace = LlmTrace()
        with capture(trace):
            result = self._graph.invoke(state, config=config)

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
