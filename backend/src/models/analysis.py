"""Результат понимания одной реплики клиента (цепочка chat_v2, узел 09).

Модель возвращает JSON, он парсится в эту модель (parse-don't-validate). Никаких
regex/словарей: вся семантика — на стороне LLM-порта, здесь только типизированный контракт.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Scope(StrEnum):
    """Охват реплики относительно базы знаний."""

    IN_KB = "in_kb"  # вопрос/сообщение по теме корпуса
    OFF_KB = "off_kb"  # темы нет в корпусе (в т.ч. бессмыслица и опечатки)
    CLARIFY = "clarify"  # клиент не понял вопрос ассистента / просит проще


class Style(StrEnum):
    """Как отвечать по тону (A4/EQ), решает модель по реплике."""

    ONE_LINE = "one_line"  # коротко, по делу
    EXPLAIN = "explain"  # разобрать ситуацию
    REASSURE = "reassure"  ###показать, что ситуация решаемая


class Analysis(BaseModel):
    """Что модель поняла из реплики + что нужно сделать дальше."""

    model_config = ConfigDict(extra="ignore")

    scope: Scope = Scope.IN_KB
    question: str = Field("", description="самостоятельная формулировка запроса для поиска")
    facts: dict[str, str] = Field(default_factory=dict, description="что клиент сообщил")
    missing: list[str] = Field(default_factory=list, description="что ещё узнать для консультации")
    asked_already: list[str] = Field(default_factory=list, description="о чём уже спрашивали")
    wants_consultation: bool = Field(False, description="клиент согласен/готов к консультации")
    style: Style = Style.EXPLAIN

    @classmethod
    def fallback(cls, question: str) -> Analysis:
        """Аварийный вариант, когда модель не выдала валидный JSON.

        Считаем реплику деловой и ищем по её исходному тексту: это хуже, чем точный
        запрос, но не выдумывает факты и не ломает диалог.
        """
        return cls(scope=Scope.IN_KB, question=question.strip())
