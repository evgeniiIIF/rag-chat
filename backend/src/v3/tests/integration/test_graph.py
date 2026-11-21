"""Интеграционные тесты графа: маршрут отказа и маршрут генерации."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from core.behavior import (
    ASK_DEBT,
    ASK_REGION,
    GREETING_FIRST,
    GREETING_REPEAT,
    INVITE,
    NOT_OUR_CASE_DEBT,
    REFUSAL_TEXTS,
)
from domain.models import Chunk, RetrievedChunk
from graph.build import build_graph, route_after_grade
from infrastructure.artifacts import read_json
from infrastructure.llm import AnswerDraft, IntakeDraft


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
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, messages: list[Any]) -> AnswerDraft:
        self.calls += 1
        return AnswerDraft(answer="От 350 000 рублей.", grounded=True, used_chunk_ids=["doc.docx-0000"])


def test_route_after_grade() -> None:
    refused = {"request_id": "r", "question": "q", "k": 3, "refused": True}
    grounded = {"request_id": "r", "question": "q", "k": 3, "refused": False}

    assert route_after_grade(refused) == "refuse"
    assert route_after_grade(grounded) == "generate"


def test_graph_refuses_below_threshold(tmp_path: Path) -> None:
    invoke = FakeInvoke()
    graph = build_graph(
        search=lambda question, k: [make_hit(0.1)],
        threshold=0.35,
        invoke=invoke,
        artifacts_dir=tmp_path,
    )

    result = graph.invoke({"request_id": "req-refuse", "question": "Что с гипопотамами?", "k": 3})

    assert result["refused"] is True
    assert result["top_score"] == 0.1
    assert result["answer"].answer == REFUSAL_TEXTS["below_threshold"]
    assert result["answer"].grounded is False
    assert [message.content for message in result["messages"]] == [REFUSAL_TEXTS["below_threshold"]]
    assert invoke.calls == 0
    assert not (tmp_path / "req-refuse" / "prompt.json").exists()


def test_graph_generates_when_grounding_exists(tmp_path: Path) -> None:
    invoke = FakeInvoke()
    graph = build_graph(
        search=lambda question, k: [make_hit(0.9)],
        threshold=0.35,
        invoke=invoke,
        artifacts_dir=tmp_path,
    )

    result = graph.invoke({"request_id": "req-ok", "question": "С какой суммой берут?", "k": 3})

    assert result["refused"] is False
    answer = result["answer"]
    assert answer.grounded is True
    assert answer.sources[0].text.startswith("Берём")
    assert invoke.calls == 1
    assert read_json(tmp_path / "req-ok" / "prompt.json")["question"] == "С какой суммой берут?"
    assert [message.content for message in result["messages"]] == [answer.answer]


def test_checkpointer_keeps_dialog_history_per_thread(tmp_path: Path) -> None:
    """Один thread_id — история копится; другой thread_id её не видит."""
    graph = build_graph(
        search=lambda question, k: [make_hit(0.9)],
        threshold=0.35,
        invoke=FakeInvoke(),
        artifacts_dir=tmp_path,
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "client-1"}}

    graph.invoke(
        {"request_id": "r1", "question": "Вопрос 1", "k": 3, "messages": [HumanMessage(content="Вопрос 1")]},
        config=config,
    )
    second = graph.invoke(
        {"request_id": "r2", "question": "Вопрос 2", "k": 3, "messages": [HumanMessage(content="Вопрос 2")]},
        config=config,
    )
    other = graph.invoke(
        {"request_id": "r3", "question": "Вопрос 3", "k": 3, "messages": [HumanMessage(content="Вопрос 3")]},
        config={"configurable": {"thread_id": "client-2"}},
    )

    assert [message.content for message in second["messages"]][:2] == ["Вопрос 1", "От 350 000 рублей."]
    assert [message.content for message in other["messages"]][0] == "Вопрос 3"  # noqa: RUF015


def test_follow_up_is_rewritten_before_search(tmp_path: Path) -> None:
    """Follow-up ищется по переписанному вопросу, ответ по-прежнему строится по фрагментам."""
    queries: list[str] = []

    def search(question: str, k: int) -> list[RetrievedChunk]:
        queries.append(question)
        return [make_hit(0.9)]

    graph = build_graph(
        search=search,
        threshold=0.35,
        invoke=FakeInvoke(),
        artifacts_dir=tmp_path,
        condense=lambda question, history: "какой суммой долга берут в процедуру?",
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "client-1"}}
    first = {"request_id": "r1", "question": "берут с какой суммой?", "k": 3}
    second = {"request_id": "r2", "question": "а подробнее?", "k": 3}

    graph.invoke({**first, "messages": [HumanMessage(content="берут с какой суммой?")]}, config=config)
    graph.invoke({**second, "messages": [HumanMessage(content="а подробнее?")]}, config=config)

    assert queries == ["берут с какой суммой?", "какой суммой долга берут в процедуру?"]


def test_greeting_answers_without_search_and_model(tmp_path: Path) -> None:
    """Соц-ветка: готовый текст, поиск и модель не вызываются."""
    calls: list[str] = []
    invoke = FakeInvoke()
    graph = build_graph(
        search=lambda question, k: calls.append(question) or [make_hit(0.9)],
        threshold=0.35,
        invoke=invoke,
        artifacts_dir=tmp_path,
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "client-1"}}

    first = graph.invoke(
        {"request_id": "r1", "question": "Здравствуйте!", "k": 3, "messages": [HumanMessage(content="Здравствуйте!")]},
        config=config,
    )
    second = graph.invoke(
        {"request_id": "r2", "question": "привет", "k": 3, "messages": [HumanMessage(content="привет")]},
        config=config,
    )

    assert first["answer"].answer == GREETING_FIRST
    assert second["answer"].answer == GREETING_REPEAT
    assert first["top_score"] == 0.0
    assert calls == []
    assert invoke.calls == 0


class FakeIntake:
    """Разбор реплики по расписанию: что «сказал» клиент в этом ходе."""

    def __init__(self, draft: IntakeDraft) -> None:
        self.draft = draft
        self.calls = 0

    def __call__(self, question: str, history: list[Any]) -> IntakeDraft:
        self.calls += 1
        return self.draft


def build_scenario_graph(tmp_path: Path, draft: IntakeDraft) -> tuple[Any, FakeIntake, FakeInvoke, list[str]]:
    intake = FakeIntake(draft)
    invoke = FakeInvoke()
    calls: list[str] = []
    graph = build_graph(
        search=lambda question, k: calls.append(question) or [make_hit(0.9)],
        threshold=0.35,
        invoke=invoke,
        artifacts_dir=tmp_path,
        intake=intake,
        min_debt_rub=350_000,
        excluded_regions=("владимирская",),
        checkpointer=InMemorySaver(),
    )
    return graph, intake, invoke, calls


def test_vague_question_goes_to_scenario_not_to_document(tmp_path: Path) -> None:
    graph, _, invoke, calls = build_scenario_graph(tmp_path, IntakeDraft(kind="situation"))

    result = graph.invoke(
        {"request_id": "r1", "question": "что знаешь вообще", "k": 3, "messages": [HumanMessage("что знаешь вообще")]},
        config={"configurable": {"thread_id": "t1"}},
    )

    assert result["answer"].answer == ASK_DEBT
    assert result["top_score"] == 0.0
    assert calls == []
    assert invoke.calls == 0


def test_scenario_advances_between_turns(tmp_path: Path) -> None:
    graph, _, _, _ = build_scenario_graph(tmp_path, IntakeDraft(kind="situation", debt_amount=500_000))

    result = graph.invoke(
        {"request_id": "r2", "question": "долг 500 тысяч", "k": 3, "messages": [HumanMessage("долг 500 тысяч")]},
        config={"configurable": {"thread_id": "t2"}},
    )

    assert result["answer"].answer == ASK_REGION


def test_small_debt_is_refused_by_scenario(tmp_path: Path) -> None:
    graph, _, invoke, calls = build_scenario_graph(tmp_path, IntakeDraft(kind="situation", debt_amount=150_000))

    result = graph.invoke(
        {"request_id": "r3", "question": "долг 150 тысяч", "k": 3, "messages": [HumanMessage("долг 150 тысяч")]},
        config={"configurable": {"thread_id": "t3"}},
    )

    assert result["answer"].answer == NOT_OUR_CASE_DEBT
    assert calls == []
    assert invoke.calls == 0


def test_qualified_client_is_invited_to_consultation(tmp_path: Path) -> None:
    draft = IntakeDraft(kind="situation", debt_amount=800_000, region="Москва", has_property=False)
    graph, _, _, _ = build_scenario_graph(tmp_path, draft)

    result = graph.invoke(
        {"request_id": "r4", "question": "долг 800 тысяч, Москва, имущества нет", "k": 3, "messages": []},
        config={"configurable": {"thread_id": "t4"}},
    )

    assert result["answer"].answer == INVITE


def test_specific_question_still_uses_document(tmp_path: Path) -> None:
    graph, _, invoke, calls = build_scenario_graph(tmp_path, IntakeDraft(kind="question"))

    result = graph.invoke(
        {"request_id": "r5", "question": "С какой суммой берут?", "k": 3, "messages": []},
        config={"configurable": {"thread_id": "t5"}},
    )

    assert result["answer"].answer == "От 350 000 рублей."
    assert invoke.calls == 1
    assert calls == ["С какой суммой берут?"]
