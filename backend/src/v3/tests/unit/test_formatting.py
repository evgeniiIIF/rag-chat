"""Тесты приведения ответа к читаемому виду (вёрстка, а не поведение модели)."""

from __future__ import annotations

from core.formatting import normalize_answer


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
