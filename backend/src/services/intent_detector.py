"""Детектор намерений: приветствие, спасибо, прощание, вопрос (точное совпадение токенов)."""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum, auto

from ..models.turn import Turn


class Intent(Enum):
    GREETING = auto()
    THANKS = auto()
    BYE = auto()
    QUESTION = auto()


GREETING_TOKENS = {
    "привет",
    "здравствуйте",
    "здрасьте",
    "добрый день",
    "добрый вечер",
    "хай",
    "здорово",
    "салют",
    "hi",
    "hello",
    "дароу",
}
THANKS_TOKENS = {"спасибо", "благодарю", "спс"}
BYE_TOKENS = {"пока", "до свидания", "бай"}


def _phrase_intent(phrase: str) -> Intent:
    if phrase in GREETING_TOKENS:
        return Intent.GREETING
    if phrase in THANKS_TOKENS:
        return Intent.THANKS
    return Intent.BYE


class IntentDetector:
    @staticmethod
    def detect(question: str) -> Intent:
        """Соц-намерение по короткой реплике (D1: эта ветка намеренно правила, а не модель).

        Пунктуация и обращения не должны ломать совпадение: «здравствуйте!», «ну привет».
        """
        import re

        flat = re.sub(r"[^\w\s]", " ", question.lower())
        tokens = [t for t in flat.split() if t]
        phrase = " ".join(tokens)
        if not tokens:
            return Intent.QUESTION
        if phrase in GREETING_TOKENS or phrase in THANKS_TOKENS or phrase in BYE_TOKENS:
            return _phrase_intent(phrase)
        # короткая реплика-приветствие с мусором вокруг («ну привет», «ой спасибо»)
        if len(tokens) <= 3:
            for intent, table in (
                (Intent.BYE, BYE_TOKENS),
                (Intent.THANKS, THANKS_TOKENS),
                (Intent.GREETING, GREETING_TOKENS),
            ):
                if any(t in table for t in tokens):
                    return intent
        return Intent.QUESTION

    @staticmethod
    def already_greeted(history: Sequence[Turn]) -> bool:
        """Проверяет, было ли уже приветствие в ответах ассистента (токены без пунктуации)."""
        import re

        greeting_words = {"привет", "здравствуйте", "добрый день", "добрый вечер"}
        for turn in history:
            if turn.role != "assistant":
                continue
            words = set(re.findall(r"\w+", turn.content.lower()))
            if any(word in greeting_words for word in words):
                return True
        return False
