"""Достаточна ли выдача поиска, чтобы вообще звать генератор (цепочка chat_v2, узел 12).

Только числовое условие по верхнему скору гибридного поиска: порог берётся из конфига
(SCORE_THRESHOLD), а не зашит в код. «Понял ли модель ответ по контексту» решает уже
генератор через маркер NO_ANSWER (узел 14→15) — отдельного третьего вызова модели нет
(решение D5: два вызова на ход: анализ + ответ).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..models.retrieved import RetrievedChunk

REASON_EMPTY: str = "empty"
REASON_BELOW_THRESHOLD: str = "below_threshold"
REASON_OK: str = "ok"


@dataclass(frozen=True)
class Relevance:
    """Вердикт по выдаче поиска."""

    enough: bool
    top_score: float
    reason: str

    @property
    def is_ok(self) -> bool:
        return self.reason == REASON_OK


def _top(hits: Sequence[RetrievedChunk]) -> float:
    return max((hit.score for hit in hits), default=0.0)


class RelevanceGate:
    def __init__(self, threshold: float) -> None:
        if threshold < 0.0 or threshold > 1.0:
            raise ValueError("порог релевантности должен быть в диапазоне [0, 1]")
        self._threshold = threshold

    @property
    def threshold(self) -> float:
        return self._threshold

    def judge(self, hits: Sequence[RetrievedChunk]) -> Relevance:
        top = _top(hits)
        if not hits:
            return Relevance(enough=False, top_score=0.0, reason=REASON_EMPTY)
        if top < self._threshold:
            return Relevance(enough=False, top_score=top, reason=REASON_BELOW_THRESHOLD)
        return Relevance(enough=True, top_score=top, reason=REASON_OK)
