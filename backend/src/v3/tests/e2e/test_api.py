"""E2E тесты HTTP: контракт фронтенда, деградация без индекса, запуск lifespan."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from core.config import Settings
from domain.models import Chunk, RetrievedChunk
from infrastructure.llm import IntakeDraft, Prompt
from main import create_app
from services.chat_service import ChatService
from services.index_service import IndexService


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        api_key=SecretStr("test"),
        data_dir=tmp_path / "data",
        artifacts_dir=tmp_path / "artifacts",
        chroma_dir=tmp_path / "chroma",
    )


def make_chunk() -> Chunk:
    return Chunk(
        id="doc.docx-0000",
        source="doc.docx",
        order=0,
        paragraph_start=1,
        paragraph_end=1,
        text="Берём в процедуру только с суммой от 350 000 рублей.",
    )


def make_service(tmp_path: Path, *, score: float = 0.9) -> ChatService:
    def search(question: str, k: int) -> list[RetrievedChunk]:
        return [RetrievedChunk(chunk=make_chunk(), score=score, rank=1)]

    def answer(prompt: Prompt) -> str:
        return "От 350 000 рублей."

    def intake(question: str, history: list[Any]) -> IntakeDraft:
        return IntakeDraft(kind="question")

    return ChatService(make_settings(tmp_path), search=search, answer_fn=answer, intake=intake)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(make_settings(tmp_path), service=make_service(tmp_path))
    with TestClient(app) as test_client:
        yield test_client


def test_chat_returns_frontend_contract(client: TestClient) -> None:
    response = client.post("/api/chat", json={"question": "С какой суммой берут?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "От 350 000 рублей."
    assert payload["grounded"] is True
    assert payload["top_score"] == 0.9
    assert payload["sources"] == [
        {
            "source": "doc.docx",
            "paragraph_start": 1,
            "paragraph_end": 1,
            "text": "Берём в процедуру только с суммой от 350 000 рублей.",
        }
    ]


def test_chat_rejects_empty_question(client: TestClient) -> None:
    response = client.post("/api/chat", json={"question": ""})

    assert response.status_code == 422


def test_health_reports_ready(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_degraded_service_without_index(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))

    with TestClient(app) as client:
        health = client.get("/api/health")
        chat = client.post("/api/chat", json={"question": "вопрос"})

    assert health.status_code == 503
    assert health.json()["status"] == "degraded"
    assert "каталог документов не найден" in health.json()["reason"]
    assert chat.status_code == 503


def test_lifespan_builds_service_from_index(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class FakeIndex:
        def __init__(self, settings: Settings) -> None:
            self.settings = settings

        def ensure_index(self) -> None:
            self.ensured = True

        @property
        def chunks(self) -> list[Chunk]:
            return [make_chunk()]

        def search(self, question: str, k: int) -> list[RetrievedChunk]:
            return [RetrievedChunk(chunk=make_chunk(), score=0.9, rank=1)]

    def fake_answer(prompt: Prompt) -> str:
        return "От 350 000 рублей."

    monkeypatch.setattr("main.IndexService", FakeIndex)
    monkeypatch.setattr("main.build_answer_fn", lambda model: fake_answer)

    def fake_intake(question: str, history: list[Any]) -> IntakeDraft:
        return IntakeDraft(kind="question")

    monkeypatch.setattr("main.build_intake", lambda model: fake_intake)
    app = create_app(make_settings(tmp_path))

    with TestClient(app) as client:
        response = client.post("/api/chat", json={"question": "С какой суммой берут?"})
        assert isinstance(app.state.chat_service, ChatService)

    assert response.status_code == 200
    assert response.json()["grounded"] is True
    assert isinstance(IndexService, type)
