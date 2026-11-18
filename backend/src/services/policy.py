"""Политика: Analysis + состояние диалога → действие на этот ход (цепочка chat_v2, узел 13).

В коде только ВЫБОР действия, как записано в цепочке. Формулировку вопроса, смысл темы,
критерии квалификации и согласие клиента на консультацию решает модель (TurnAnalyzer) — здесь
нет ни словарей, ни регулярок, ни стадий-FSM (решение D2).

Порядок: clarify → просьба о консультации → off_kb → критерии → ответ. Просьба о юристе никогда
не «вне темы»; пока критерии квалификации не собраны, консультацию не оформляем, а спрашиваем
следующий критерий (подготовка информации для юриста); собраны — договариваемся о времени.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from ..models.analysis import Analysis, Scope, Style
from ..models.dialog_state import DialogState


class Action(StrEnum):
    """Чем ассистент занят в этом ходу."""

    ANSWER = "answer"  # ответить по найденному контексту
    ASK_ONE = "ask_one"  # ответить и задать РОВНО один новый уточняющий вопрос (A5)
    HANDOFF = "handoff"  # критерии собраны, клиент готов: договориться о времени консультации
    DECLINE_OFFTOPIC = "decline_offtopic"  # темы нет в корпусе: коротко сказать об этом (D4)
    REPHRASE = "rephrase"  # клиент не понял: переформулировать простым языком


@dataclass(frozen=True)
class Decision:
    action: Action
    ask_about: str = ""  # о чём спросить (первый ещё не заданный критерий)
    pending: Sequence[str] = field(default_factory=tuple)
    style: Style = Style.EXPLAIN


class Policy:
    """Чистое дерево решений. Без побочных эффектов и обращений к модели."""

    def decide(self, analysis: Analysis, state: DialogState) -> Decision:
        style = analysis.style
        # A5: спрашиваем только про то, о чём ещё НЕ спрашивали
        pending = state.pending(analysis.missing)

        if analysis.scope is Scope.CLARIFY:
            return Decision(action=Action.REPHRASE, style=style)

        if analysis.wants_consultation:
            return self._consultation(pending, style)

        if analysis.scope is Scope.OFF_KB:
            return Decision(action=Action.DECLINE_OFFTOPIC, style=style)

        if pending:
            return self._ask(pending, style)

        return Decision(action=Action.ANSWER, style=style)

    def _consultation(self, pending: Sequence[str], style: Style) -> Decision:
        """Клиент просит консультацию: сначала недостающие критерии, потом время."""
        if pending:
            return self._ask(pending, style)
        return Decision(action=Action.HANDOFF, style=style)

    def _ask(self, pending: Sequence[str], style: Style) -> Decision:
        return Decision(action=Action.ASK_ONE, ask_about=pending[0], pending=tuple(pending), style=style)
