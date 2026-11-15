"""Composition root: порты + контейнер. Собирается в main.py lifespan."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ..models.retrieved import RetrievedChunk
from ..models.turn import Turn
from .config import Settings, get_settings


@runtime_checkable
class RetrieverPort(Protocol):
    def search(self, question: str, k: int) -> list[RetrievedChunk]: ...


@runtime_checkable
class GeneratorPort(Protocol):
    def generate(self, question: str, context: list[str]) -> str: ...


@runtime_checkable
class CondenserPort(Protocol):
    def standalone(self, question: str, history: Sequence[Turn]) -> str: ...


class DIContainer:
    """Собирается в main.py lifespan. Поля — порты, реальные — с шага 10."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings: Settings = settings or get_settings()
        self.retriever: RetrieverPort | None = None
        self.generator: GeneratorPort | None = None
        self.condenser: CondenserPort | None = None
