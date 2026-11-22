"""Узел поиска: реплика (+ история) → самостоятельный запрос → фрагменты документа."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from domain.graph_state import GraphState
from domain.models import RetrievedChunk
from domain.scenario import next_step, search_query
from graph.nodes import NodeFn, NodeResult
from infrastructure.llm import CondenseFn

SearchFn = Callable[[str, int], Sequence[RetrievedChunk]]


def make_retrieve_node(search: SearchFn, condense: CondenseFn, threshold: float) -> NodeFn:
    def retrieve(state: GraphState) -> NodeResult:
        step = next_step(state.profile, state.kind)
        if step == "rag":
            # follow-up («а сроки?») переписывается в самостоятельный вопрос по истории
            question = condense(state.question, state.messages[:-1]) if len(state.messages) > 1 else state.question
            query = search_query(step, question)
        else:
            # «800 тысяч» или «ставрополь» — плохой поисковый запрос: ищем то, что нужно на шаге
            query = search_query(step, state.question)
        hits = [hit for hit in search(query, state.k) if hit.score >= threshold]
        return {"search_query": query, "retrieved": hits, "grounded": bool(hits)}

    return retrieve
