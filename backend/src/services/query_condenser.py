"""Сведение истории + текущего вопроса в один standalone-вопрос.

По умолчанию — детерминированное правило (без сети): если история пустая,
возвращаем вопрос как есть; иначе склеиваем последние N реплик в короткий
контекст. LLM-конденсация — опциональна (порт CondenserPort).
"""

from __future__ import annotations

from collections.abc import Sequence

from ..models.turn import Turn

DEFAULT_HISTORY_LIMIT: int = 6


class QueryCondenser:
    """Rule-based конденсация. Без сети — безопасно для unit-тестов."""

    def __init__(self, history_limit: int = DEFAULT_HISTORY_LIMIT) -> None:
        if history_limit < 0:
            raise ValueError("history_limit не может быть отрицательным")
        self._limit = history_limit

    def standalone(self, question: str, history: Sequence[Turn]) -> str:
        q = question.strip()
        if not q:
            raise ValueError("Пустой вопрос")
        if not history:
            return q
        recent = list(history)[-self._limit :]
        if not recent:
            return q
        parts: list[str] = []
        for turn in recent:
            prefix = "U:" if turn.role == "user" else "A:"
            parts.append(f"{prefix} {turn.content.strip()}")
        parts.append(f"Q: {q}")
        return " / ".join(parts)
