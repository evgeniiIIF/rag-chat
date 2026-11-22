"""Интеграционный тест визуализации: страница рисует граф самого LangGraph."""

from __future__ import annotations

from base64 import b64encode
from pathlib import Path
from typing import Any, cast

from api.graph import graph_mermaid, graph_page
from domain.models import RetrievedChunk
from graph.build import build_graph
from infrastructure.llm import Prompt
from services.chat_service import ChatService

NODES = ("greet", "extract", "retrieve", "answer")


class FakeService:
    """Носитель поля graph: роутеры читают только его."""

    def __init__(self, compiled: Any) -> None:
        self.graph = compiled


def make_graph(artifacts_dir: Path) -> Any:
    def search(question: str, k: int) -> list[RetrievedChunk]:
        return []

    def answer(prompt: Prompt) -> str:
        return "ок"

    return build_graph(search=search, answer_fn=answer, threshold=0.35, artifacts_dir=artifacts_dir)


def make_service(artifacts_dir: Path) -> ChatService:
    return cast(ChatService, FakeService(make_graph(artifacts_dir)))


def test_mermaid_matches_the_graph(tmp_path: Path) -> None:
    source = graph_mermaid(make_service(tmp_path))

    assert "graph TD" in source
    for node in NODES:
        assert node in source


def test_page_renders_that_same_text(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    page = graph_page(service)

    assert 'id="graph"' in page
    assert "mermaid.min.js" in page
    assert b64encode(graph_mermaid(service).encode("utf-8")).decode("ascii") in page


def test_page_has_no_hand_written_sections(tmp_path: Path) -> None:
    page = graph_page(make_service(tmp_path))

    assert "<table" not in page
    assert "<details" not in page
    assert "<h1" not in page
