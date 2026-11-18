"""Unit: IntentDetector.detect и .already_greeted (узел 09 цепочки)."""

from __future__ import annotations

import pytest

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


# ── S34: широкий словарь приветствий при строгом полном совпадении ──────────────
ALL_GREETINGS = (
    "привет",
    "Привет!",
    "приветик",
    "прет",
    "прив",
    "пр",
    "приветствую",
    "здравствуй",
    "Здравствуйте!",
    "здраствуйте",
    "здрасьте",
    "здрасте",
    "здрасти",
    "здрям",
    "здр",
    "зд",
    "з",
    "здоров",
    "здорова",
    "здарова",
    "хай",
    "хаюшки",
    "hello",
    "hi",
    "hey",
    "ку",
    "йо",
    "алло",
    "ау",
    "добрый день",
    "Добрый вечер!",
    "доброе утро",
    "день добрый",
    "вечер добрый",
    "доброго времени суток",
    "мое почтение",
    "здравия желаю",
    "привет всем",
    "всем привет",
    "приветствую вас",
    "ну привет",
    "и снова здравствуйте",
)

NOT_GREETINGS = (
    # нет полного совпадения → деловая реплика
    "здравствуйте, хочу списать долги",
    "привет, у меня долг 500000",
    "приветствие в суде",
    "пр 500000",
    "куда обратиться по долгам",
    "здорово получилось, а что с долгами",
    "алло, это по банкротству?",
    "добрый день, сколько стоит банкротство",
)


@pytest.mark.parametrize("text", ALL_GREETINGS)
def test_greeting_variants_detected(text: str) -> None:
    assert IntentDetector.detect(text) is Intent.GREETING, text


@pytest.mark.parametrize("text", NOT_GREETINGS)
def test_greeting_is_full_match_only(text: str) -> None:
    assert IntentDetector.detect(text) is Intent.QUESTION, text


@pytest.mark.parametrize("text", ("пока", "Пока!", "покеда", "бай", "до связи", "до встречи", "всего доброго", "спокойной ночи", "доброй ночи"))
def test_bye_variants_detected(text: str) -> None:
    assert IntentDetector.detect(text) is Intent.BYE, text


@pytest.mark.parametrize("text", ("пока не знаю", "пока думаю", "пока нет", "до связи не доходит"))
def test_bye_not_triggered_by_prefix(text: str) -> None:
    assert IntentDetector.detect(text) is Intent.QUESTION, text


@pytest.mark.parametrize("text", ("спасибо", "спс", "сб", "пасиб", "благодарю", "мерси", "thx", "спасибо большое", "спасибо вам"))
def test_thanks_variants_detected(text: str) -> None:
    assert IntentDetector.detect(text) is Intent.THANKS, text
