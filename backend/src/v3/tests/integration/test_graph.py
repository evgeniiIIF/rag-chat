"""Интеграционные тесты графа: приветствие, сбор фильтров, справка и ответ по фрагментам."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from domain.graph_state import GraphState
from domain.models import Chunk, RetrievedChunk
from domain.profile import ClientProfile
from domain.scenario import INFO_QUERIES, STEP_QUERIES
from graph.build import build_graph
from infrastructure.llm import IntakeDraft, Prompt


def make_chunk() -> Chunk:
    return Chunk(
        id="doc.docx-0000",
        source="doc.docx",
        order=0,
        paragraph_start=1,
        paragraph_end=1,
        text="В процедуру берут с суммой от 350 000 рублей.",
    )


def make_hit(score: float = 0.9) -> RetrievedChunk:
    return RetrievedChunk(chunk=make_chunk(), score=score, rank=1)


class FakeIntake:
    def __init__(self, drafts: dict[str, IntakeDraft]) -> None:
        self.drafts = drafts

    def __call__(self, question: str, history: Sequence[BaseMessage]) -> IntakeDraft:
        return self.drafts.get(question, IntakeDraft(kind="situation"))


class FakeAnswer:
    def __init__(self) -> None:
        self.prompts: list[Prompt] = []

    def __call__(self, prompt: Prompt) -> str:
        self.prompts.append(prompt)
        return f"ответ:{prompt.stage}"


def make_graph(tmp_path: Path, intake: FakeIntake, answer: FakeAnswer, *, score: float = 0.9) -> Any:
    def search(question: str, k: int) -> list[RetrievedChunk]:
        return [make_hit(score)]

    return build_graph(
        search=search,
        answer_fn=answer,
        threshold=0.35,
        artifacts_dir=tmp_path / "artifacts",
        intake=intake,
        checkpointer=InMemorySaver(),
    )


def run(graph: Any, question: str, profile: ClientProfile | None = None) -> dict[str, Any]:
    # сервис всегда кладёт реплику клиента в историю перед вызовом графа
    state = GraphState(
        request_id="r1",
        question=question,
        messages=[HumanMessage(content=question)],
        profile=profile or ClientProfile(),
    )
    return graph.invoke(state, config={"configurable": {"thread_id": "t1"}})


def test_greeting_ends_the_turn(tmp_path: Path) -> None:
    answer = FakeAnswer()
    graph = make_graph(tmp_path, FakeIntake({}), answer)

    result = run(graph, "привет")

    assert result["step"] == "greeting"
    assert result["answer"].startswith("Привет!")
    assert answer.prompts == []


def test_graph_asks_debt_then_region(tmp_path: Path) -> None:
    intake = FakeIntake({"долг 800 тысяч": IntakeDraft(kind="situation", debt_amount=800_000)})
    answer = FakeAnswer()
    graph = make_graph(tmp_path, intake, answer)

    result = run(graph, "долг 800 тысяч")

    assert result["step"] == "ask_region"
    assert result["profile"].debt_amount == 800_000
    # контекст приходит на любом шаге, но запрос свой: «долг 800 тысяч» — плохой поисковый запрос
    assert result["search_query"] == STEP_QUERIES["ask_region"]
    assert result["retrieved"] != []
    assert result["grounded"] is False


def test_passed_filters_invite_without_context(tmp_path: Path) -> None:
    answer = FakeAnswer()
    graph = make_graph(tmp_path, FakeIntake({}), answer)
    profile = ClientProfile(debt_amount=800_000, region="Москва")

    result = run(graph, "запишите меня", profile)

    assert result["step"] == "invite"
    assert result["retrieved"] != []
    assert result["grounded"] is False
    assert "В конце задай один вопрос" not in answer.prompts[0].system


def test_question_retrieves_fragments(tmp_path: Path) -> None:
    answer = FakeAnswer()
    graph = make_graph(tmp_path, FakeIntake({"с какой суммой?": IntakeDraft(kind="question")}), answer)
    profile = ClientProfile(debt_amount=800_000, region="Москва")

    result = run(graph, "с какой суммой?", profile)

    assert result["step"] == "rag"
    assert result["grounded"] is True
    assert result["search_query"] == "с какой суммой?"
    assert "от 350 000 рублей" in answer.prompts[0].inputs["фрагменты"]


def test_one_failed_filter_skips_the_next_question(tmp_path: Path) -> None:
    intake = FakeIntake({"долг 310 тысяч": IntakeDraft(kind="situation", debt_amount=310_000)})
    answer = FakeAnswer()
    graph = make_graph(tmp_path, intake, answer)

    result = run(graph, "долг 310 тысяч")

    assert result["step"] == "info"
    assert result["profile"].region is None
    assert "не предлагай консультацию" in answer.prompts[0].system.lower()


def test_info_step_searches_by_the_failed_filter(tmp_path: Path) -> None:
    answer = FakeAnswer()
    graph = make_graph(tmp_path, FakeIntake({}), answer)
    profile = ClientProfile(debt_amount=200_000, region="Москва")

    result = run(graph, "и что теперь?", profile)

    assert result["step"] == "info"
    # фильтр провален по долгу: ищем, что предложить вместо процедуры
    assert result["search_query"] == INFO_QUERIES["debt"]
    assert "не предлагай консультацию" in answer.prompts[0].system.lower()


def test_booked_step_confirms(tmp_path: Path) -> None:
    answer = FakeAnswer()
    graph = make_graph(tmp_path, FakeIntake({}), answer)
    profile = ClientProfile(debt_amount=800_000, region="Москва", phone="+79991234567", consultation_time="завтра")

    result = run(graph, "спасибо", profile)

    assert result["step"] == "booked"
    assert result["answer"].lower() == "ответ:booked"


def test_messages_are_appended_to_history(tmp_path: Path) -> None:
    answer = FakeAnswer()
    graph = make_graph(tmp_path, FakeIntake({}), answer)

    result = run(graph, "привет")

    assert [message.type for message in result["messages"]] == ["human", "ai"]
