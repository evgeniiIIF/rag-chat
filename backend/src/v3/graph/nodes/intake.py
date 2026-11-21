"""Узел разбора реплики: вопрос по правилам или ситуация клиента (слоты профиля)."""

from __future__ import annotations

from collections.abc import Sequence

from core.behavior import NOT_OUR_CASE_DEBT, NOT_OUR_CASE_REGION
from domain.graph_state import GraphState
from domain.models import Answer
from domain.profile import qualify, scenario_reply
from graph.nodes import NodeFn, NodeResult
from infrastructure.llm import IntakeFn


def make_intake_node(
    intake: IntakeFn,
    *,
    min_debt_rub: int,
    excluded_regions: Sequence[str],
) -> NodeFn:
    """Понимает реплику и решает: отвечать по документу или вести сценарий."""

    def node(state: GraphState) -> NodeResult:
        draft = intake(state["question"], state.get("messages", [])[:-1])
        profile = draft.profile()
        qualification = qualify(profile, min_debt_rub=min_debt_rub, excluded_regions=excluded_regions)
        result: NodeResult = {"profile": profile, "next_step": "retrieve"}
        if qualification != "ok":
            text = NOT_OUR_CASE_DEBT if qualification == "small_debt" else NOT_OUR_CASE_REGION
            return {**result, "next_step": "ask", "answer": Answer(answer=text, grounded=False)}
        if draft.kind == "situation":
            text = scenario_reply(profile, qualification)
            return {**result, "next_step": "ask", "answer": Answer(answer=text, grounded=False)}
        return result

    return node
