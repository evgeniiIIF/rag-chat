"""Узел отказа: честный ответ «нет оснований» и реплика в историю диалога."""

from __future__ import annotations

from langchain_core.messages import AIMessage

from domain.graph_state import GraphState
from domain.models import refusal
from graph.nodes import NodeFn, NodeResult


def make_refuse_node() -> NodeFn:
    """Узел, который пишет стандартный отказ и добавляет его в историю."""

    def refuse(state: GraphState) -> NodeResult:
        answer = refusal(state.get("refusal_reason", "no_context"))
        return {"answer": answer, "messages": [AIMessage(content=answer.answer)]}

    return refuse
