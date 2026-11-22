"""Сценарий закрепного диалога: шаги и слоты от реплики к реплике, без реальной модели."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from domain.graph_state import GraphState
from domain.models import Chunk, RetrievedChunk
from domain.profile import ClientProfile
from graph.build import build_graph
from infrastructure.llm import IntakeDraft, Prompt

OPERATOR_TEXT = "ОБУЧЕНИЕ КЦ. Главная задача — продать клиенту юриста."

TURNS: list[tuple[str, IntakeDraft, str]] = [
    ("323 тыс", IntakeDraft(kind="question"), "info"),
    ("899 тыс", IntakeDraft(kind="situation"), "ask_region"),
    ("чечня", IntakeDraft(kind="situation", region="Чечня"), "info"),
    ("ой забыл я в дагестане", IntakeDraft(kind="situation", region="Дагестан"), "invite"),
    ("6644 завтра в 12", IntakeDraft(kind="situation", phone="6644", consultation_time="завтра в 12:00"), "invite"),
    ("66 44 55", IntakeDraft(kind="question"), "booked"),
    ("+7 900 123-45-67", IntakeDraft(kind="situation", phone="+7 900 123-45-67"), "booked"),
]


class ScriptedIntake:
    def __init__(self) -> None:
        self.drafts: dict[str, IntakeDraft] = {text: draft for text, draft, _ in TURNS}

    def __call__(self, question: str, history: Sequence[BaseMessage]) -> IntakeDraft:
        return self.drafts[question]


class FakeAnswer:
    def __init__(self) -> None:
        self.prompts: list[Prompt] = []

    def __call__(self, prompt: Prompt) -> str:
        self.prompts.append(prompt)
        return f"ответ {prompt.stage}"


def make_graph(answer: FakeAnswer, tmp_path: Path) -> Any:
    chunk = Chunk(
        id="doc.docx-0000", source="doc.docx", order=0, paragraph_start=1, paragraph_end=1, text=OPERATOR_TEXT
    )

    def search(question: str, k: int) -> list[RetrievedChunk]:
        return [RetrievedChunk(chunk=chunk, score=0.9, rank=1)]

    return build_graph(
        search=search,
        answer_fn=answer,
        threshold=0.35,
        artifacts_dir=tmp_path / "artifacts",
        intake=ScriptedIntake(),
        checkpointer=InMemorySaver(),
    )


def test_pinned_dialog_steps_and_slots(tmp_path: Path) -> None:
    answer = FakeAnswer()
    graph = make_graph(answer, tmp_path)
    profile = ClientProfile()

    for index, (text, _, expected_step) in enumerate(TURNS):
        state = GraphState(
            request_id=f"r{index}",
            question=text,
            messages=[HumanMessage(content=text)],
            profile=profile,
        )
        result = graph.invoke(state, config={"configurable": {"thread_id": f"t{index}"}})
        assert result["step"] == expected_step, (text, result["step"])
        profile = result["profile"]
        if index == 1:
            assert profile.debt_amount == 899_000  # новая сумма заменила старую
        if index == 4:
            assert profile.phone is None  # 4 цифры: номер неполный
            assert profile.phone_raw == "6644"
            assert profile.consultation_time == "завтра в 12:00"
        if index == 5:
            assert profile.phone == "66-44-55"  # после вопроса о телефоне 6 цифр это номер
            assert profile.phone_raw is None

    assert profile.phone == "+79001234567"
    assert profile.region == "Дагестан"
    assert profile.debt_amount == 899_000
    # инструкции операторам не дошли ни до одного промпта
    for prompt in answer.prompts:
        assert "ОБУЧЕНИЕ" not in prompt.inputs["фрагменты"]
        assert "продать клиенту" not in prompt.system
