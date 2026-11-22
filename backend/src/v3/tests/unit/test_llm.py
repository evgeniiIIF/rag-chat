"""Тесты сборки промпта: роль, шаг, фрагменты и подсказка про недостающий фильтр."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from domain.models import Chunk
from domain.profile import ClientProfile
from infrastructure.llm import Prompt, build_answer_fn, build_prompt, trim_history


def make_chunk() -> Chunk:
    return Chunk(
        id="doc.docx-0000",
        source="doc.docx",
        order=0,
        paragraph_start=1,
        paragraph_end=2,
        text="В процедуру берут с суммой от 350 000 рублей.",
    )


def test_prompt_has_role_step_and_question() -> None:
    prompt = build_prompt(step="ask_debt", profile=ClientProfile(), question="хочу списать долги")

    assert isinstance(prompt, Prompt)
    assert "консультант компании по банкротству" in prompt.system
    assert "общую сумму долга" in prompt.system
    assert prompt.messages[0].type == "system"
    assert isinstance(prompt.messages[-1], HumanMessage)
    assert "хочу списать долги" in str(prompt.messages[-1].content)


def test_prompt_has_no_missing_hint_when_filters_collected() -> None:
    profile = ClientProfile(debt_amount=800_000, region="Москва")

    prompt = build_prompt(step="invite", profile=profile, question="запишите меня")

    assert "В конце задай один вопрос" not in prompt.system
    assert "фильтры: пройдены" in prompt.inputs["состояние фильтров"]


def test_failed_filters_block_the_offer_even_for_questions() -> None:
    failed = ClientProfile(debt_amount=310_000, region="Москва")

    prompt = build_prompt(step="rag", profile=failed, question="а что делать?")

    assert "не предлагай консультацию" in prompt.system


def test_fragments_go_into_prompt_and_dump() -> None:
    prompt = build_prompt(step="rag", profile=ClientProfile(), question="с какой суммой берут?", chunks=[make_chunk()])

    human = str(prompt.messages[-1].content)
    assert "от 350 000 рублей" in human
    # ни id, ни имени файла, ни слова «фрагмент»: для модели это просто знание
    assert "doc.docx" not in human
    assert "фрагмент" not in human.lower()
    assert "фрагменты" in prompt.inputs
    assert prompt.dump()["stage"] == "rag"


def test_history_is_trimmed_and_counted() -> None:
    history = [HumanMessage(content="привет"), AIMessage(content="здравствуйте")]

    prompt = build_prompt(step="rag", profile=ClientProfile(), question="а сроки?", history=history)

    assert len(prompt.history) == 2
    assert prompt.inputs["история"].startswith("2 из 2")


def test_trim_history_returns_list() -> None:
    assert trim_history([]) == []


def test_answer_fn_returns_text_and_records_call() -> None:
    from core.trace import LlmTrace, capture

    class FakeModel:
        def invoke(self, messages: list[Any]) -> AIMessage:
            return AIMessage(content="  Ответ модели.  ")

    answer = build_answer_fn(FakeModel())  # type: ignore[arg-type]
    prompt = build_prompt(step="ask_debt", profile=ClientProfile(), question="привет")
    trace = LlmTrace()

    with capture(trace):
        text = answer(prompt)

    assert text == "Ответ модели."
    assert trace.calls[0].purpose == "answer:ask_debt"
    assert trace.calls[0].messages[0].role == "system"
