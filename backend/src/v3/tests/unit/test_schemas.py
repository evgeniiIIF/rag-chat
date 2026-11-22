"""Тесты HTTP-границ: валидация запроса и диапазоны ответа."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.chat import (
    ChatRequest,
    ChatResponse,
    ProfileSchema,
    SourceSchema,
    StateSchema,
    Turn,
)


def test_request_defaults() -> None:
    request = ChatRequest(question="С какой суммой берут?")

    assert request.history == []
    assert request.session_id is None
    assert request.k is None


def test_request_rejects_blank_question() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(question="")
    with pytest.raises(ValidationError):
        ChatRequest(question="   ".strip())


def test_request_rejects_long_question() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(question="в" * 2001)


def test_request_rejects_out_of_range_k() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(question="вопрос", k=0)
    with pytest.raises(ValidationError):
        ChatRequest(question="вопрос", k=11)


def test_request_limits_history() -> None:
    turns = [Turn(role="user", content="привет")] * 31

    with pytest.raises(ValidationError):
        ChatRequest(question="вопрос", history=turns)


def test_response_bounds_top_score() -> None:
    source = SourceSchema(source="doc.docx", paragraph_start=1, paragraph_end=2, text="фрагмент")

    state = StateSchema(filters_passed=False, retrieved=0, profile=ProfileSchema())
    response = ChatResponse(answer="ответ", sources=[source], grounded=True, top_score=0.5, state=state)

    assert response.sources[0].paragraph_end == 2
    with pytest.raises(ValidationError):
        ChatResponse(answer="ответ", sources=[], grounded=False, top_score=1.5, state=state)
