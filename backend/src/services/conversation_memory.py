"""Управление историей диалога: скользящее окно + суммаризация (best practice)."""

from __future__ import annotations

from collections.abc import Sequence

from ..models.turn import Turn
from .answer_generator import LLMPort

SUMMARY_PROMPT = (
    "Суммируй следующий диалог в 2-3 предложениях, сохраняя ключевые факты и цели пользователя. "
    "Выведи только текст резюме."
)


class ConversationMemory:
    def __init__(self, llm: LLMPort, window_size: int = 6, summary_threshold: int = 10):
        self._llm = llm
        self._window_size = window_size
        self._summary_threshold = summary_threshold

    def get_processed_history(self, history: Sequence[Turn]) -> tuple[str | None, list[Turn]]:
        """Возвращает (summary, recent_history)."""
        if len(history) <= self._summary_threshold:
            # Если история короткая — просто скользящее окно
            return None, list(history[-self._window_size :])

        # Иначе — суммаризируем старые сообщения
        old_messages = history[: -self._window_size]
        recent = list(history[-self._window_size :])

        history_text = "\n".join(f"{t.role}: {t.content}" for t in old_messages)
        user_prompt = f"Диалог:\n{history_text}\n\nРезюме:"
        try:
            summary = self._llm.complete(SUMMARY_PROMPT, user_prompt).strip()
        except Exception:
            summary = None
        return summary, recent
