"""Очистка знаний от инструкций и кейсов, разбор суммы из короткой реплики."""

from __future__ import annotations

from collections.abc import Sequence

from langchain_core.messages import BaseMessage

from core.formatting import knowledge_text
from domain.graph_state import GraphState
from domain.profile import parse_amount
from graph.nodes.extract import make_extract_node
from infrastructure.llm import IntakeDraft


class FakeIntake:
    def __init__(self, draft: IntakeDraft) -> None:
        self.draft = draft

    def __call__(self, question: str, history: Sequence[BaseMessage]) -> IntakeDraft:
        return self.draft


def test_parse_amount_variants() -> None:
    assert parse_amount("323 тыс") == 323_000
    assert parse_amount("899 тысяч") == 899_000
    assert parse_amount("1,5 млн") == 1_500_000
    assert parse_amount("500к") == 500_000
    assert parse_amount("323 000 рублей") == 323_000
    assert parse_amount("323000") == 323_000


def test_parse_amount_ignores_phone_hour_and_sentences() -> None:
    assert parse_amount("66 44 55") is None
    assert parse_amount("12") is None
    assert parse_amount("у меня долг 500 тысяч") is None
    assert parse_amount("а если долг 500 тысяч?") is None


def test_pure_amount_is_data_even_if_model_said_question() -> None:
    node = make_extract_node(FakeIntake(IntakeDraft(kind="question")))

    result = node(GraphState(question="323 тыс"))

    assert result["profile"].debt_amount == 323_000
    assert result["kind"] == "situation"


def test_operator_instructions_are_not_knowledge() -> None:
    assert knowledge_text("ОБУЧЕНИЕ КЦ\n\nГлавная мысль для консультации такая: клиент приходит за списанием.") == ""
    assert knowledge_text("Главная задача — успокоить клиента и продать юриста.") == ""


def test_case_tails_are_not_knowledge() -> None:
    assert knowledge_text("от Яндекса награду Хорошее место. Это не нужно зачитывать.") == ""
    assert knowledge_text("женщина, которая пыталась пройти МФЦ. Заявление вернули.") == ""


def test_case_is_cut_but_rule_stays() -> None:
    text = "Внесудебное банкротство подходит не всем. У нас была женщина, которой вернули заявление."

    assert knowledge_text(text) == "Внесудебное банкротство подходит не всем."
