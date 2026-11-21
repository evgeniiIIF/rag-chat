"""Тесты узлов графа: поиск, числовой гейт, сборка Answer и артефакты генерации."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from core.behavior import REFUSAL_TEXTS
from domain.graph_state import GraphState
from domain.models import Answer, Chunk, RetrievedChunk
from graph.nodes.condense import make_condense_node
from graph.nodes.generate import make_generate_node, to_answer
from graph.nodes.grade import make_grade_node
from graph.nodes.refuse import make_refuse_node
from graph.nodes.retrieve import make_retrieve_node
from infrastructure.artifacts import read_json
from infrastructure.llm import AnswerDraft


def make_chunk(order: int = 0) -> Chunk:
    return Chunk(
        id=f"doc.docx-{order:04d}",
        source="doc.docx",
        order=order,
        paragraph_start=order + 1,
        paragraph_end=order + 2,
        text="Берём в процедуру только с суммой от 350 000 рублей.",
    )


def make_hit(score: float, order: int = 0, rank: int = 1) -> RetrievedChunk:
    return RetrievedChunk(chunk=make_chunk(order), score=score, rank=rank)


def make_state(**extra: object) -> GraphState:
    state: GraphState = {"request_id": "req-1", "question": "С какой суммой берут?", "k": 3}
    state.update(extra)  # type: ignore[typeddict-item]
    return state


def test_retrieve_node_uses_question_and_k() -> None:
    calls: list[tuple[str, int]] = []
    hits = [make_hit(0.9)]

    def search(question: str, k: int) -> list[RetrievedChunk]:
        calls.append((question, k))
        return hits

    result = make_retrieve_node(search)(make_state())

    assert calls == [("С какой суммой берут?", 3)]
    assert result["retrieved"] == hits


def test_grade_node_without_hits_refuses() -> None:
    result = make_grade_node(0.35)(make_state(retrieved=[]))

    assert result == {"top_score": 0.0, "refused": True, "refusal_reason": "no_context"}


def test_grade_node_refuses_below_threshold() -> None:
    result = make_grade_node(0.35)(make_state(retrieved=[make_hit(0.2)]))

    assert result["top_score"] == 0.2
    assert result["refused"] is True
    assert result["refusal_reason"] == "below_threshold"


def test_grade_node_passes_above_threshold() -> None:
    result = make_grade_node(0.35)(make_state(retrieved=[make_hit(0.4), make_hit(0.8, order=1, rank=2)]))

    assert result["top_score"] == 0.8
    assert result["refused"] is False


def test_to_answer_keeps_only_known_and_grounded_ids() -> None:
    draft = AnswerDraft(
        answer="От 350 000 рублей.",
        grounded=True,
        used_chunk_ids=["doc.docx-0000", "doc.docx-9999", "doc.docx-0000"],
    )

    answer = to_answer(draft, [make_chunk(0)])

    assert answer.grounded is True
    assert answer.used_chunk_ids == ["doc.docx-0000"]
    assert answer.sources[0].paragraph_start == 1
    assert answer.sources[0].text.startswith("Берём")


def test_to_answer_keeps_honest_model_text_without_grounding() -> None:
    """Модель сама сказала «не знаю» — её человеческая фраза остаётся, источников нет."""
    draft = AnswerDraft(
        answer="Не знаю, это лучше уточнить у юриста.", grounded=False, used_chunk_ids=["doc.docx-0000"]
    )

    answer = to_answer(draft, [make_chunk(0)])

    assert answer.answer == "Не знаю, это лучше уточнить у юриста."
    assert answer.grounded is False
    assert answer.used_chunk_ids == []
    assert answer.sources == []


def test_to_answer_refuses_without_known_ids() -> None:
    draft = AnswerDraft(answer="Что-то.", grounded=True, used_chunk_ids=["нет-такого"])

    answer = to_answer(draft, [make_chunk(0)])

    assert answer.grounded is False
    assert answer.sources == []


def test_generate_node_writes_artifacts(tmp_path: Path) -> None:
    captured: list[list[object]] = []
    draft = AnswerDraft(answer="От 350 000 рублей.", grounded=True, used_chunk_ids=["doc.docx-0000"])

    def invoke(messages: list[object]) -> AnswerDraft:
        captured.append(messages)
        return draft

    node = make_generate_node(invoke, artifacts_dir=tmp_path)  # type: ignore[arg-type]
    result = node(make_state(retrieved=[make_hit(0.9)]))

    answer = cast(Answer, result["answer"])
    assert answer.grounded is True
    assert captured
    prompt = read_json(tmp_path / "req-1" / "prompt.json")
    assert prompt["chunk_ids"] == ["doc.docx-0000"]
    assert read_json(tmp_path / "req-1" / "answer.json")["refused"] is False


def test_condense_passes_question_without_history() -> None:
    calls: list[str] = []

    def rewrite(question: str, history: list[Any]) -> str:
        calls.append(question)
        return "переписанный"

    node = make_condense_node(rewrite)

    result = node({"request_id": "r", "question": "какой суммой?", "k": 3, "messages": [HumanMessage("какой суммой?")]})

    assert result["search_query"] == "какой суммой?"
    assert calls == []


def test_condense_rewrites_follow_up_with_history() -> None:
    seen: list[list[Any]] = []

    def rewrite(question: str, history: list[Any]) -> str:
        seen.append(list(history))
        return "Можно ли списать долг по ипотеке?"

    node = make_condense_node(rewrite)
    state = {
        "request_id": "r",
        "question": "а если ипотека?",
        "k": 3,
        "messages": [
            HumanMessage("у меня долг 2 млн"),
            AIMessage("расскажите про ипотеку"),
            HumanMessage("а если ипотека?"),
        ],
    }

    result = node(state)

    assert result["search_query"] == "Можно ли списать долг по ипотеке?"
    assert len(seen[0]) == 2


def test_retrieve_uses_rewritten_query() -> None:
    queries: list[str] = []

    def search(question: str, k: int) -> list[RetrievedChunk]:
        queries.append(question)
        return [make_hit(0.9)]

    node = make_retrieve_node(search)

    node({"request_id": "r", "question": "а если ипотека?", "k": 3, "search_query": "долг по ипотеке"})

    assert queries == ["долг по ипотеке"]


def test_refuse_node_uses_reason_from_state() -> None:
    result = make_refuse_node()({"request_id": "r", "question": "q", "k": 3, "refusal_reason": "no_context"})

    assert result["answer"].answer == REFUSAL_TEXTS["no_context"]
    assert result["answer"].grounded is False


def test_to_answer_falls_back_to_template_without_model_text() -> None:
    """Пустой текст модели — единственный случай, когда клиент видит шаблон отказа."""
    draft = AnswerDraft(answer="   ", grounded=False, used_chunk_ids=[])

    assert to_answer(draft, [make_chunk()], "no_answer").answer == REFUSAL_TEXTS["no_answer"]


def test_to_answer_replaces_leaky_answer_with_refusal() -> None:
    """Модель сослалась на инструкцию — клиент получает отказ, а не внутреннюю кухню."""
    draft = AnswerDraft(answer="В инструкции об этом сказано так.", grounded=True, used_chunk_ids=["doc.docx-0000"])

    answer = to_answer(draft, [make_chunk()])

    assert answer.grounded is False
    assert answer.answer == REFUSAL_TEXTS["no_answer"]
    assert answer.sources == []


def test_generate_falls_back_to_refusal_when_model_fails(tmp_path: Path) -> None:
    """Упёрлась в max_tokens — клиент получает отказ, а не 500."""

    def boom(messages: list[BaseMessage]) -> AnswerDraft:
        raise RuntimeError("LengthFinishReasonError")

    node = make_generate_node(boom, artifacts_dir=tmp_path)
    state: GraphState = {
        "request_id": "r1",
        "question": "с чего начать?",
        "k": 3,
        "messages": [HumanMessage(content="с чего начать?")],
        "retrieved": [make_hit(0.9)],
    }

    result = node(state)

    assert result["answer"] is not None
    assert result["answer"].answer == REFUSAL_TEXTS["no_answer"]
    assert result["answer"].grounded is False


def test_to_answer_composes_summary_points_and_next_step() -> None:
    """Структуру ответа собираем из полей схемы, а не из вёрстки модели."""
    draft = AnswerDraft(
        answer="Вас берут в процедуру.",
        points=["Сумма долга — от 350 000 рублей", "Смотрю имущество и сделки"],
        next_step="Давайте на бесплатную консультацию?",
        grounded=True,
        used_chunk_ids=["doc.docx-0000"],
    )

    answer = to_answer(draft, [make_chunk(0)])

    assert answer.answer == (
        "Вас берут в процедуру.\n\n"
        "- Сумма долга — от 350 000 рублей\n"
        "- Смотрю имущество и сделки\n\n"
        "Давайте на бесплатную консультацию?"
    )
    assert answer.grounded is True


def test_to_answer_without_points_stays_plain() -> None:
    draft = AnswerDraft(answer="От 350 000 рублей.", grounded=True, used_chunk_ids=["doc.docx-0000"])

    assert to_answer(draft, [make_chunk(0)]).answer == "От 350 000 рублей."
