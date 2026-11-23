"""Тесты шага разговора: шесть шагов и порядок фильтров."""

from __future__ import annotations

from domain.profile import ClientProfile
from domain.scenario import CONTEXT_STEPS, INFO_QUERIES, STEP_QUERIES, next_step, search_query


def test_question_goes_to_context_answer() -> None:
    # обязательные фильтры важнее: пока сумма и регион не собраны, вопрос ждёт
    assert next_step(ClientProfile(), "question") == "ask_debt"
    qualified = ClientProfile(debt_amount=800_000, region="Москва")
    assert next_step(qualified, "question") == "rag"
    assert "rag" in CONTEXT_STEPS


def test_filters_are_collected_in_order() -> None:
    assert next_step(ClientProfile(), "situation") == "ask_debt"
    assert next_step(ClientProfile(debt_amount=800_000), "situation") == "ask_region"


def test_failed_filters_give_context_explanation() -> None:
    assert next_step(ClientProfile(debt_amount=200_000, region="Москва"), "situation") == "info"
    assert next_step(ClientProfile(debt_amount=800_000, region="Чечня"), "situation") == "info"
    assert "info" in CONTEXT_STEPS


def test_one_failed_filter_stops_the_questions_at_once() -> None:
    # сумма ниже порога, регион ещё не спрошен — сразу справка, а не вопрос про регион
    assert next_step(ClientProfile(debt_amount=310_000), "situation") == "info"
    # исключённый регион известен, сумма ещё нет — тоже сразу справка
    assert next_step(ClientProfile(region="Чеченская Республика"), "situation") == "info"


def test_passed_filters_invite_and_book() -> None:
    qualified = ClientProfile(debt_amount=800_000, region="Москва")
    assert next_step(qualified, "situation") == "invite"
    assert next_step(qualified.model_copy(update={"phone": "+79991234567"}), "situation") == "invite"
    booked = qualified.model_copy(update={"phone": "+79991234567", "consultation_time": "завтра"})
    assert next_step(booked, "situation") == "booked"


def test_slot_can_change_at_any_step() -> None:
    # сумма упала ниже порога — шаг сразу меняется на справку
    profile = ClientProfile(debt_amount=800_000, region="Москва")
    assert next_step(profile, "situation") == "invite"
    assert next_step(profile.model_copy(update={"debt_amount": 100_000}), "situation") == "info"


def test_search_query_follows_the_step() -> None:
    profile = ClientProfile()
    # вопрос клиента ищется как есть, на остальных шагах — то, что делаем сейчас
    assert search_query("rag", "а какие сроки?", profile) == "а какие сроки?"
    queries = {step: search_query(step, "800 тысяч", profile) for step in STEP_QUERIES}
    assert len(set(queries.values())) == len(queries)  # у каждого шага свой запрос


def test_info_query_depends_on_the_failed_filter() -> None:
    # на info ищем то, что предложить вместо процедуры, и только по проваленному фильтру
    assert search_query("info", "320 тысяч", ClientProfile(debt_amount=320_000)) == INFO_QUERIES["debt"]
    assert search_query("info", "Чечня", ClientProfile(region="Чечня")) == INFO_QUERIES["region"]
    assert search_query("info", "ну и что", ClientProfile()) == "ну и что"
