"""Порт к LLM (цепочка chat_v2, узел 18).

Единственная точка, через которую доменные сервисы ходят в модель. Реализация —
langchain-адаптер в main.py (DI); сервисы зависят только от этого протокола.
Используют его: TurnAnalyzer (09), TopicsMap (08), AnswerGenerator (14).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMPort(Protocol):
    def complete(self, system: str, user: str) -> str: ...
