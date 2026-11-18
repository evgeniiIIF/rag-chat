"""Unit: IntentDetector.detect и .already_greeted (узел 09 цепочки)."""

from __future__ import annotations

from src.models.turn import Turn
from src.services.intent_detector import Intent, IntentDetector


def test_detect_greeting_exact_token() -> None:
    assert IntentDetector.detect("привет") is Intent.GREETING
    assert IntentDetector.detect("Здравствуйте") is Intent.GREETING


def test_detect_thanks() -> None:
    assert IntentDetector.detect("спасибо") is Intent.THANKS


def test_detect_bye() -> None:
    assert IntentDetector.detect("до свидания") is Intent.BYE


def test_detect_question_fallback() -> None:
    assert IntentDetector.detect("как списать долги?") is Intent.QUESTION


def test_detect_is_exact_not_substring() -> None:
    # «приветствие» — не приветствие; детектор не должен ловить подстроку
    assert IntentDetector.detect("приветствие в суде") is Intent.QUESTION


def test_already_greeted_true_when_assistant_greeted() -> None:
    history = [
        Turn(role="user", content="здравствуйте"),
        Turn(role="assistant", content="Здравствуйте! Чем могу помочь?"),
    ]
    assert IntentDetector.already_greeted(history) is True


def test_already_greeted_false_without_assistant_greeting() -> None:
    history = [
        Turn(role="user", content="привет"),
        Turn(role="assistant", content="Расскажите о вашей ситуации."),
    ]
    assert IntentDetector.already_greeted(history) is False
