"""Тесты доменных моделей: инварианты Chunk, RetrievedChunk, Answer и сборка GraphState."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.behavior import REFUSAL_TEXTS, leaks_internals
from domain.graph_state import GraphState
from domain.models import Answer, Chunk, RetrievedChunk, SourceRef


def make_chunk(**overrides: object) -> Chunk:
    params: dict[str, object] = {
        "id": "doc.docx-0000",
        "source": "doc.docx",
        "order": 0,
        "paragraph_start": 1,
        "paragraph_end": 3,
        "text": "В процедуру берём с суммой от 350 000 рублей.",
    }
    params.update(overrides)
    return Chunk(**params)  # type: ignore[arg-type]


def test_chunk_builds_and_is_frozen() -> None:
    chunk = make_chunk()

    assert chunk.id == "doc.docx-0000"
    assert chunk.paragraph_end - chunk.paragraph_start == 2
    with pytest.raises(ValidationError):
        chunk.text = "другое"  # type: ignore[misc]


def test_chunk_rejects_id_not_matching_source_and_order() -> None:
    with pytest.raises(ValidationError):
        make_chunk(id="doc.docx-0001")


def test_chunk_rejects_reversed_paragraphs() -> None:
    with pytest.raises(ValidationError):
        make_chunk(paragraph_start=5, paragraph_end=2)


def test_chunk_rejects_empty_text() -> None:
    with pytest.raises(ValidationError):
        make_chunk(text="")


def test_retrieved_chunk_bounds() -> None:
    chunk = make_chunk()
    retrieved = RetrievedChunk(chunk=chunk, score=0.5, rank=1)

    assert retrieved.chunk.id == chunk.id
    with pytest.raises(ValidationError):
        RetrievedChunk(chunk=chunk, score=1.5, rank=1)
    with pytest.raises(ValidationError):
        RetrievedChunk(chunk=chunk, score=0.5, rank=0)


def test_answer_grounded_with_sources() -> None:
    source = SourceRef(source="doc.docx", paragraph_start=1, paragraph_end=3, text="От 350 000 рублей.")

    answer = Answer(answer="От 350 000 рублей.", grounded=True, used_chunk_ids=["doc.docx-0000"], sources=[source])

    assert answer.grounded is True
    assert answer.sources[0].source == "doc.docx"


def test_answer_refusal_has_no_sources() -> None:
    source = SourceRef(source="doc.docx", paragraph_start=1, paragraph_end=3, text="От 350 000 рублей.")

    refusal = Answer(answer="В документе об этом нет.", grounded=False)

    assert refusal.used_chunk_ids == []
    with pytest.raises(ValidationError):
        Answer(answer="В документе об этом нет.", grounded=False, sources=[source])


def test_graph_state_after_all_nodes() -> None:
    chunk = make_chunk()
    state: GraphState = {
        "request_id": "req-1",
        "question": "с какой суммой берут?",
        "k": 3,
        "retrieved": [RetrievedChunk(chunk=chunk, score=0.9, rank=1)],
        "top_score": 0.9,
        "refused": False,
        "answer": Answer(answer="От 350 000 рублей.", grounded=True, used_chunk_ids=[chunk.id]),
    }

    assert state["retrieved"][0].chunk.id == chunk.id
    assert state["answer"] is not None
    assert state["answer"].grounded is True


def test_refusal_texts_never_mention_internals() -> None:
    """Клиент не должен узнать про инструкцию, фрагменты и источники."""
    for reason, text in REFUSAL_TEXTS.items():
        assert not leaks_internals(text), reason


def test_leaks_internals_detects_document_words() -> None:
    assert leaks_internals("В инструкции об этом не сказано") is True
    assert leaks_internals("Опираюсь на фрагмент 3") is True
    assert leaks_internals("По источникам видно") is True
    assert leaks_internals("Спишем долги через суд") is False


def test_off_topic_refusal_names_the_specialization() -> None:
    """Вопрос не по теме: клиент должен понять, о чём чат вообще."""
    text = REFUSAL_TEXTS["no_context"]

    assert "специализиру" in text
    assert "банкротств" in text
