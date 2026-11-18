"""Условия приёма клиента и вердикт по ним (цепочка chat_v2, итерация 3, узлы 08/21).

Условия извлекает из корпуса модель (TopicsMap). Здесь только неизменяемые значения:
метка условия, вид (минимум числа | перечень неподходящих значений) и результат проверки.
Слов предметной области в модуле нет.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CriterionKind(StrEnum):
    MIN_AMOUNT = "min_amount"  # значение должно быть не меньше порога min_rub
    EXCLUDED_VALUES = "excluded_values"  # значение не должно входить в перечень excluded


class Status(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"  # значения нет или формат не распознан


class Overall(StrEnum):
    NO_CRITERIA = "no_criteria"  # условий в корпусе не найдено: диалог без проверки
    DISQUALIFIED = "disqualified"  # хотя бы одно условие не выполнено
    QUALIFIED = "qualified"  # все условия выполнены
    PENDING = "pending"  # не хватает данных


@dataclass(frozen=True)
class Criterion:
    label: str
    kind: CriterionKind
    min_rub: int = 0
    excluded: tuple[str, ...] = ()


@dataclass(frozen=True)
class CriterionResult:
    criterion: Criterion
    status: Status
    value: str = ""


@dataclass(frozen=True)
class Verdict:
    """Итог проверки всех условий по известным фактам клиента."""

    results: tuple[CriterionResult, ...] = ()

    @property
    def has_criteria(self) -> bool:
        return bool(self.results)

    @property
    def overall(self) -> Overall:
        if not self.results:
            return Overall.NO_CRITERIA
        statuses = [result.status for result in self.results]
        if Status.FAIL in statuses:
            return Overall.DISQUALIFIED
        if Status.UNKNOWN in statuses:
            return Overall.PENDING
        return Overall.QUALIFIED

    @property
    def first_unknown(self) -> Criterion | None:
        for result in self.results:
            if result.status is Status.UNKNOWN:
                return result.criterion
        return None

    def summary(self) -> str:
        parts: list[str] = []
        for result in self.results:
            suffix = " (" + result.value + ")" if result.value else ""
            parts.append(result.criterion.label + "=" + result.status.value + suffix)
        return "; ".join(parts)
