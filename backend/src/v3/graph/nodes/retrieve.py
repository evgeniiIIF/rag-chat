"""Узел поиска: вопрос → фрагменты документа."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from domain.graph_state import GraphState
from domain.models import RetrievedChunk
from graph.nodes import NodeFn, NodeResult

SearchFn = Callable[[str, int], Sequence[RetrievedChunk]]


def make_retrieve_node(search: SearchFn) -> NodeFn:
    """Узел, который наполняет `retrieved` выдачей гибридного поиска."""

    def retrieve(state: GraphState) -> NodeResult:
        query = state.get("search_query") or state["question"]
        return {"retrieved": list(search(query, state["k"]))}

    return retrieve
