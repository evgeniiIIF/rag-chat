"""Генерация ответа по контексту с учётом истории диалога. LLM — порт, промпт — константа."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ..core.config import Settings
from ..models.turn import Turn

NO_ANSWER_MARKER: str = "NO_ANSWER"

SYSTEM_INSTRUCTION: str = (
    "Ты — вежливый ассистент по банкротству, ведёшь живой диалог с пользователем.\n"
    "Правила:\n"
    "1. Лаконичность: 1–3 предложения, без воды и повторов. Отвечай по делу.\n"
    "2. Учитывай предыдущие реплики: не здоровайся повторно; ссылайся на уже сказанное "
    "(город, сумму долга, имущество).\n"
    "3. Используй ТОЛЬКО факты из предоставленного контекста. Если фактов не хватает — "
    "честно скажи и задай 1 уточняющий вопрос по теме, не выдумывай.\n"
    "4. Если вопрос по теме и в контексте есть информация — ответь, обобщи по смыслу.\n"
    "5. Если ответ отрицательный (например, «не работаем в X»), добавь позитивную альтернативу из контекста.\n"
    "6. Если вопрос СОВЕРШЕННО не по теме и в контексте нет ни слова — верни ровно одно слово: NO_ANSWER.\n"
    "7. Не выдумывай факты.\n"
)


@runtime_checkable
class LLMPort(Protocol):
    def complete(self, system: str, user: str) -> str: ...


def _format_history(history: Sequence[Turn]) -> str:
    if not history:
        return ""
    lines: list[str] = []
    for turn in history:
        role = "Пользователь" if turn.role == "user" else "Ассистент"
        lines.append(f"{role}: {turn.content.strip()}")
    return "\n".join(lines)


def build_user_prompt(
    question: str,
    context: Sequence[str],
    history: Sequence[Turn] = (),
) -> str:
    joined = "\n\n".join(part.strip() for part in context if part.strip())
    dialog = _format_history(history)
    dialog_block = f"История диалога:\n{dialog}\n\n" if dialog else ""
    return f"{dialog_block}Контекст:\n{joined}\n\nВопрос: {question.strip()}\n\nОтвет:"


class AnswerGenerator:
    def __init__(self, llm: LLMPort, settings: Settings) -> None:
        self._llm = llm
        self._settings = settings

    def generate(
        self,
        question: str,
        context: Sequence[str],
        history: Sequence[Turn] = (),
    ) -> str:
        if not question.strip():
            raise ValueError("Пустой вопрос")
        if not context:
            return NO_ANSWER_MARKER
        user = build_user_prompt(question, context, history)
        raw = self._llm.complete(SYSTEM_INSTRUCTION, user)
        return normalize(raw)


def normalize(raw: str) -> str:
    text = raw.strip()
    if not text:
        return NO_ANSWER_MARKER
    return text
