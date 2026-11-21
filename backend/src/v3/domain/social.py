"""Соц-реплики как правило, а не модель (решение D1, перенесено из v2).

Сравнение — только полное совпадение нормализованной реплики: «приветствие в суде» — вопрос,
«здравствуйте, хочу списать долги» — тоже деловая реплика. Словари лежат в `core/behavior.py`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from enum import Enum, auto

from langchain_core.messages import BaseMessage

from core.behavior import (
    BYE_TOKENS,
    GREETING_PHRASES,
    GREETING_TOKENS,
    GREETING_WORDS,
    LEADING_FILLERS,
    THANKS_PHRASES,
    THANKS_TOKENS,
)

_PUNCT = re.compile(r"[^\w\s]")


class Intent(Enum):
    """Намерение реплики: соц-ветка или деловой вопрос."""

    GREETING = auto()
    THANKS = auto()
    BYE = auto()
    QUESTION = auto()


def normalize(question: str) -> str:
    """Реплика → сравнимое значение: регистр/пунктуация/ё сняты, ведущие филлеры убраны."""
    flat = _PUNCT.sub(" ", question.lower().replace("ё", "е"))
    tokens = [token for token in flat.split() if token]
    while tokens and tokens[0] in LEADING_FILLERS:
        tokens.pop(0)
    return " ".join(tokens)


def detect(question: str) -> Intent:
    """Соц-намерение строго по полному совпадению нормализованной реплики."""
    phrase = normalize(question)
    if not phrase:
        return Intent.QUESTION
    if phrase in BYE_TOKENS:
        return Intent.BYE
    if phrase in THANKS_TOKENS or phrase in THANKS_PHRASES:
        return Intent.THANKS
    if phrase in GREETING_TOKENS or phrase in GREETING_PHRASES:
        return Intent.GREETING
    return Intent.QUESTION


def already_greeted(history: Sequence[BaseMessage]) -> bool:
    """Здоровался ли ассистент раньше: важно, чтобы повтор не был тем же текстом."""
    for message in history:
        if message.type != "ai":
            continue
        words = set(_PUNCT.sub(" ", str(message.content).lower().replace("ё", "е")).split())
        if words & GREETING_WORDS:
            return True
    return False
