"""Генерация ответа по контексту. LLM — порт, промпт — константа.

Промпт жёстко требует отвечать ТОЛЬКО по контексту и, если ответа нет,
вернуть ровно NO_ANSWER. Gate (answer_gate.gate) трактует NO_ANSWER как
Grounding.NOT_ANSWERABLE и клиент получает «Не знаю».
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ..core.config import Settings

NO_ANSWER_MARKER: str = "NO_ANSWER"

SYSTEM_INSTRUCTION: str = (
    "Ты — ассистент, который отвечает на вопросы, используя ТОЛЬКО "
    "предоставленный контекст. Не добавляй фактов вне контекста. Если "
    f"контекста недостаточно, ответь ровно одним словом: {NO_ANSWER_MARKER}. "
    "Отвечай кратко и по существу."
)


@runtime_checkable
class LLMPort(Protocol):
    """Порт LLM: один вызов, возвращает текст ответа."""

    def complete(self, system: str, user: str) -> str: ...


def build_user_prompt(question: str, context: Sequence[str]) -> str:
    joined = "\n\n".join(part.strip() for part in context if part.strip())
    return f"Контекст:\n{joined}\n\nВопрос: {question.strip()}\n\nОтвет:"


class AnswerGenerator:
    """Собирает промпт и дергает LLM. Промпт-константа, temperature=0."""

    def __init__(self, llm: LLMPort, settings: Settings) -> None:
        self._llm = llm
        self._settings = settings

    def generate(self, question: str, context: Sequence[str]) -> str:
        if not question.strip():
            raise ValueError("Пустой вопрос")
        if not context:
            return NO_ANSWER_MARKER
        user = build_user_prompt(question, context)
        raw = self._llm.complete(SYSTEM_INSTRUCTION, user)
        return normalize(raw)


def normalize(raw: str) -> str:
    """Трим и защита: пусто -> NO_ANSWER; маркер оставляем как есть."""
    text = raw.strip()
    if not text:
        return NO_ANSWER_MARKER
    return text
