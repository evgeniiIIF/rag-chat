from __future__ import annotations

from src.core.config import Settings
from src.models.chunk import Chunk, ParagraphSpan
from src.models.grounding import Grounding
from src.models.retrieved import RetrievedChunk
from src.services.answer_gate import NO_ANSWER_MARKER, gate, passes_threshold


def _settings(threshold: float = 0.35) -> Settings:
    return Settings(API_KEY="dummy", SCORE_THRESHOLD=threshold)


def _hit(score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=Chunk(source="КЦ.docx", text="x", span=ParagraphSpan(start=1, end=1)),
        score=score,
    )


def test_passes_threshold_false_on_empty() -> None:
    assert passes_threshold([], 0.35) is False


def test_passes_threshold_uses_top_score() -> None:
    assert passes_threshold([_hit(0.2), _hit(0.5)], 0.35) is True
    assert passes_threshold([_hit(0.1), _hit(0.2)], 0.35) is False


def test_gate_not_answerable_below_threshold() -> None:
    assert gate([_hit(0.1)], "answer", _settings()) is Grounding.NOT_ANSWERABLE


def test_gate_not_answerable_when_llm_skipped() -> None:
    assert gate([_hit(0.9)], None, _settings()) is Grounding.NOT_ANSWERABLE


def test_gate_not_answerable_on_marker() -> None:
    assert gate([_hit(0.9)], NO_ANSWER_MARKER, _settings()) is Grounding.NOT_ANSWERABLE


def test_gate_not_answerable_on_empty_string() -> None:
    assert gate([_hit(0.9)], "   ", _settings()) is Grounding.NOT_ANSWERABLE


def test_gate_grounded_when_above_and_answer_present() -> None:
    assert gate([_hit(0.9)], "точный ответ", _settings()) is Grounding.GROUNDED
