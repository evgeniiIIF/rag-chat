"""Узел сценарного ответа: готовый текст (вопрос сценария, отказ или приглашение) → клиенту."""

from __future__ import annotations

from langchain_core.messages import AIMessage

from domain.graph_state import GraphState
from domain.models import Answer
from domain.profile import ClientProfile, scenario_reply
from graph.nodes import NodeFn, NodeResult


def make_ask_node() -> NodeFn:
    """Отдаёт решение сценария из intake; при пустом ответе спрашивает по шагам."""

    def ask(state: GraphState) -> NodeResult:
        answer = state.get("answer") or Answer(
            answer=scenario_reply(state.get("profile") or ClientProfile(), "ok"), grounded=False
        )
        return {"answer": answer, "top_score": 0.0, "messages": [AIMessage(content=answer.answer)]}

    return ask
