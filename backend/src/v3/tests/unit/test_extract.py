"""Тесты узла разбора: новые данные заменяют старые, мусор не затирает профиль."""

from __future__ import annotations

from collections.abc import Sequence

from langchain_core.messages import BaseMessage

from domain.graph_state import GraphState
from domain.profile import ClientProfile
from graph.nodes.extract import _apply_expected, make_extract_node
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


def test_region_is_not_taken_from_a_request_phrase() -> None:
    # бот уже отказал по «чечня»; следующая реплика — просьба, а не новый регион
    node = make_extract_node(FakeIntake(IntakeDraft(kind="situation")))
    profile = ClientProfile(debt_amount=500_000, region="чечня")

    result = node(make_state("консультацию давай", profile))

    assert result["profile"].region == "чечня"
    assert result["profile"].failed_filter() == "region"


def test_region_changes_when_client_names_another_one() -> None:
    # новое значение приходит от модели и применяется на любом шаге, в том числе после отказа
    node = make_extract_node(FakeIntake(IntakeDraft(kind="situation", region="Дагестан")))
    profile = ClientProfile(debt_amount=500_000, region="чечня")

    result = node(make_state("в дагестане прописан", profile))

    assert result["profile"].region == "Дагестан"
    assert result["profile"].failed_filter() is None


def test_reply_words_do_not_overwrite_known_region() -> None:
    # «просрочки» — это факт, а не регион: бот регион уже спросил и получил «чечня»
    node = make_extract_node(FakeIntake(IntakeDraft(kind="situation")))
    profile = ClientProfile(debt_amount=500_000, region="чечня")

    result = node(make_state("просрочки", profile))

    assert result["profile"].region == "чечня"


def test_amount_in_a_phrase_counts_when_the_sum_was_asked() -> None:
    """Бот спросил сумму — «рассрочку на 310к платить не могу» это и есть ответ."""
    draft = _apply_expected(
        ClientProfile(),
        "рассрочку на 310к платить уже не могу",
        IntakeDraft(kind="situation"),
        expected="debt",
    )

    assert draft.debt_amount == 310_000


def test_side_amount_is_not_the_total_debt() -> None:
    """Регион спросили — сумма из попутной фразы общим долгом не становится."""
    draft = _apply_expected(
        ClientProfile(),
        "рассрочка на 310к тяжёлая, прописан в Москве",
        IntakeDraft(kind="situation"),
        expected="region",
    )

    assert draft.debt_amount is None
