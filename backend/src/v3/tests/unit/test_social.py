"""Тесты распознавания приветствия: единственная реплика без модели."""

from __future__ import annotations

import pytest

from domain.social import is_greeting


@pytest.mark.parametrize("text", ["привет", "Здравствуйте!", "добрый день", "хай", "ку", "Hello"])
def test_greeting_detected(text: str) -> None:
    assert is_greeting(text) is True


@pytest.mark.parametrize(
    "text",
    ["привет, у меня долг 500 тысяч", "с какой суммой берут?", "Москва", "нет", "спасибо"],
)
def test_not_greeting(text: str) -> None:
    assert is_greeting(text) is False
