"""Тесты разбора реплики и узлов intake/ask (сценарий консультации)."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage

from core.behavior import ASK_DEBT, ASK_REGION, INVITE, NOT_OUR_CASE_DEBT
from domain.graph_state import GraphState
from graph.nodes.ask import make_ask_node
from graph.nodes.intake import make_intake_node
from infrastructure.llm import IntakeDraft

MIN_DEBT = 350_000
EXCLUDED = ("чечня", "днр", "лнр", "владимирская")


def make_state(question: str) -> GraphState:
    return {"request_id": "r", "question": question, "k": 3, "messages": [HumanMessage(question)]}


def fake_intake(draft: IntakeDraft) -> Any:
    return lambda question, history: draft


def test_intake_sends_specific_question_to_document() -> None:
    node = make_intake_node(fake_intake(IntakeDraft(kind="question")), min_debt_rub=MIN_DEBT, excluded_regions=EXCLUDED)

    result = node(make_state("С какой суммой берут в процедуру?"))

    assert result["next_step"] == "retrieve"
    assert "answer" not in result


def test_intake_asks_next_scenario_step() -> None:
    node = make_intake_node(
        fake_intake(IntakeDraft(kind="situation", debt_amount=800_000)),
        min_debt_rub=MIN_DEBT,
        excluded_regions=EXCLUDED,
    )

    result = node(make_state("что знаешь вообще"))

    assert result["next_step"] == "ask"
    assert result["answer"].answer == ASK_REGION  # type: ignore[union-attr]


def test_intake_stops_small_debt() -> None:
    node = make_intake_node(
        fake_intake(IntakeDraft(kind="situation", debt_amount=100_000)),
        min_debt_rub=MIN_DEBT,
        excluded_regions=EXCLUDED,
    )

    result = node(make_state("у меня долг 100 тысяч"))

    assert result["answer"].answer == NOT_OUR_CASE_DEBT  # type: ignore[union-attr]


def test_intake_invites_when_profile_is_complete() -> None:
    draft = IntakeDraft(kind="situation", debt_amount=800_000, region="Москва", has_property=True)
    node = make_intake_node(fake_intake(draft), min_debt_rub=MIN_DEBT, excluded_regions=EXCLUDED)

    result = node(make_state("долг 800 тысяч, Москва, есть машина"))

    assert result["answer"].answer == INVITE  # type: ignore[union-attr]


def test_ask_node_keeps_scenario_reply_in_history() -> None:
    result = make_ask_node()({"request_id": "r", "question": "привет", "k": 3, "messages": []})

    assert result["messages"][0].type == "ai"  # type: ignore[index]
    assert result["top_score"] == 0.0
    assert result["answer"].answer == ASK_DEBT  # type: ignore[union-attr]
