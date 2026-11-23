"""Регрессия по диалогу из закрепа: регионы, телефон, время, ожидаемый слот, факты, дисциплина ответа."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from langchain_core.messages import BaseMessage

from core.formatting import answer_text, build_blocks, enforce_style
from domain.graph_state import GraphState
from domain.models import RetrievedChunk
from domain.profile import ClientProfile, extract_phone, extract_time, is_excluded_region, normalize_phone
from domain.scenario import expected_slot
from graph.nodes.extract import make_extract_node
from graph.nodes.retrieve import make_retrieve_node
from infrastructure.llm import IntakeDraft

QUALIFIED = ClientProfile(debt_amount=899_000, region="Дагестан")


class FakeIntake:
    def __init__(self, draft: IntakeDraft) -> None:
        self.draft = draft

    def __call__(self, question: str, history: Sequence[BaseMessage]) -> IntakeDraft:
        return self.draft


def run(question: str, draft: IntakeDraft, profile: ClientProfile) -> ClientProfile:
    state = make_extract_node(FakeIntake(draft))(GraphState(question=question, profile=profile))
    return cast(ClientProfile, state["profile"])


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
    assert extract_phone("мой номер 89991234567 в 12:00") == "+79991234567"
    assert extract_phone("66 44 55 завтра в 12") is None  # короткий номер — только в ответ на вопрос


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

    assert enforce_style(text, "info") == "Вам подойдёт рассрочка."


def test_info_has_no_questions() -> None:
    assert enforce_style("Вы не проходите по сумме. Хотите расскажу про МФЦ?", "info") == "Вы не проходите по сумме."


def test_collecting_step_keeps_ack_and_question() -> None:
    assert enforce_style("Понял. Это важно. Какая сумма долга?", "ask_debt") == "Какая сумма долга?"


def test_long_answer_is_cut_but_final_question_stays() -> None:
    text = "Раз. Два. Три. Четыре. Пять. Назовите телефон?"

    assert enforce_style(text, "invite") == "Назовите телефон?"


def test_internal_note_is_not_sent_to_client() -> None:
    text = answer_text(
        "Клиент настаивает на консультации, фильтры пройдены.",
        [],
        "",
        "invite",
        ask="Подскажите, пожалуйста, удобное время для звонка.",
    )

    assert text == "Подскажите, пожалуйста, удобное время для звонка."


def test_installment_amount_is_not_the_total_debt() -> None:
    profile = run(
        "я в целом с долгами справляюсь, но именно рассрочку на 310к платить уже не могу",
        IntakeDraft(kind="situation", debt_amount=310_000),
        ClientProfile(),
    )

    assert profile.debt_amount is None


def test_amount_named_as_debt_is_the_total_debt() -> None:
    profile = run("500к сумма", IntakeDraft(kind="situation", debt_amount=500_000), ClientProfile())

    assert profile.debt_amount == 500_000


def test_search_is_skipped_when_knowledge_is_not_needed() -> None:
    calls: list[str] = []

    def search(query: str, k: int) -> list[RetrievedChunk]:
        calls.append(query)
        return []

    node = make_retrieve_node(search, lambda question, history: question, 0.1)
    client = QUALIFIED.model_copy(update={"phone": "+79991234567", "consultation_time": "12:00"})

    node(GraphState(question="завтра в 12", profile=client))
    assert calls == []

    node(GraphState(question="какие сроки?", profile=QUALIFIED, kind="question"))
    assert calls


def test_time_named_as_a_number_is_normalized() -> None:
    profile = run("554433 в 10", IntakeDraft(kind="situation", phone="554433", consultation_time="10"), ClientProfile())

    assert profile.consultation_time == "10:00"
    assert profile.phone == "55-44-33"


def test_mirrored_facts_collapse_to_one() -> None:
    profile = run(
        "просрочка",
        IntakeDraft(kind="situation", facts={"просрочка": "не может платить рассрочку"}),
        ClientProfile(facts={"не справляется с платежами по рассрочке": "просрочка"}),
    )

    assert profile.facts == {"просрочка": "не может платить рассрочку"}


def test_unknown_slot_note_is_not_shown_to_client() -> None:
    text = answer_text("Регион пока неизвестен.", [], "", "ask_region")

    assert text == ""


def test_blocks_do_not_show_where_the_answer_came_from() -> None:
    blocks = build_blocks("Мы берём в процедуру долги от 350 000 ₽.", "", "Какая у вас общая сумма долга?")

    assert [block["type"] for block in blocks] == ["lead", "question"]
    assert "контекст" not in str(blocks).lower()
    assert "источник" not in str(blocks).lower()
