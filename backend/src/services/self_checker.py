"""Self Checker: второй вызов LLM проверяет, что ответ основан на контексте."""

from __future__ import annotations

from .answer_generator import LLMPort, NO_ANSWER_MARKER

CHECK_PROMPT = (
    "Ты — строгий валидатор. Проверь, подтверждается ли ответ контекстом.\n"
    "Если каждое утверждение в ответе есть в контексте — ответь YES.\n"
    "Если в ответе есть факты, которых нет в контексте — ответь NO.\n"
    "Выведи только YES или NO."
)


class SelfChecker:
    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    def check(self, question: str, context: str, answer: str) -> str:
        """Возвращает answer, если он подтверждён, иначе NO_ANSWER_MARKER."""
        if not answer or answer.strip() == NO_ANSWER_MARKER:
            return answer
        user = f"Контекст:\n{context}\n\nВопрос: {question}\n\nОтвет: {answer}\n\nПодтверждён?"
        try:
            verdict = self._llm.complete(CHECK_PROMPT, user).strip().upper()
            if "YES" in verdict:
                return answer
            return NO_ANSWER_MARKER
        except Exception:
            return answer  # при ошибке не ломаем, возвращаем как есть
