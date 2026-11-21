"""Узел переписывания вопроса: follow-up («а если ипотека?») → самостоятельный вопрос."""

from __future__ import annotations

from domain.graph_state import GraphState
from graph.nodes import NodeFn, NodeResult
from infrastructure.llm import CondenseFn


def make_condense_node(condense: CondenseFn) -> NodeFn:
    """Узел, который пишет `search_query`; без истории вопрос уходит как есть (без вызова модели)."""

    def node(state: GraphState) -> NodeResult:
        # последняя реплика в state — текущий вопрос, историей считаем всё до неё
        history = state.get("messages", [])[:-1]
        if not history:
            return {"search_query": state["question"]}
        return {"search_query": condense(state["question"], history)}

    return node
