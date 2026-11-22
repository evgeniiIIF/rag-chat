"""Сборка графа (LangGraph): четыре узла и одна развилка.

  START → greet ─приветствие→ END
                └→ extract → retrieve → answer → END

greet     — готовое приветствие (единственный хардкод);
extract   — модель разбирает реплику в слоты профиля (любое поле можно изменить);
retrieve  — поиск фрагментов КЦ на КАЖДОМ шаге: модель всегда получает базу знаний;
answer    — один вызов модели на любой шаг, шаг считает `domain/scenario.next_step`.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from domain.graph_state import GraphState
from graph.nodes import NodeFn
from graph.nodes.answer import make_answer_node
from graph.nodes.extract import make_extract_node
from graph.nodes.greet import GREETING_STEP, make_greet_node
from graph.nodes.retrieve import SearchFn, make_retrieve_node
from infrastructure.llm import AnswerFn, CondenseFn, IntakeDraft, IntakeFn

logger = logging.getLogger(__name__)

NODE_GREET = "greet"
NODE_EXTRACT = "extract"
NODE_RETRIEVE = "retrieve"
NODE_ANSWER = "answer"


def route_after_greet(state: GraphState) -> str:
    return END if state.step == GREETING_STEP else NODE_EXTRACT


def build_graph(
    *,
    search: SearchFn,
    answer_fn: AnswerFn,
    threshold: float,
    artifacts_dir: Path,
    condense: CondenseFn | None = None,
    intake: IntakeFn | None = None,
    checkpointer: Any = None,
) -> Any:
    rewrite: CondenseFn = condense if condense is not None else (lambda question, history: question)

    def fallback_intake(question: str, history: Sequence[Any]) -> IntakeDraft:
        return IntakeDraft(kind="situation")

    read: IntakeFn = intake if intake is not None else fallback_intake

    nodes: dict[str, NodeFn] = {
        NODE_GREET: make_greet_node(),
        NODE_EXTRACT: make_extract_node(read),
        NODE_RETRIEVE: make_retrieve_node(search, rewrite, threshold),
        NODE_ANSWER: make_answer_node(answer_fn, artifacts_dir=artifacts_dir),
    }

    graph: StateGraph[GraphState] = StateGraph(GraphState)
    for name, node in nodes.items():
        graph.add_node(name, cast(Any, node))

    graph.add_edge(START, NODE_GREET)
    graph.add_conditional_edges(NODE_GREET, route_after_greet, {END: END, NODE_EXTRACT: NODE_EXTRACT})
    graph.add_edge(NODE_EXTRACT, NODE_RETRIEVE)
    graph.add_edge(NODE_RETRIEVE, NODE_ANSWER)
    graph.add_edge(NODE_ANSWER, END)

    return graph.compile(checkpointer=checkpointer)
