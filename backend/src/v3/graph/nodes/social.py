"""Узел соц-реплики: приветствие/спасибо/прощание — готовый текст (D1), без LLM."""

from __future__ import annotations

from langchain_core.messages import AIMessage

from core.behavior import BYE_REPLY, GREETING_FIRST, GREETING_REPEAT, THANKS_REPLY
from domain.graph_state import GraphState
from domain.models import Answer
from domain.social import Intent, already_greeted, detect
from graph.nodes import NodeFn, NodeResult


def make_social_node() -> NodeFn:
    def social(state: GraphState) -> NodeResult:
        intent = detect(state.question)
        if intent is Intent.GREETING:
            reply = GREETING_REPEAT if already_greeted(state.messages[:-1]) else GREETING_FIRST
        elif intent is Intent.THANKS:
            reply = THANKS_REPLY
        else:
            reply = BYE_REPLY
        answer = Answer(answer=reply, grounded=False)
        return {"answer": answer, "top_score": 0.0, "messages": [AIMessage(content=reply)]}

    return social
