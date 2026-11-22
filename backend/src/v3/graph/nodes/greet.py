"""Узел приветствия: единственный готовый ответ, дальше всё делает модель."""

from __future__ import annotations

from langchain_core.messages import AIMessage

from core.behavior import GREETING
from domain.graph_state import GraphState
from domain.social import is_greeting
from graph.nodes import NodeFn, NodeResult

GREETING_STEP = "greeting"


def make_greet_node() -> NodeFn:
    def greet(state: GraphState) -> NodeResult:
        if not is_greeting(state.question):
            return {}
        return {
            "step": GREETING_STEP,
            "answer": GREETING,
            "grounded": False,
            "messages": [AIMessage(content=GREETING)],
        }

    return greet
