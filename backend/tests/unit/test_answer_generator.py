"""Unit: AnswerGenerator (цепочка chat_v2, узел 14). Контракт D3/A5/A7/D4 и сборка промпта."""

from __future__ import annotations

import pytest

from src.core.config import Settings
from src.models.analysis import Analysis, Style
from src.models.dialog_state import DialogState
from src.models.turn import Turn
from src.services.answer_generator import (
    HISTORY_TURN_CHARS,
    HISTORY_WINDOW,
    NO_ANSWER_MARKER,
    SYSTEM_INSTRUCTION,
    AnswerGenerator,
    build_user_prompt,
    normalize,
)
from src.services.policy import Action, Decision


class _FakeLLM:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.reply


def _settings() -> Settings:
    return Settings(API_KEY="dummy")


def _analysis(**kwargs: object) -> Analysis:
    data: dict[str, object] = {"scope": "in_kb", "question": "какой минимальный долг"}
    data.update(kwargs)
    return Analysis.model_validate(data)


def test_no_context_does_not_call_llm_for_answer() -> None:
    llm = _FakeLLM("ignored")
    gen = AnswerGenerator(llm, _settings())
    out = gen.generate("q?", [], Decision(action=Action.ANSWER), DialogState.empty(), _analysis())
    assert out == NO_ANSWER_MARKER
    assert llm.calls == []


def test_no_context_still_answers_for_off_topic_and_rephrase() -> None:
    """Вне темы и «не понял» контекст не нужен — иначе клиент получает «Не знаю» вместо ответа."""
    for action in (Action.DECLINE_OFFTOPIC, Action.REPHRASE, Action.HANDOFF):
        llm = _FakeLLM("короткая реплика")
        gen = AnswerGenerator(llm, _settings())
        assert gen.generate("про гипопотамов", [], Decision(action=action), DialogState.empty(), _analysis()) == (
            "короткая реплика"
        )
        assert len(llm.calls) == 1


def test_empty_question_rejected() -> None:
    gen = AnswerGenerator(_FakeLLM("x"), _settings())
    with pytest.raises(ValueError, match="Пустой вопрос"):
        gen.generate("  ", ["ctx"], Decision(action=Action.ANSWER), DialogState.empty(), _analysis())


def test_system_contract_forbids_invented_facts() -> None:
    assert "ТОЛЬКО из блока «Контекст»" in SYSTEM_INSTRUCTION
    assert "нельзя придумывать" in SYSTEM_INSTRUCTION.lower()
    assert "РОВНО ОДИН" in SYSTEM_INSTRUCTION or "ровно один" in SYSTEM_INSTRUCTION
    assert "NO_ANSWER" in SYSTEM_INSTRUCTION


def test_prompt_puts_context_first_and_keeps_state_blocks() -> None:
    state = DialogState.empty().merged({"сумма долга": "310 000 ₽"}, ["регион прописки"])
    prompt = build_user_prompt(
        "рассрочку на 310к платить не могу",
        ["берем в процедуру только с суммой от 350к"],
        Decision(action=Action.ASK_ONE, ask_about="состав долгов"),
        state,
        _analysis(),
    )
    assert prompt.index("Контекст:") < prompt.index("Вопрос клиента:")
    assert "берем в процедуру только с суммой от 350к" in prompt
    assert "сумма долга: 310 000 ₽" in prompt
    assert "О чём уже спрашивали:\nрегион прописки" in prompt
    assert "РОВНО ОДИН уточняющий вопрос по теме: состав долгов" in prompt


def test_action_specific_instructions() -> None:
    cases = {
        Action.DECLINE_OFFTOPIC: "НЕ пытайся угадать",
        Action.HANDOFF: "не продавай её заново",
        Action.REPHRASE: "максимально простыми словами",
        Action.ANSWER: "не обязателен",
    }
    for action, needle in cases.items():
        prompt = build_user_prompt("вопрос", ["контекст"], Decision(action=action), DialogState.empty(), _analysis())
        assert needle in prompt, action


def test_style_comes_from_analysis() -> None:
    prompt = build_user_prompt(
        "мне страшно",
        ["контекст"],
        Decision(action=Action.ANSWER),
        DialogState.empty(),
        _analysis(style=Style.REASSURE),
    )
    assert "ситуация решаемая" in prompt


def test_history_window_is_small_and_clipped() -> None:
    history = [Turn(role="assistant", content="д" * 900)] + [
        Turn(role="user", content=f"реплика {i}") for i in range(6)
    ]
    prompt = build_user_prompt("q", ["ctx"], Decision(action=Action.ANSWER), DialogState.empty(), _analysis(), history)
    assert "реплика 5" in prompt
    assert "реплика 3" not in prompt
    assert "д" * (HISTORY_TURN_CHARS + 1) not in prompt
    assert prompt.count("Ассистент:") <= HISTORY_WINDOW


def test_generate_sends_system_and_user_and_returns_text() -> None:
    llm = _FakeLLM("Минимум 350 тысяч.")
    out = AnswerGenerator(llm, _settings()).generate(
        "какой минимальный долг",
        ["берем в процедуру только с суммой от 350к"],
        Decision(action=Action.ANSWER),
        DialogState.empty(),
        _analysis(),
    )
    assert out == "Минимум 350 тысяч."
    assert llm.calls[0][0] == SYSTEM_INSTRUCTION


def test_marker_from_llm_is_preserved() -> None:
    out = AnswerGenerator(_FakeLLM(NO_ANSWER_MARKER), _settings()).generate(
        "q", ["ctx"], Decision(action=Action.ANSWER), DialogState.empty(), _analysis()
    )
    assert out == NO_ANSWER_MARKER


def test_normalize_blank_to_marker() -> None:
    assert normalize("   ") == NO_ANSWER_MARKER
    assert normalize("  текст \n") == "текст"
