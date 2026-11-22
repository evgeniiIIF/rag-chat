"""Узел отказа: честный ответ «нет оснований» и реплика в историю."""

from __future__ import annotations

from langchain_core.messages import AIMessage

from domain.graph_state import GraphState
from domain.models import refusal
from graph.nodes import NodeFn, NodeResult


def make_refuse_node() -> NodeFn:
    def refuse(state: GraphState) -> NodeResult:
        answer = refusal(state.refusal_reason or "no_context")  # type: ignore[arg-type]
        return {"answer": answer, "messages": [AIMessage(content=answer.answer)]}

    return refuse
