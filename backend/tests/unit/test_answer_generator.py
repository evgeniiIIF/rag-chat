from __future__ import annotations

import pytest

from src.core.config import Settings
from src.services.answer_generator import (
    NO_ANSWER_MARKER,
    SYSTEM_INSTRUCTION,
    AnswerGenerator,
    build_user_prompt,
    normalize,
)


class _FakeLLM:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.reply


def _settings() -> Settings:
    return Settings(API_KEY="dummy")


def test_empty_context_returns_marker_without_llm() -> None:
    llm = _FakeLLM("ignored")
    gen = AnswerGenerator(llm, _settings())
    assert gen.generate("q?", []) == NO_ANSWER_MARKER
    assert llm.calls == []


def test_empty_question_rejected() -> None:
    gen = AnswerGenerator(_FakeLLM("x"), _settings())
    with pytest.raises(ValueError, match="Пустой вопрос"):
        gen.generate("  ", ["ctx"])


def test_passes_system_prompt_and_context() -> None:
    llm = _FakeLLM("ответ")
    gen = AnswerGenerator(llm, _settings())
    out = gen.generate("Кто Иван?", ["Иван — царь."])
    assert out == "ответ"
    assert len(llm.calls) == 1
    system, user = llm.calls[0]
    assert system == SYSTEM_INSTRUCTION
    assert "Иван — царь." in user
    assert "Вопрос: Кто Иван?" in user


def test_marker_preserved_from_llm() -> None:
    gen = AnswerGenerator(_FakeLLM(NO_ANSWER_MARKER), _settings())
    assert gen.generate("q?", ["ctx"]) == NO_ANSWER_MARKER


def test_whitespace_becomes_marker() -> None:
    gen = AnswerGenerator(_FakeLLM("   "), _settings())
    assert gen.generate("q?", ["ctx"]) == NO_ANSWER_MARKER


def test_build_user_prompt_ignores_blank_context_parts() -> None:
    user = build_user_prompt("q?", ["a", "   ", "b"])
    assert "a" in user and "b" in user
    assert user.count("\n\n\n") == 0


def test_normalize_trim() -> None:
    assert normalize("  hi  ") == "hi"
