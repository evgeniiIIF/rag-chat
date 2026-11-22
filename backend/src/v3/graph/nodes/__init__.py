"""Узлы графа: greet → extract → (retrieve) → answer."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from domain.graph_state import GraphState

NodeResult = dict[str, Any]
NodeFn = Callable[[GraphState], NodeResult]
