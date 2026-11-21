"""Тесты адаптера модели: состав промпта, параметры клиента, структурный ответ."""

from __future__ import annotations

from typing import Any, ClassVar, cast

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import SecretStr

from core.config import Settings
from domain.models import Chunk
from infrastructure import llm as llm_module
from infrastructure.llm import (
    AnswerDraft,
    IntakeDraft,
    build_chat_model,
    build_condense,
    build_intake,
    build_messages,
    build_structured_model,
)


def make_settings() -> Settings:
    return Settings(api_key=SecretStr("test"))


def make_chunk(order: int = 0) -> Chunk:
    return Chunk(
        id=f"doc.docx-{order:04d}",
        source="doc.docx",
        order=order,
        paragraph_start=order + 1,
        paragraph_end=order + 1,
        text="Берём в процедуру только с суммой от 350 000 рублей.",
    )


def test_messages_contain_instruction_question_and_fragments() -> None:
    messages = build_messages("С какой суммой берут?", [make_chunk()])

    assert messages[0].type == "system"
    # проверяем сборку сообщений, а не формулировки модели: роль + вопрос + выдержки
    assert messages[0].type == "system"
    assert str(messages[0].content).strip()
    human = str(messages[1].content)
    assert "С какой суммой берут?" in human
    assert "[doc.docx-0000]" in human
    assert "350 000" in human


class FakeStructured:
    def __init__(self, result: object) -> None:
        self._result = result
        self.messages: list[Any] = []

    def invoke(self, messages: list[Any]) -> object:
        self.messages.append(messages)
        return self._result


class FakeChatOpenAI:
    instances: ClassVar[list[FakeChatOpenAI]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.structured = FakeStructured(
            AnswerDraft(answer="От 350 000 рублей.", grounded=True, used_chunk_ids=["doc.docx-0000"])
        )
        FakeChatOpenAI.instances.append(self)

    def with_structured_output(self, schema: type[AnswerDraft]) -> FakeStructured:
        assert schema is AnswerDraft
        return self.structured


def test_build_chat_model_passes_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_module, "ChatOpenAI", FakeChatOpenAI)
    FakeChatOpenAI.instances.clear()
    settings = make_settings()

    model = build_chat_model(settings)

    assert isinstance(model, FakeChatOpenAI)
    assert model.kwargs["api_key"].get_secret_value() == "test"
    assert model.kwargs["model"] == settings.llm_model
    assert model.kwargs["temperature"] == settings.temperature
    assert model.kwargs["extra_body"] == {"max_tokens": settings.max_tokens}


def test_build_structured_model_returns_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_module, "ChatOpenAI", FakeChatOpenAI)
    invoke = build_structured_model(make_settings())

    draft = invoke(build_messages("вопрос", [make_chunk()]))

    assert draft.grounded is True
    assert draft.used_chunk_ids == ["doc.docx-0000"]


def test_build_structured_model_rejects_unexpected_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    class BadStructured(FakeStructured):
        pass

    class BadClient(FakeChatOpenAI):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.structured = BadStructured({"answer": "dict вместо модели"})

    monkeypatch.setattr(llm_module, "ChatOpenAI", BadClient)
    invoke = build_structured_model(make_settings())

    with pytest.raises(TypeError, match="ожидался AnswerDraft"):
        invoke(build_messages("вопрос", [make_chunk()]))


class FakeTextModel:
    """Модель без структуры: на любой запрос возвращает заданный текст."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.seen: list[Any] = []

    def invoke(self, messages: list[Any]) -> AIMessage:
        self.seen.append(messages)
        return AIMessage(content=self.content)


def test_build_condense_returns_rewritten_question() -> None:
    model = FakeTextModel(content="  Можно ли списать долг по ипотеке?  ")
    condense = build_condense(cast(BaseChatModel, model))

    result = condense("а если ипотека?", [HumanMessage("долг 2 млн")])

    assert result == "Можно ли списать долг по ипотеке?"


def test_build_condense_falls_back_to_question_on_empty_answer() -> None:
    condense = build_condense(cast(BaseChatModel, FakeTextModel(content="   ")))

    assert condense("а если ипотека?", [HumanMessage("долг 2 млн")]) == "а если ипотека?"


class FakeFailingModel:
    """Модель, которая падает так же, как при упоре в max_tokens."""

    def invoke(self, messages: list[Any]) -> AIMessage:
        raise RuntimeError("LengthFinishReasonError")


def test_build_condense_keeps_question_when_model_fails() -> None:
    condense = build_condense(cast(BaseChatModel, FakeFailingModel()))

    assert condense("а если ипотека?", [HumanMessage("у меня долг 500 тысяч")]) == "а если ипотека?"


class FakeIntakeModel:
    def __init__(self, result: object) -> None:
        self._result = result
        self.seen: list[Any] = []

    def with_structured_output(self, schema: object) -> Any:
        model = self

        class _Structured:
            def invoke(self, messages: list[Any]) -> object:
                model.seen.append(messages)
                return model._result

        return _Structured()


def test_answer_draft_has_structure_fields() -> None:
    """Схема ответа задаёт вёрстку: суть, пункты, следующий шаг."""
    draft = AnswerDraft(answer="Суть.", points=["факт"], next_step="Шаг.", grounded=True)

    assert draft.points == ["факт"]
    assert draft.next_step == "Шаг."


def test_build_intake_reads_profile_slots() -> None:
    model = FakeIntakeModel(IntakeDraft(kind="situation", debt_amount=800_000, region="Москва", has_property=True))

    draft = build_intake(cast(BaseChatModel, model))("долг 800 тысяч, Москва, есть машина", [])

    assert draft.kind == "situation"
    assert draft.profile().debt_amount == 800_000
    assert draft.profile().region == "Москва"
    assert draft.profile().has_property is True


def test_build_intake_falls_back_to_question_on_failure() -> None:
    class Broken:
        def with_structured_output(self, schema: object) -> Any:
            class _Structured:
                def invoke(self, messages: list[Any]) -> object:
                    raise RuntimeError("model is down")

            return _Structured()

    draft = build_intake(cast(BaseChatModel, Broken()))("С какой суммой берут?", [])

    assert draft.kind == "question"
    assert draft.debt_amount is None
