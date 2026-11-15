from __future__ import annotations

import pytest

from src.core.config import Settings
from src.models.chunk import Chunk, ParagraphSpan
from src.models.retrieved import RetrievedChunk
from src.models.turn import Turn
from src.schemas.chat import ChatRequest
from src.services.answer_gate import NOT_ANSWERABLE_TEXT
from src.services.answer_generator import NO_ANSWER_MARKER, AnswerGenerator
from src.services.chat_service import ChatService
from src.services.query_condenser import QueryCondenser


class _FakeRetriever:
    def __init__(self, hits: list[RetrievedChunk]) -> None:
        self._hits = hits
        self.calls: list[tuple[str, int]] = []

    def search(self, question: str, k: int) -> list[RetrievedChunk]:
        self.calls.append((question, k))
        return self._hits[:k]


class _FakeLLM:
    def __init__(self, reply: str) -> None:
        self.reply = reply

    def complete(self, system: str, user: str) -> str:
        return self.reply


def _settings() -> Settings:
    return Settings(API_KEY="dummy", SCORE_THRESHOLD=0.35, RETRIEVER_K=3)


def _hit(score: float, text: str = "Иван — царь.") -> RetrievedChunk:
    return RetrievedChunk(
        chunk=Chunk(source="КЦ.docx", text=text, span=ParagraphSpan(start=7, end=7)),
        score=score,
    )


def _svc(retriever: _FakeRetriever, llm_reply: str) -> ChatService:
    return ChatService(
        retriever=retriever,
        generator=AnswerGenerator(_FakeLLM(llm_reply), _settings()),
        condenser=QueryCondenser(),
        settings=_settings(),
    )


def test_grounded_response_includes_sources_and_span() -> None:
    svc = _svc(_FakeRetriever([_hit(0.9)]), "Иван — царь.")
    resp = svc.ask(ChatRequest(question="Кто Иван?"))
    assert resp.grounded is True
    assert resp.answer == "Иван — царь."
    assert len(resp.sources) == 1
    assert resp.sources[0].paragraph_start == 7
    assert resp.top_score == pytest.approx(0.9)


def test_not_answerable_below_threshold_no_llm_call() -> None:
    retriever = _FakeRetriever([_hit(0.05)])
    svc = _svc(retriever, "should not be used")
    resp = svc.ask(ChatRequest(question="q?"))
    assert resp.grounded is False
    assert resp.answer == NOT_ANSWERABLE_TEXT
    assert resp.sources == []


def test_not_answerable_when_llm_returns_marker() -> None:
    svc = _svc(_FakeRetriever([_hit(0.9)]), NO_ANSWER_MARKER)
    resp = svc.ask(ChatRequest(question="q?"))
    assert resp.grounded is False
    assert resp.answer == NOT_ANSWERABLE_TEXT


def test_condenser_receives_history() -> None:
    retriever = _FakeRetriever([_hit(0.9)])
    svc = _svc(retriever, "ok")
    svc.ask(
        ChatRequest(
            question="А он один?",
            history=[
                Turn(role="user", content="Кто Иван?"),
                Turn(role="assistant", content="Царь."),
            ],
        )
    )
    assert retriever.calls
    standalone, _k = retriever.calls[0]
    assert "Кто Иван?" in standalone
    assert "Q: А он один?" in standalone


def test_empty_hits_returns_not_answerable() -> None:
    svc = _svc(_FakeRetriever([]), "x")
    resp = svc.ask(ChatRequest(question="q?"))
    assert resp.grounded is False
    assert resp.top_score == 0.0
