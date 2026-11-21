"""Сборка графа: social | condense → intake → (ask | retrieve → grade → generate | refuse).

Память диалога — штатный чекпойнтер LangGraph: история живёт в state.messages и
восстанавливается по `thread_id` (session_id клиента).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from domain.graph_state import GraphState
from domain.social import Intent, detect
from graph.nodes import NodeFn
from graph.nodes.ask import make_ask_node
from graph.nodes.condense import make_condense_node
from graph.nodes.generate import make_generate_node
from graph.nodes.grade import make_grade_node
from graph.nodes.intake import make_intake_node
from graph.nodes.refuse import make_refuse_node
from graph.nodes.retrieve import SearchFn, make_retrieve_node
from graph.nodes.social import make_social_node
from infrastructure.llm import CondenseFn, IntakeDraft, IntakeFn, StructuredInvoke

NODE_SOCIAL = "social"
NODE_CONDENSE = "condense"
NODE_INTAKE = "intake"
NODE_ASK = "ask"
NODE_RETRIEVE = "retrieve"
NODE_GRADE = "grade"
NODE_GENERATE = "generate"
NODE_REFUSE = "refuse"


def route_social(state: GraphState) -> str:
    """Маршрут со входа: соц-реплика или агрессия отвечаются сразу, деловой вопрос идёт в разбор."""
    return NODE_CONDENSE if detect(state["question"]) is Intent.QUESTION else NODE_SOCIAL


def route_after_intake(state: GraphState) -> str:
    """Маршрут после разбора реплики: отвечаем по документу или ведём сценарий."""
    return NODE_ASK if state.get("next_step") == "ask" else NODE_RETRIEVE


def route_after_grade(state: GraphState) -> str:
    """Маршрут после оценки: нет оснований — узел отказа, иначе — генерация."""
    return NODE_REFUSE if state.get("refused", True) else NODE_GENERATE


def build_graph(
    *,
    search: SearchFn,
    threshold: float,
    invoke: StructuredInvoke,
    artifacts_dir: Path,
    condense: CondenseFn | None = None,
    intake: IntakeFn | None = None,
    min_debt_rub: int = 350_000,
    excluded_regions: Sequence[str] = (),
    checkpointer: Any = None,
) -> Any:
    """Скомпилированный граф запроса; с чекпойнтером помнит диалог по thread_id."""
    rewrite: CondenseFn = condense if condense is not None else (lambda question, history: question)
    read: IntakeFn = intake if intake is not None else (lambda question, history: IntakeDraft(kind="question"))
    nodes: dict[str, NodeFn] = {
        NODE_SOCIAL: make_social_node(),
        NODE_CONDENSE: make_condense_node(rewrite),
        NODE_INTAKE: make_intake_node(read, min_debt_rub=min_debt_rub, excluded_regions=excluded_regions),
        NODE_ASK: make_ask_node(),
        NODE_RETRIEVE: make_retrieve_node(search),
        NODE_GRADE: make_grade_node(threshold),
        NODE_GENERATE: make_generate_node(invoke, artifacts_dir=artifacts_dir),
        NODE_REFUSE: make_refuse_node(),
    }

    graph: StateGraph[GraphState] = StateGraph(GraphState)
    for name, node in nodes.items():
        # cast: LangGraph 1.x связывает NodeInputT с собственным TypedDictLikeV2,
        # наш GraphState (typing.NotRequired) в этот bound не выводится.
        graph.add_node(name, cast(Any, node))

    graph.add_conditional_edges(
        START,
        route_social,
        {NODE_SOCIAL: NODE_SOCIAL, NODE_CONDENSE: NODE_CONDENSE},
    )
    graph.add_edge(NODE_SOCIAL, END)
    graph.add_edge(NODE_CONDENSE, NODE_INTAKE)
    graph.add_conditional_edges(
        NODE_INTAKE,
        route_after_intake,
        {NODE_ASK: NODE_ASK, NODE_RETRIEVE: NODE_RETRIEVE},
    )
    graph.add_edge(NODE_ASK, END)
    graph.add_edge(NODE_RETRIEVE, NODE_GRADE)
    graph.add_conditional_edges(
        NODE_GRADE,
        route_after_grade,
        {NODE_GENERATE: NODE_GENERATE, NODE_REFUSE: NODE_REFUSE},
    )
    graph.add_edge(NODE_GENERATE, END)
    graph.add_edge(NODE_REFUSE, END)
    return graph.compile(checkpointer=checkpointer)
