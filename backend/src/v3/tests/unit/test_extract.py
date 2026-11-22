"""Тесты узла разбора: новые данные заменяют старые, мусор не затирает профиль."""

from __future__ import annotations

from collections.abc import Sequence

from langchain_core.messages import BaseMessage

from domain.graph_state import GraphState
from domain.profile import ClientProfile
from graph.nodes.extract import make_extract_node
from infrastructure.llm import IntakeDraft


class FakeIntake:
    def __init__(self, draft: IntakeDraft) -> None:
        self.draft = draft
        self.calls = 0

    def __call__(self, question: str, history: Sequence[BaseMessage]) -> IntakeDraft:
        self.calls += 1
        return self.draft


def make_state(question: str, profile: ClientProfile | None = None) -> GraphState:
    return GraphState(question=question, profile=profile or ClientProfile())


def test_new_debt_replaces_old_value() -> None:
    node = make_extract_node(FakeIntake(IntakeDraft(kind="situation", debt_amount=500_000)))
    state = make_state("у меня долг 500 тысяч", ClientProfile(debt_amount=310_000))

    result = node(state)

    assert result["profile"].debt_amount == 500_000
    assert result["kind"] == "situation"


def test_garbage_debt_does_not_wipe_known_value() -> None:
    node = make_extract_node(FakeIntake(IntakeDraft(kind="situation", debt_amount=3_555_000_000)))
    state = make_state("да это вся сумма", ClientProfile(debt_amount=310_000))

    result = node(state)

    assert result["profile"].debt_amount == 310_000


def test_garbage_region_is_ignored() -> None:
    node = make_extract_node(FakeIntake(IntakeDraft(kind="situation", region="RUB", debt_amount=310_000)))

    result = node(make_state("310000 рублей"))

    assert result["profile"].region is None
    assert result["profile"].debt_amount == 310_000


def test_phone_and_time_from_text_and_draft() -> None:
    draft = IntakeDraft(kind="situation", phone=None, consultation_time=None)
    node = make_extract_node(FakeIntake(draft))

    result = node(make_state("запишите на завтра, телефон 8 999 123-45-67"))

    assert result["profile"].consultation_time == "завтра"
    assert result["profile"].phone is not None


def test_question_kind_is_passed_through() -> None:
    node = make_extract_node(FakeIntake(IntakeDraft(kind="question")))

    result = node(make_state("сколько стоит процедура?"))

    assert result["kind"] == "question"
