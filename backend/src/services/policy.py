"""Политика: Analysis + Verdict → действие на этот ход (цепочка chat_v2, узел 13).

В коде только ВЫБОР действия. Смысл реплики, факты и формулировки — у модели (D2), проверка
условий приёма — у Qualification (узел 21). Цель диалога: выяснить условия приёма, подходящего
клиента довести до консультации юриста, неподходящему вежливо объяснить.

Порядок: clarify → off_kb (с возвратом к цели) → не подходит → подходит → вопрос по первому
неизвестному условию (каждый ход, пока условие неизвестно: клиент не уводит диалог).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from ..models.analysis import Analysis, Scope, Style
from ..models.criteria import Overall, Verdict


class Action(StrEnum):
    """Чем ассистент занят в этом ходу."""

    ANSWER = "answer"  # ответить по найденному контексту (условий приёма в корпусе нет)
    ASK_ONE = "ask_one"  # ответить и задать РОВНО один вопрос по неизвестному условию
    HANDOFF = "handoff"  # клиент подходит: согласовать время консультации
    DISQUALIFY = "disqualify"  # клиент не подходит: вежливо объяснить, не окончательно
    DECLINE_OFFTOPIC = "decline_offtopic"  # темы нет в корпусе: коротко и обратно к цели
    REPHRASE = "rephrase"  # клиент не понял: переформулировать простым языком


@dataclass(frozen=True)
class Decision:
    action: Action
    ask_about: str = ""  # о чём спросить / к чему вернуть разговор
    pending: Sequence[str] = field(default_factory=tuple)
    style: Style = Style.EXPLAIN


class Policy:
    """Чистое дерево решений. Без побочных эффектов и обращений к модели."""

    def decide(self, analysis: Analysis, verdict: Verdict) -> Decision:
        style = analysis.style

        if analysis.scope is Scope.CLARIFY:
            return Decision(action=Action.REPHRASE, style=style)

        if not verdict.has_criteria:
            return self._without_criteria(analysis)

        unknown = verdict.first_unknown
        steer = unknown.label if unknown is not None else ""

        if analysis.scope is Scope.OFF_KB and not analysis.wants_consultation:
            return Decision(action=Action.DECLINE_OFFTOPIC, ask_about=steer, style=style)

        overall = verdict.overall
        if overall is Overall.DISQUALIFIED:
            return Decision(action=Action.DISQUALIFY, style=style)
        if overall is Overall.QUALIFIED:
            return Decision(action=Action.HANDOFF, style=style)
        return Decision(action=Action.ASK_ONE, ask_about=steer, pending=(steer,), style=style)

    def _without_criteria(self, analysis: Analysis) -> Decision:
        """Условий в корпусе не нашлось: прежнее поведение (консультация / вне темы / ответ)."""
        style = analysis.style
        if analysis.wants_consultation:
            return Decision(action=Action.HANDOFF, style=style)
        if analysis.scope is Scope.OFF_KB:
            return Decision(action=Action.DECLINE_OFFTOPIC, style=style)
        return Decision(action=Action.ANSWER, style=style)
