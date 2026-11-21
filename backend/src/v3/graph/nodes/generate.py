"""Узел генерации: промпт → структурный ответ модели → Answer (или честный отказ)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

from langchain_core.messages import AIMessage

from core.behavior import RefusalReason, leaks_internals
from domain.graph_state import GraphState
from domain.models import Answer, Chunk, SourceRef, refusal
from domain.profile import ClientProfile
from graph.nodes import NodeFn, NodeResult
from infrastructure.artifacts import write_json
from infrastructure.llm import AnswerDraft, StructuredInvoke, build_messages

logger = logging.getLogger(__name__)


def compose(draft: AnswerDraft) -> str:
    """Суть + пункты + следующий шаг → читаемый markdown (структуру задаёт схема)."""
    parts = [draft.answer.strip()]
    points = [point.strip() for point in draft.points if point.strip()]
    if points:
        parts.append("\n".join(f"- {point}" for point in points))
    if draft.next_step:
        parts.append(draft.next_step.strip())
    return "\n\n".join(part for part in parts if part)


def to_answer(draft: AnswerDraft, chunks: Sequence[Chunk], reason: RefusalReason = "no_answer") -> Answer:
    """Ответ модели → доменный Answer; неизвестные id отбрасываются, без опоры — отказ."""
    known = {chunk.id: chunk for chunk in chunks}
    used = [chunk_id for chunk_id in dict.fromkeys(draft.used_chunk_ids) if chunk_id in known]
    if leaks_internals(draft.answer):
        # модель проговорилась про инструкцию/фрагменты — клиенту это видеть нельзя
        return refusal("no_answer")
    if not draft.grounded or not used:
        # модель сама честно сказала «не знаю, спросите юриста» — её слова человечнее шаблона
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
    """Узел, который пишет артефакты промпта/ответа и возвращает `answer`."""

    def generate(state: GraphState) -> NodeResult:
        chunks = [hit.chunk for hit in state.get("retrieved", [])]
        request_dir = artifacts_dir / state["request_id"]
        # последняя реплика в state — текущий вопрос, он уходит в промпт отдельным сообщением
        history = state.get("messages", [])[:-1]
        # этап: пока идёт сбор слотов — qualify, иначе ответ по документу — consult
        profile = state.get("profile") or ClientProfile()
        # qualify — пока собираем слоты; invited/booked — уже консультация
        stage = "qualify" if profile.stage == "qualify" and not profile.invited else "consult"
        messages = build_messages(state["question"], chunks, history, stage=stage)
        write_json(
            request_dir / "prompt.json",
            {
                "question": state["question"],
                "chunk_ids": [chunk.id for chunk in chunks],
                "messages": [message.model_dump() for message in messages],
            },
        )
        try:
            draft = invoke(messages)
        except Exception:  # сбой модели не должен превращаться в 500
            logger.warning("модель не дала разборчивый ответ", exc_info=True)
            answer = refusal(state.get("refusal_reason", "no_answer"))
            write_json(request_dir / "answer.json", {"draft": None, "refused": True, "error": "model_error"})
            return {"answer": answer, "messages": [AIMessage(content=answer.answer)]}
        write_json(
            request_dir / "answer.json",
            {"draft": draft.model_dump(), "refused": not draft.grounded},
        )
        answer = to_answer(draft, chunks, state.get("refusal_reason", "no_answer"))
        return {"answer": answer, "messages": [AIMessage(content=answer.answer)]}

    return generate
