"""Query Rewriter: переписывание вопроса с учетом истории и резюме (LLM)."""

from __future__ import annotations

from collections.abc import Sequence
from ..models.turn import Turn
from .answer_generator import LLMPort

REWRITER_PROMPT = (
    "Given the following conversation history (and optional summary) and a follow-up question, "
    "rephrase the follow-up question to be a standalone question. "
    "If the question is already standalone, return it as is. "
    "Return ONLY the rewritten question, without any explanations."
)

class QueryRewriter:
    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    def rewrite(self, question: str, history: Sequence[Turn], summary: str | None = None) -> str:
        if not history and not summary:
            return question

        context_parts = []
        if summary:
            context_parts.append(f"Summary: {summary}")
        if history:
            history_text = "\n".join(f"{t.role}: {t.content}" for t in history)
            context_parts.append(f"Recent history:\n{history_text}")

        context = "\n\n".join(context_parts)
        user_prompt = f"{context}\n\nFollow-up: {question}\nStandalone question:"

        try:
            rewritten = self._llm.complete(REWRITER_PROMPT, user_prompt).strip()
            return rewritten if rewritten else question
        except Exception:
            return question
