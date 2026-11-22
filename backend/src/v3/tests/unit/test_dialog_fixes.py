"""Регрессия по диалогу из закрепа: регионы, телефон, время, ожидаемый слот, факты, дисциплина ответа."""

from __future__ import annotations

from collections.abc import Sequence

from langchain_core.messages import BaseMessage

from core.formatting import enforce_style
from domain.graph_state import GraphState
from domain.profile import ClientProfile, extract_phone, extract_time, is_excluded_region, normalize_phone
from domain.scenario import expected_slot
from graph.nodes.extract import make_extract_node
from infrastructure.llm import IntakeDraft

QUALIFIED = ClientProfile(debt_amount=899_000, region="Дагестан")


class FakeIntake:
    def __init__(self, draft: IntakeDraft) -> None:
        self.draft = draft

    def __call__(self, question: str, history: Sequence[BaseMessage]) -> IntakeDraft:
        return self.draft


def run(question: str, draft: IntakeDraft, profile: ClientProfile) -> ClientProfile:
    return make_extract_node(FakeIntake(draft))(GraphState(question=question, profile=profile))["profile"]


def test_excluded_regions_in_any_case_form() -> None:
    for region in ["Чечне", "Чечня", "в Чеченской республике", "Владимирской области", "ДНР", "Донецк"]:
        assert is_excluded_region(region), region
    assert not is_excluded_region("Дагестан")
    assert not is_excluded_region("Москва")


def test_phone_accepts_6_10_and_11_digits() -> None:
    assert normalize_phone("66 44 55") == "66-44-55"
    assert normalize_phone("999 123 45 67") == "+79991234567"
    assert normalize_phone("8 999 123-45-67") == "+79991234567"
    assert normalize_phone("6644") is None
    assert normalize_phone("12345678") is None
    assert normalize_phone("123456789012") is None


def test_extract_phone_from_text() -> None:
    assert extract_phone("66 44 55 завтра в 12") == "66-44-55"
    assert extract_phone("мой номер 89991234567 в 12:00") == "+79991234567"
    assert extract_phone("664455") is None
    assert extract_phone("664455", allow_bare_short=True) == "66-44-55"


def test_time_with_day_and_hour() -> None:
    assert extract_time("завтра в 12") == "завтра 12:00"
    assert extract_time("в 12") == "12:00"
    assert extract_time("899 тысяч") is None


def test_expected_slot_follows_the_steps() -> None:
    assert expected_slot(ClientProfile()) == "debt"
    assert expected_slot(ClientProfile(debt_amount=899_000)) == "region"
    assert expected_slot(QUALIFIED) == "phone"
    assert expected_slot(QUALIFIED.model_copy(update={"phone": "66-44-55"})) == "time"
    assert expected_slot(ClientProfile(debt_amount=100_000)) is None


def test_bare_digits_are_a_phone_when_phone_was_asked() -> None:
    profile = run("664455", IntakeDraft(kind="situation", debt_amount=664_455), QUALIFIED)

    assert profile.phone == "66-44-55"
    assert profile.debt_amount == 899_000


def test_bare_digits_are_a_debt_when_debt_was_asked() -> None:
    assert run("664455", IntakeDraft(kind="question"), ClientProfile()).debt_amount == 664_455


def test_short_phone_answer_stays_incomplete() -> None:
    profile = run(
        "6644 завтра в 12", IntakeDraft(kind="situation", phone="6644", consultation_time="завтра в 12:00"), QUALIFIED
    )

    assert profile.phone is None
    assert profile.phone_raw == "6644"
    assert profile.consultation_time == "завтра в 12:00"


def test_complete_phone_clears_phone_raw() -> None:
    profile = run("вот номер", IntakeDraft(kind="situation", phone="+7 900 123-45-67"), ClientProfile(phone_raw="6644"))

    assert profile.phone == "+79001234567"
    assert profile.phone_raw is None


def test_hour_only_answer_after_phone() -> None:
    booked = QUALIFIED.model_copy(update={"phone": "66-44-55"})

    assert run("12", IntakeDraft(kind="question"), booked).consultation_time == "12:00"


def test_region_answer_when_region_was_asked() -> None:
    profile = run("дагестан", IntakeDraft(kind="question"), ClientProfile(debt_amount=899_000))

    assert profile.region == "дагестан"


def test_slot_duplicates_are_dropped_from_facts() -> None:
    draft = IntakeDraft(
        kind="situation", facts={"notes": "сумма ниже порога", "долг": "899 тыс", "цель": "банкротство"}
    )

    assert run("расскажу про себя", draft, ClientProfile(facts={"interest": "МФЦ"})).facts == {"цель": "банкротство"}


def test_stories_are_removed() -> None:
    text = "Понял вас. Знаю случай, когда женщина не прошла МФЦ. Вам подойдёт рассрочка."

    assert enforce_style(text, "info") == "Понял вас. Вам подойдёт рассрочка."


def test_info_has_no_questions() -> None:
    assert enforce_style("Вы не проходите по сумме. Хотите расскажу про МФЦ?", "info") == "Вы не проходите по сумме."


def test_collecting_step_keeps_ack_and_question() -> None:
    assert enforce_style("Понял. Это важно. Какая сумма долга?", "ask_debt") == "Понял. Какая сумма долга?"


def test_long_answer_is_cut_but_final_question_stays() -> None:
    text = "Раз. Два. Три. Четыре. Пять. Назовите телефон?"

    assert enforce_style(text, "invite") == "Раз. Два. Три. Назовите телефон?"
