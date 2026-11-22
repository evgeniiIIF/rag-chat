"""Узел переписывания вопроса: follow-up → самостоятельный вопрос."""

from __future__ import annotations

from domain.graph_state import GraphState
from graph.nodes import NodeFn, NodeResult
from infrastructure.llm import CondenseFn


def make_condense_node(condense: CondenseFn) -> NodeFn:
    def node(state: GraphState) -> NodeResult:
        history = state.messages[:-1]
        if not history:
            return {"search_query": state.question}
        return {"search_query": condense(state.question, history)}

    return node
