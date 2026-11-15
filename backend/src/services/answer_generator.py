"""Генерация ответа по контексту. LLM — порт, промпт — константа."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ..core.config import Settings

NO_ANSWER_MARKER: str = "NO_ANSWER"

SYSTEM_INSTRUCTION: str = (
    "Ты — вежливый ассистент по банкротству. Используй ТОЛЬКО факты из предоставленного контекста.\n"
    "Правила:\n"
    "1. Отвечай красиво, понятно и по делу. Если в контексте есть факты, но они разбросаны — собери их в логичный ответ.\n"
    "2. Если вопрос по теме банкротства и в контексте есть хоть какая-то информация — ответь, даже если нет дословного определения. Обобщи по смыслу.\n"
    "3. Если ответ отрицательный (например, «не работаем в X»), добавь позитивную альтернативу из контекста (например, «зато работаем в 63 регионах»).\n"
    "4. Если вопрос СОВЕРШЕННО не по теме (политика, погода, другие науки) и в контексте нет ни слова об этом — верни ровно одно слово: NO_ANSWER.\n"
    "5. Не выдумывай факты, которых нет в контексте.\n"
)

@runtime_checkable
class LLMPort(Protocol):
    def complete(self, system: str, user: str) -> str: ...

def build_user_prompt(question: str, context: Sequence[str]) -> str:
    joined = "\n\n".join(part.strip() for part in context if part.strip())
    return f"Контекст:\n{joined}\n\nВопрос: {question.strip()}\n\nОтвет:"

class AnswerGenerator:
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
    text = raw.strip()
    if not text:
        return NO_ANSWER_MARKER
    return text
