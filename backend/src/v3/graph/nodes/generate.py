"""Узел генерации: промпт → структурный ответ модели → Answer (или честный отказ)."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from pathlib import Path

from langchain_core.messages import AIMessage

from core.behavior import RefusalReason, leaks_internals
from domain.graph_state import GraphState
from domain.models import Answer, Chunk, SourceRef, refusal
from domain.profile import filter_question
from graph.nodes import NodeFn, NodeResult
from infrastructure.artifacts import write_json
from infrastructure.llm import AnswerDraft, Stage, StructuredInvoke, build_messages

logger = logging.getLogger(__name__)


_HEADER_RE = re.compile(r"^(?:Условия|Риски|Кейс|Записать|Шаг|Дальше|Подскажу)\s*:\s*", re.IGNORECASE)


def _clean_point(point: str) -> str:
    """Убрать служебные заголовки («Условия:», «Риски:», «Кейс:») из пункта."""
    return _HEADER_RE.sub("", point.strip()).strip()


def compose(draft: AnswerDraft) -> str:
    parts = [draft.answer.strip()]
    points = [_clean_point(p) for p in draft.points if _clean_point(p)]
    if points:
        parts.append("\n".join(f"- {p}" for p in points))
    if draft.next_step:
        parts.append(_clean_point(draft.next_step))
    return "\n\n".join(part for part in parts if part)


def to_answer(draft: AnswerDraft, chunks: Sequence[Chunk], reason: RefusalReason = "no_answer") -> Answer:
    known = {chunk.id: chunk for chunk in chunks}
    used = [chunk_id for chunk_id in dict.fromkeys(draft.used_chunk_ids) if chunk_id in known]
    if leaks_internals(draft.answer):
        return refusal("no_answer")
    if not draft.grounded or not used:
        text = draft.answer.strip()
        return Answer(answer=text, grounded=False) if text else refusal(reason)
    sources = [
        SourceRef(
            source=known[chunk_id].source,
            paragraph_start=known[chunk_id].paragraph_start,
            paragraph_end=known[chunk_id].paragraph_end,
            text=known[chunk_id].text,
        )
        for chunk_id in used
    ]
    return Answer(answer=compose(draft), grounded=True, used_chunk_ids=used, sources=sources)


def make_generate_node(invoke: StructuredInvoke, *, artifacts_dir: Path) -> NodeFn:
    def generate(state: GraphState) -> NodeResult:
        chunks = [hit.chunk for hit in state.retrieved]
        request_dir = artifacts_dir / state.request_id
        history = state.messages[:-1]
        profile = state.profile
        stage: Stage = "info" if filter_question(profile) else "consult"
        messages = build_messages(state.question, chunks, history, stage=stage)
        write_json(
            request_dir / "prompt.json",
            {
                "question": state.question,
                "chunk_ids": [chunk.id for chunk in chunks],
                "messages": [message.model_dump() for message in messages],
            },
        )
        try:
            draft = invoke(messages)
        except Exception:
            logger.warning("модель не дала разборчивый ответ", exc_info=True)
            answer = refusal(state.refusal_reason or "no_answer")  # type: ignore[arg-type]
            write_json(request_dir / "answer.json", {"draft": None, "refused": True, "error": "model_error"})
            return {"answer": answer, "messages": [AIMessage(content=answer.answer)]}
        write_json(request_dir / "answer.json", {"draft": draft.model_dump(), "refused": not draft.grounded})
        answer = to_answer(draft, chunks, state.refusal_reason or "no_answer")  # type: ignore[arg-type]
        return {"answer": answer, "messages": [AIMessage(content=answer.answer)]}

    return generate
