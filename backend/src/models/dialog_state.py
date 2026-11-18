"""Состояние диалога (цепочка chat_v2, узел 10): деловые факты + о чём уже спрашивали.

Неизменяемое значение (VO). Наполняется ТОЛЬКО тем, что вернула модель (TurnAnalyzer):
в этом модуле нет ни словарей тем, ни регулярок — сравнение топиков только нормализацией
строки, которую вернула модель (решение D2).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


def _norm(topic: str) -> str:
    """Нормализация топика: нижний регистр, ё=е, схлопнутые пробелы."""
    return " ".join(topic.lower().replace("ё", "е").split())


@dataclass(frozen=True)
class DialogState:
    """Что уже известно о клиенте и о чём его уже спрашивали."""

    facts: Mapping[str, str]
    asked: frozenset[str]

    @classmethod
    def empty(cls) -> DialogState:
        return cls(facts={}, asked=frozenset())

    def merged(self, facts: Mapping[str, str] | None = None, asked: Iterable[str] = ()) -> DialogState:
        """Новое состояние = старое + вытащенное моделью (пустые значения не попадают)."""
        new_facts: dict[str, str] = dict(self.facts)
        for key, value in (facts or {}).items():
            clean_key, clean_value = key.strip(), value.strip()
            if clean_key and clean_value:
                new_facts[clean_key] = clean_value
        new_asked: set[str] = set(self.asked)
        for topic in asked:
            norm = _norm(topic)
            if norm:
                new_asked.add(norm)
        return DialogState(facts=new_facts, asked=frozenset(new_asked))

    def asked_about(self, topic: str) -> bool:
        """Спрашивали ли уже про этот топик (пересечение нормализованных строк)."""
        norm = _norm(topic)
        if not norm:
            return False
        return any(norm in known or known in norm for known in self.asked)

    def pending(self, missing: Iterable[str]) -> list[str]:
        """Топики, о которых ещё НЕ спрашивали (критерий A5: не повторяться)."""
        out: list[str] = []
        for topic in missing:
            clean = topic.strip()
            if clean and not self.asked_about(clean):
                out.append(clean)
        return out

    def as_prompt_block(self) -> str:
        """Блок «Что известно» для промпта; пусто — если фактов нет."""
        if not self.facts:
            return ""
        return "; ".join(f"{key}: {self.facts[key]}" for key in sorted(self.facts))

    def asked_as_prompt_block(self) -> str:
        """Блок «О чём уже спрашивали» для промпта."""
        if not self.asked:
            return ""
        return "; ".join(sorted(self.asked))
