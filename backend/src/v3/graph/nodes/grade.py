"""Узел оценки: есть ли основание отвечать (числовой гейт по скору)."""

from __future__ import annotations

from domain.graph_state import GraphState
from graph.nodes import NodeFn, NodeResult


def make_grade_node(threshold: float) -> NodeFn:
    """Узел, который пишет `top_score`, решает `refused` и объясняет причину отказа."""

    def grade(state: GraphState) -> NodeResult:
        hits = state.get("retrieved", [])
        if not hits:
            return {"top_score": 0.0, "refused": True, "refusal_reason": "no_context"}
        top_score = max(hit.score for hit in hits)
        if top_score < threshold:
            return {"top_score": top_score, "refused": True, "refusal_reason": "below_threshold"}
        return {"top_score": top_score, "refused": False}

    return grade
