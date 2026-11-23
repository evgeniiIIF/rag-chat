"""Тесты сценария чата: граф целиком, шаги, артефакты и трейс модели."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from langchain_core.messages import BaseMessage
from pydantic import SecretStr

from core.config import Settings
from domain.models import Chunk, RetrievedChunk
from infrastructure.artifacts import read_json
from infrastructure.llm import AnswerDraft, IntakeDraft
from schemas.chat import ChatRequest
from services.chat_service import ChatService


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        api_key=SecretStr("test"),
        artifacts_dir=tmp_path / "artifacts",
        retriever_k=3,
        score_threshold=0.35,
    )


def make_chunk(order: int = 0) -> Chunk:
    return Chunk(
        id=f"doc.docx-{order:04d}",
        source="doc.docx",
        order=order,
        paragraph_start=order + 1,
        paragraph_end=order + 1,
        text="В процедуру берут с суммой от 350 000 рублей.",
    )


class FakeIntake:
    """Разбор реплики по тексту: что «понял» — то и вернём."""

    def __init__(self) -> None:
        self.answers: dict[str, IntakeDraft] = {}

    def __call__(self, question: str, history: Sequence[BaseMessage]) -> IntakeDraft:
        return self.answers.get(question, IntakeDraft(kind="situation"))


class FakeAnswer:
    def __init__(self) -> None:
        self.stages: list[str] = []
        self.prompts: list[Any] = []

    def __call__(self, prompt: Any) -> AnswerDraft:
        self.stages.append(prompt.stage)
        self.prompts.append(prompt)
        return AnswerDraft(summary=f"Ответ на шаге {prompt.stage}.")


def make_service(tmp_path: Path, *, score: float = 0.9) -> tuple[ChatService, FakeIntake, FakeAnswer]:
    intake = FakeIntake()
    answer = FakeAnswer()

    def search(question: str, k: int) -> list[RetrievedChunk]:
        return [RetrievedChunk(chunk=make_chunk(), score=score, rank=1)]

    service = ChatService(
        make_settings(tmp_path),
        search=search,
        answer_fn=answer,
        intake=intake,
    )
    return service, intake, answer


def test_greeting_answers_without_model(tmp_path: Path) -> None:
    service, _, answer = make_service(tmp_path)

    response = service.ask(ChatRequest(question="привет", session_id="s1"))

    assert response.answer.startswith("Привет!")
    assert response.state.step == "greeting"
    assert answer.stages == []


def test_filters_are_collected_step_by_step(tmp_path: Path) -> None:
    service, intake, answer = make_service(tmp_path)
    intake.answers["долг 310 тысяч"] = IntakeDraft(kind="situation", debt_amount=310_000)
    intake.answers["Москва"] = IntakeDraft(kind="situation", region="Москва")

    first = service.ask(ChatRequest(question="долг 310 тысяч", session_id="s2"))
    second = service.ask(ChatRequest(question="Москва", session_id="s2"))

    # сумма ниже порога: справка сразу, регион уже не спрашиваем
    assert first.state.step == "info"
    assert first.state.profile.debt_amount == 310_000
    assert first.state.profile.region is None
    assert second.state.step == "info"
    assert second.state.filters_passed is False
    assert answer.stages == ["info", "info"]


def test_question_uses_document_fragments(tmp_path: Path) -> None:
    service, intake, answer = make_service(tmp_path)
    intake.answers["долг 800 тысяч, Москва"] = IntakeDraft(kind="situation", debt_amount=800_000, region="Москва")
    intake.answers["с какой суммой берут?"] = IntakeDraft(kind="question")
    service.ask(ChatRequest(question="долг 800 тысяч, Москва", session_id="s3"))

    response = service.ask(ChatRequest(question="с какой суммой берут?", session_id="s3"))

    assert response.state.step == "rag"
    assert response.grounded is True
    assert response.state.retrieved == 1
    human = str(answer.prompts[-1].messages[-1].content)
    assert "350 000" in human
    assert "doc.docx" not in human  # модель не видит адресов источника
    assert response.sources[0].source == "doc.docx"


def test_weak_fragments_are_dropped(tmp_path: Path) -> None:
    service, intake, _ = make_service(tmp_path, score=0.1)
    intake.answers["долг 800 тысяч, Москва"] = IntakeDraft(kind="situation", debt_amount=800_000, region="Москва")
    intake.answers["с какой суммой берут?"] = IntakeDraft(kind="question")
    service.ask(ChatRequest(question="долг 800 тысяч, Москва", session_id="s4"))

    response = service.ask(ChatRequest(question="с какой суммой берут?", session_id="s4"))

    assert response.grounded is False
    assert response.state.chunks == []


def test_artifacts_written_per_request(tmp_path: Path) -> None:
    service, intake, _ = make_service(tmp_path)
    intake.answers["долг 800 тысяч, Москва"] = IntakeDraft(kind="situation", debt_amount=800_000, region="Москва")
    intake.answers["с какой суммой берут?"] = IntakeDraft(kind="question")
    service.ask(ChatRequest(question="долг 800 тысяч, Москва", session_id="s5"))
    service.ask(ChatRequest(question="с какой суммой берут?", session_id="s5"))

    artifact_dirs = [path for path in (tmp_path / "artifacts").iterdir() if path.is_dir()]
    names = {item.name for path in artifact_dirs for item in path.iterdir()}
    assert {"retrieved.json", "answer_rag.json", "llm.json"} <= names
    trace_dir = next(path for path in artifact_dirs if (path / "answer_rag.json").exists())
    trace = read_json(trace_dir / "llm.json")
    assert trace
