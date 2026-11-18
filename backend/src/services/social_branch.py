"""Соц-реплики (цепочка chat_v2, узел 19). Хардкод этой ветки зафиксирован решением D1.

Словарь намерений (IntentDetector) остаётся правилом, но строки ответов — таблица
констант: короткие, без «простыней», одна реплика = одна строка (критерий A3).
"""

from __future__ import annotations

from collections.abc import Sequence

from ..models.turn import Turn
from .intent_detector import Intent, IntentDetector

GREETING_FIRST: str = "Привет! Я ассистент по банкротству. Чем могу помочь?"
GREETING_REPEAT: str = "Мы уже на связи. Расскажите о вашей ситуации — чем помочь?"
THANKS_REPLY: str = "Пожалуйста! Если есть ещё вопросы — спрашивайте."
BYE_REPLY: str = "До свидания! Если понадобится помощь — обращайтесь."


class SocialBranch:
    """Отдаёт готовую соц-реплику либо None, если реплика деловая (узел 19 ─► 07)."""

    @staticmethod
    def replica(question: str, history: Sequence[Turn]) -> str | None:
        intent = IntentDetector.detect(question)
        if intent is Intent.GREETING:
            return GREETING_REPEAT if IntentDetector.already_greeted(history) else GREETING_FIRST
        if intent is Intent.THANKS:
            return THANKS_REPLY
        if intent is Intent.BYE:
            return BYE_REPLY
        return None
