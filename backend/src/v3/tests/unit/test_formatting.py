"""Тесты приведения ответа к читаемому виду (вёрстка, а не поведение модели)."""

from __future__ import annotations

from core.formatting import answer_text, enforce_style, normalize_answer, strip_source_refs
from domain.profile import ClientProfile


def test_inline_bullets_are_split_into_lines() -> None:
    text = "Платите так. - Сначала консультация. - Потом договор."

    assert normalize_answer(text) == "Платите так.\n\n- Сначала консультация.\n- Потом договор."


def test_ready_list_is_kept_intact() -> None:
    text = "Итог:\n\n- сумма\n- имущество"

    assert normalize_answer(text) == "Итог:\n\n- сумма\n- имущество"


def test_plain_text_is_untouched() -> None:
    text = "Одно предложение без списков."

    assert normalize_answer(text) == text


def test_extra_spaces_and_blank_lines_are_collapsed() -> None:
    text = "\n\nПервая   мысль.\n\n\nВторая мысль.\n\n"

    assert normalize_answer(text) == "Первая мысль.\n\nВторая мысль."


def test_bullet_without_heading() -> None:
    assert normalize_answer("- раз\n- два") == "- раз\n- два"


def test_source_refs_are_removed() -> None:
    assert normalize_answer("По документу, срок — 5 лет.") == "Срок — 5 лет."
    assert normalize_answer("Согласно источнику [КЦ.docx-0002], сумма от 350 000.") == "Сумма от 350 000."
    assert normalize_answer("во фрагменте сказано, что берём с 350 000") == "Сказано, что берём с 350 000"


def test_plain_answer_keeps_its_text() -> None:
    text = "Банкротство стоит от 350 000 рублей долга."

    assert strip_source_refs(text) == text
    assert normalize_answer(text) == text


def test_internal_notes_are_not_shown_to_client() -> None:
    assert enforce_style("Клиент настаивает на консультации, фильтры пройдены.") == ""
    assert enforce_style("Состояние фильтров: всё подходит.") == ""
    assert enforce_style("Что известно о клиенте: долг 500 000 ₽.") == ""
    assert enforce_style("Регион пока неизвестен.") == ""
    assert enforce_style("Сумма долга пока неизвестна.") == ""
    text = answer_text(
        "Клиент настаивает на консультации, фильтры пройдены.",
        [],
        "",
        "invite",
        ask="Напишите, пожалуйста, ваш телефон и удобное время для звонка.",
    )
    assert text == "Напишите, пожалуйста, ваш телефон и удобное время для звонка."


def test_step_question_is_not_repeated() -> None:
    question = "Подскажите, пожалуйста, в каком регионе вы прописаны?"

    assert answer_text(question, [], "", "ask_region", ask=question) == question


def test_booking_text_reads_naturally() -> None:
    profile = ClientProfile(phone="+79991234567", consultation_time="завтра 12:00")

    text = answer_text("", [], "", "booked", profile)

    assert "юрист позвонит на" in text
    assert "+79991234567" in text
    assert "время — завтра" in text


def test_explanation_survives_when_model_ends_with_step_question() -> None:
    summary = (
        "Понимаю, ситуация с рассрочкой давит, но для банкротства важна общая сумма всех долгов — "
        "кредиты, займы, рассрочки, налоги, ЖКХ. Подскажите, пожалуйста, какая у вас общая сумма долга "
        "по всем обязательствам?"
    )
    ask = "Подскажите, пожалуйста, какая у вас общая сумма долга?"

    text = answer_text(summary, [], "", "ask_debt", ask=ask)

    assert "кредиты, займы, рассрочки, налоги, ЖКХ" in text
    assert text.endswith(ask)
    assert text.count("какая у вас общая сумма долга") == 1
