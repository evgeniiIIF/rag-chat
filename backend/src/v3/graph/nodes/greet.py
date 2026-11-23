"""Узел соц-реплик: приветствие, благодарность, прощание — готовый текст, без модели."""

from __future__ import annotations

from langchain_core.messages import AIMessage

from core.behavior import BYE_REPLY, GREETING_FIRST, GREETING_REPEAT, THANKS_REPLY
from domain.graph_state import GraphState
from domain.social import social_kind
from graph.nodes import NodeFn, NodeResult

GREETING_STEP = "greeting"

_REPLIES: dict[str, str] = {"thanks": THANKS_REPLY, "bye": BYE_REPLY}


def make_greet_node() -> NodeFn:
    def greet(state: GraphState) -> NodeResult:
        kind = social_kind(state.question)
        if kind is None:
            return {}
        # в истории уже есть реплики — значит здороваемся не первый раз
        repeated = bool(state.messages[:-1])
        text = (GREETING_REPEAT if repeated else GREETING_FIRST) if kind == "greeting" else _REPLIES[kind]
        return {
            "step": GREETING_STEP,
            "answer": text,
            "grounded": False,
            "messages": [AIMessage(content=text)],
        }

    return greet
