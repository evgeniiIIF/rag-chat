"""Узлы графа: greet (готовый текст) → turn (один запрос модели)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from domain.graph_state import GraphState
from domain.models import RetrievedChunk

NodeResult = dict[str, Any]
NodeFn = Callable[[GraphState], NodeResult]
SearchFn = Callable[[str, int], Sequence[RetrievedChunk]]
