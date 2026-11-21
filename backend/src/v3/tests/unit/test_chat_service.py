"""Тесты сценария чата: граф целиком, артефакты запроса, отказ без вызова модели."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import SecretStr

from core.config import Settings
from domain.models import Chunk, RetrievedChunk
from infrastructure.artifacts import read_json
from infrastructure.llm import AnswerDraft
from schemas.chat import ChatRequest, Turn
from services.chat_service import ChatService


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        api_key=SecretStr("test"),
        artifacts_dir=tmp_path / "artifacts",
        retriever_k=3,
        score_threshold=0.35,
    )


def make_chunk(order: int = 0) -> Chunk:
    return Chunk(
        id=f"doc.docx-{order:04d}",
        source="doc.docx",
        order=order,
        paragraph_start=order + 1,
        paragraph_end=order + 1,
        text="Берём в процедуру только с суммой от 350 000 рублей.",
    )


def make_hit(score: float) -> RetrievedChunk:
    return RetrievedChunk(chunk=make_chunk(), score=score, rank=1)


class FakeInvoke:
    def __init__(self, draft: AnswerDraft) -> None:
        self.draft = draft
        self.calls = 0

    def __call__(self, messages: list[Any]) -> AnswerDraft:
        self.calls += 1
        return self.draft


def test_ask_returns_grounded_answer_with_sources(tmp_path: Path) -> None:
    invoke = FakeInvoke(AnswerDraft(answer="От 350 000 рублей.", grounded=True, used_chunk_ids=["doc.docx-0000"]))
    settings = make_settings(tmp_path)
    service = ChatService(settings, search=lambda question, k: [make_hit(0.9)], invoke=invoke)

    response = service.ask(ChatRequest(question="С какой суммой берут?"))

    assert response.grounded is True
    assert response.answer == "От 350 000 рублей."
    assert response.top_score == 0.9
    assert response.sources[0].source == "doc.docx"
    assert invoke.calls == 1
    request_dirs = list(settings.artifacts_dir.iterdir())
    assert len(request_dirs) == 1
    assert read_json(request_dirs[0] / "retrieved.json")[0]["score"] == 0.9


def test_ask_refuses_without_calling_model(tmp_path: Path) -> None:
    invoke = FakeInvoke(AnswerDraft(answer="не должен вызваться", grounded=True, used_chunk_ids=[]))
    settings = make_settings(tmp_path)
    service = ChatService(settings, search=lambda question, k: [make_hit(0.1)], invoke=invoke)

    response = service.ask(ChatRequest(question="Что с гипопотамами?"))

    assert response.grounded is False
    assert response.sources == []
    assert response.top_score == 0.1
    assert invoke.calls == 0
    request_dirs = list(settings.artifacts_dir.iterdir())
    assert not (request_dirs[0] / "prompt.json").exists()


def test_ask_uses_request_k(tmp_path: Path) -> None:
    seen: list[int] = []

    def search(question: str, k: int) -> list[RetrievedChunk]:
        seen.append(k)
        return [make_hit(0.9)]

    invoke = FakeInvoke(AnswerDraft(answer="От 350 000 рублей.", grounded=True, used_chunk_ids=["doc.docx-0000"]))
    service = ChatService(make_settings(tmp_path), search=search, invoke=invoke)

    service.ask(ChatRequest(question="вопрос", k=7))

    assert seen == [7]


def test_ask_refuses_when_no_candidates(tmp_path: Path) -> None:
    invoke = FakeInvoke(AnswerDraft(answer="нет", grounded=True, used_chunk_ids=[]))
    service = ChatService(make_settings(tmp_path), search=lambda question, k: [], invoke=invoke)

    response = service.ask(ChatRequest(question="вопрос"))

    assert response.grounded is False
    assert response.top_score == 0.0


def test_history_from_request_restores_empty_thread(tmp_path: Path) -> None:
    """Сервис перезапущен (чекпойнтер пуст) — история берётся из тела запроса."""
    seen: list[list[Any]] = []

    def invoke(messages: list[Any]) -> AnswerDraft:
        seen.append(messages)
        return AnswerDraft(answer="От 350 000 рублей.", grounded=True, used_chunk_ids=["doc.docx-0000"])

    service = ChatService(make_settings(tmp_path), search=lambda question, k: [make_hit(0.9)], invoke=invoke)

    service.ask(
        ChatRequest(
            question="а что там есть?",
            session_id="client-1",
            history=[Turn(role="user", content="какой суммой берут?"), Turn(role="assistant", content="от 350к")],
        )
    )

    roles = [message.type for message in seen[0]]
    assert roles == ["system", "human", "ai", "human"]


def test_same_session_does_not_repeat_history(tmp_path: Path) -> None:
    """Второй вопрос той же сессии не дублирует историю из запроса: она уже в чекпойнтере."""
    seen: list[list[Any]] = []

    def invoke(messages: list[Any]) -> AnswerDraft:
        seen.append(messages)
        return AnswerDraft(answer="От 350 000 рублей.", grounded=True, used_chunk_ids=["doc.docx-0000"])

    service = ChatService(make_settings(tmp_path), search=lambda question, k: [make_hit(0.9)], invoke=invoke)
    history = [Turn(role="user", content="первый вопрос"), Turn(role="assistant", content="первый ответ")]
    service.ask(ChatRequest(question="второй вопрос", session_id="client-1", history=history))
    service.ask(ChatRequest(question="третий вопрос", session_id="client-1", history=history))

    contents = [str(message.content) for message in seen[1]]
    # история из тела запроса не дублируется: в промпте она ровно один раз
    assert contents.count("первый вопрос") == 1
    assert contents[1:3] == ["первый вопрос", "первый ответ"]
    assert contents[-1].startswith("Вопрос: третий вопрос")
