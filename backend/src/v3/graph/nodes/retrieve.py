"""Узел поиска: реплика (+ история) → самостоятельный запрос → фрагменты документа."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from core.behavior import KNOWLEDGE_STEPS
from domain.graph_state import GraphState
from domain.models import RetrievedChunk
from domain.scenario import next_step, search_query
from graph.nodes import NodeFn, NodeResult
from infrastructure.llm import CondenseFn

SearchFn = Callable[[str, int], Sequence[RetrievedChunk]]


def make_retrieve_node(search: SearchFn, condense: CondenseFn, threshold: float) -> NodeFn:
    def retrieve(state: GraphState) -> NodeResult:
        step = next_step(state.profile, state.kind)
        if step not in KNOWLEDGE_STEPS:  # подтверждение записи идёт без знаний
            return {"search_query": "", "retrieved": [], "grounded": False}
        if step == "rag":
            # follow-up («а сроки?») переписывается в самостоятельный вопрос по истории
            question = condense(state.question, state.messages[:-1]) if len(state.messages) > 1 else state.question
            query = search_query(step, question, state.profile, state.kind)
        else:
            # на info ищем по проваленному фильтру, на сборе данных — по теме шага, иначе по словам клиента
            query = search_query(step, state.question, state.profile, state.kind)
        hits = [hit for hit in search(query, state.k) if hit.score >= threshold]
        return {"search_query": query, "retrieved": hits, "grounded": bool(hits)}

    return retrieve
