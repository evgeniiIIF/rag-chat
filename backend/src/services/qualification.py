"""Проверка фактов клиента по условиям приёма (цепочка chat_v2, итерация 3, узел 21).

Чистый код без обращений к модели и без знаний предметной области: условия (метки, порог,
перечень исключений) приходят из корпуса через TopicsMap, значения фактов — из TurnAnalyzer.
Нет значения или формат не распознан → UNKNOWN (диалог продолжается вопросом), а не отказ.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from ..models.criteria import Criterion, CriterionKind, CriterionResult, Status, Verdict

MIN_LABEL_CHARS: int = 5
STEM_CHARS: int = 5

# Родовые слова типов территорий: сами по себе ничего не различают («Республика Х» vs «Республика Y»).
GENERIC_WORDS: frozenset[str] = frozenset(
    {"республика", "область", "край", "округ", "автономный", "автономная", "народная", "город"}
)

_CURRENCY = re.compile(r"(?:₽|руб(?:\.|л\w*)?|р\.?)$")
_PLAIN_NUMBER = re.compile(r"\d+")
_GROUPED_NUMBER = re.compile(r"\d{1,3}(?:[.,]\d{3})+")
_WORD = re.compile(r"\w+")


def normalize(text: str) -> str:
    return " ".join(text.lower().replace("ё", "е").split())


def same_label(left: str, right: str) -> bool:
    """Одна и та же метка: совпадение или вхождение (короткая сторона не короче MIN_LABEL_CHARS)."""
    a, b = normalize(left), normalize(right)
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return bool(short) and (short == long_ or (len(short) >= MIN_LABEL_CHARS and short in long_))


def parse_amount(value: str) -> int | None:
    """Целое число рублей из строки формата «310000», «310 000 ₽», «1.500.000»; иначе None.

    Анализатор обязан отдавать сумму цифрами; «310к» или «1,5 млн» здесь не угадываем (UNKNOWN).
    """
    text = normalize(value.replace("\u00a0", " "))
    text = _CURRENCY.sub("", text).strip().replace(" ", "")
    if _PLAIN_NUMBER.fullmatch(text):
        return int(text)
    if _GROUPED_NUMBER.fullmatch(text):
        return int(re.sub(r"[.,]", "", text))
    return None


def _stems(text: str) -> set[str]:
    words = [w for w in _WORD.findall(normalize(text)) if w not in GENERIC_WORDS]
    return {w[:STEM_CHARS] for w in words}


def _same_value(value: str, excluded: str) -> bool:
    a, b = _stems(value), _stems(excluded)
    if a and b:
        return bool(a & b)
    return normalize(value) == normalize(excluded)


def _value_of(criterion: Criterion, facts: Mapping[str, str]) -> str:
    for key, value in facts.items():
        if same_label(criterion.label, key):
            return str(value).strip()
    return ""


def _check(criterion: Criterion, value: str) -> CriterionResult:
    if not value:
        return CriterionResult(criterion, Status.UNKNOWN)
    if criterion.kind is CriterionKind.MIN_AMOUNT:
        amount = parse_amount(value)
        if amount is None or criterion.min_rub <= 0:
            return CriterionResult(criterion, Status.UNKNOWN, value)
        status = Status.PASS if amount >= criterion.min_rub else Status.FAIL
        return CriterionResult(criterion, status, value)
    if criterion.kind is CriterionKind.EXCLUDED_VALUES:
        hit = any(_same_value(value, item) for item in criterion.excluded)
        return CriterionResult(criterion, Status.FAIL if hit else Status.PASS, value)
    return CriterionResult(criterion, Status.UNKNOWN, value)


def evaluate(criteria: Sequence[Criterion], facts: Mapping[str, str]) -> Verdict:
    """Факты клиента → вердикт по каждому условию (порядок условий сохраняется)."""
    return Verdict(results=tuple(_check(c, _value_of(c, facts)) for c in criteria))


def _money(amount: int) -> str:
    return f"{amount:,}".replace(",", " ")


def _line(result: CriterionResult) -> str:
    label, value = result.criterion.label, result.value
    if result.status is Status.PASS:
        return f"{label}: {value} — подходит"
    if result.status is Status.FAIL:
        if result.criterion.kind is CriterionKind.MIN_AMOUNT:
            return f"{label}: {value} — ниже минимума, не подходит"
        return f"{label}: {value} — входит в перечень неподходящих, не подходит"
    return f"{label}: ещё не известно"


def describe(verdict: Verdict) -> str:
    """Текст блока «Проверка условий» для генератора: факт от кода, не мнение модели."""
    lines = [_line(result) for result in verdict.results]
    for result in verdict.results:
        criterion = result.criterion
        if criterion.kind is CriterionKind.MIN_AMOUNT and criterion.min_rub > 0:
            lines.append(f"Для условия «{criterion.label}» минимум: {_money(criterion.min_rub)} ₽")
        if criterion.kind is CriterionKind.EXCLUDED_VALUES and criterion.excluded:
            lines.append(f"Для условия «{criterion.label}» не подходят значения: " + "; ".join(criterion.excluded))
    return "\n".join(lines)
