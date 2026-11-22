"""Узел ответа: один вызов модели на любой шаг разговора.

Модель получает роль, историю, профиль, состояние фильтров, инструкцию шага и (если шаг
требует) фрагменты документа. Формулирует ответ сама — цитат и пересказа инструкций нет.
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.messages import AIMessage

from core.formatting import normalize_answer
from domain.graph_state import GraphState
from domain.scenario import CONTEXT_STEPS, next_step
from graph.nodes import NodeFn, NodeResult
from infrastructure.artifacts import write_json
from infrastructure.llm import AnswerFn, build_prompt


def make_answer_node(answer_fn: AnswerFn, artifacts_dir: Path | None = None) -> NodeFn:
    def answer(state: GraphState) -> NodeResult:
        step = next_step(state.profile, state.kind)
        prompt = build_prompt(
            step=step,
            profile=state.profile,
            question=state.question,
            chunks=[hit.chunk for hit in state.retrieved],
            history=state.messages[:-1],
        )
        text = normalize_answer(answer_fn(prompt))
        if artifacts_dir:
            write_json(
                artifacts_dir / state.request_id / f"answer_{step}.json",
                {"step": step, "profile": state.profile.model_dump(), "prompt": prompt.dump(), "text": text},
            )
        return {
            "step": step,
            "answer": text,
            "grounded": bool(state.retrieved) and step in CONTEXT_STEPS,
            "messages": [AIMessage(content=text)],
        }

    return answer
