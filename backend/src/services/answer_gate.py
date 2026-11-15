"""Единственная точка принятия решения «Не знаю».

Два независимых условия:
1) top_score < threshold  -> нет релевантных чанков, LLM не зовём вовсе.
2) LLM вернул маркер NO_ANSWER -> контекста не хватило.

Оба ведут к Grounding.NOT_ANSWERABLE — вызывающая сторона отдаёт клиенту
{answer: "Не знаю", grounded=false}.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..core.config import Settings
from ..models.grounding import Grounding
from ..models.retrieved import RetrievedChunk

NO_ANSWER_MARKER: str = "NO_ANSWER"
NOT_ANSWERABLE_TEXT: str = "Не знаю"


def passes_threshold(hits: Sequence[RetrievedChunk], threshold: float) -> bool:
    """Порог по верхнему скору: пусто/top < τ -> False."""
    if not hits:
        return False
    return max(hit.score for hit in hits) >= threshold


def gate(
    hits: Sequence[RetrievedChunk],
    llm_answer: str | None,
    settings: Settings,
) -> Grounding:
    """Итоговый статус. llm_answer=None => LLM не звали (отсев по порогу)."""
    if not passes_threshold(hits, settings.score_threshold):
        return Grounding.NOT_ANSWERABLE
    if llm_answer is None:
        return Grounding.NOT_ANSWERABLE
    if llm_answer.strip() == NO_ANSWER_MARKER:
        return Grounding.NOT_ANSWERABLE
    if not llm_answer.strip():
        return Grounding.NOT_ANSWERABLE
    return Grounding.GROUNDED
