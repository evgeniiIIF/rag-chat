"""Сборка графа (LangGraph): соц-реплика по правилам и один ход с моделью.

  START → greet ─привет/спасибо/пока→ END
                └→ turn → END

greet — готовый текст без модели (единственный хардкод);
turn  — код считает шаг, ожидаемый слот и запросы в индекс, находит фрагменты, зовёт модель
        РОВНО ОДИН РАЗ и применяет её поля к профилю; если знаний нет или запись уже оформлена,
        модель не вызывается вовсе и текст собирает код.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from domain.graph_state import GraphState
from graph.nodes import NodeFn, SearchFn
from graph.nodes.greet import GREETING_STEP, make_greet_node
from graph.nodes.turn import make_turn_node
from infrastructure.llm import TurnFn

NODE_GREET = "greet"
NODE_TURN = "turn"


def route_after_greet(state: GraphState) -> str:
    return END if state.step == GREETING_STEP else NODE_TURN


def build_graph(
    *,
    search: SearchFn,
    turn_fn: TurnFn,
    threshold: float,
    artifacts_dir: Path,
    checkpointer: Any = None,
) -> Any:
    nodes: dict[str, NodeFn] = {
        NODE_GREET: make_greet_node(),
        NODE_TURN: make_turn_node(turn_fn, search, threshold, artifacts_dir=artifacts_dir),
    }

    graph: StateGraph[GraphState] = StateGraph(GraphState)
    for name, node in nodes.items():
        graph.add_node(name, cast(Any, node))

    graph.add_edge(START, NODE_GREET)
    graph.add_conditional_edges(NODE_GREET, route_after_greet, {END: END, NODE_TURN: NODE_TURN})
    graph.add_edge(NODE_TURN, END)

    return graph.compile(checkpointer=checkpointer)
