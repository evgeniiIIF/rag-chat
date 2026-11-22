"""Узел ответа: один вызов модели на любой шаг разговора.

Модель получает роль, историю, профиль, состояние фильтров, инструкцию шага и (только на шагах
rag/info) очищенные знания компании: без инструкций операторам и без кейсов других клиентов.
Ответ проходит `enforce_style`: длина, один вопрос, никаких чужих историй.
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.messages import AIMessage

from core.formatting import enforce_style, knowledge_text, normalize_answer
from domain.graph_state import GraphState
from domain.models import Chunk
from domain.scenario import CONTEXT_STEPS, next_step
from graph.nodes import NodeFn, NodeResult
from infrastructure.artifacts import write_json
from infrastructure.llm import AnswerFn, build_prompt


def _clean_context(state: GraphState, step: str) -> list[Chunk]:
    """Знания только для шагов rag/info и только годные для клиента."""
    if step not in CONTEXT_STEPS:
        return []
    cleaned: list[Chunk] = []
    for hit in state.retrieved:
        text = knowledge_text(hit.chunk.text)
        if text:
            cleaned.append(hit.chunk.model_copy(update={"text": text}))
    return cleaned


def make_answer_node(answer_fn: AnswerFn, artifacts_dir: Path | None = None) -> NodeFn:
    def answer(state: GraphState) -> NodeResult:
        step = next_step(state.profile, state.kind)
        context = _clean_context(state, step)
        prompt = build_prompt(
            step=step,
            profile=state.profile,
            question=state.question,
            chunks=context,
            history=state.messages[:-1],
        )
        text = normalize_answer(enforce_style(answer_fn(prompt), step))
        if artifacts_dir:
            write_json(
                artifacts_dir / state.request_id / f"answer_{step}.json",
                {"step": step, "profile": state.profile.model_dump(), "prompt": prompt.dump(), "text": text},
            )
        return {
            "step": step,
            "answer": text,
            "grounded": bool(context),
            "messages": [AIMessage(content=text)],
        }

    return answer
