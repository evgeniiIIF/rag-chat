"""Unit: RelevanceGate + Policy (цепочка chat_v2, узлы 12/13)."""

from __future__ import annotations

import pytest

from src.models.analysis import Analysis, Scope, Style
from src.models.chunk import Chunk, ParagraphSpan
from src.models.dialog_state import DialogState
from src.models.retrieved import RetrievedChunk
from src.services.policy import Action, Policy
from src.services.relevance_gate import (
    REASON_BELOW_THRESHOLD,
    REASON_EMPTY,
    REASON_OK,
    RelevanceGate,
)


def _hit(score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=Chunk(
            source="КЦ.docx", text="берем в процедуру только с суммой от 350к", span=ParagraphSpan(start=1, end=1)
        ),
        score=score,
    )


def test_gate_rejects_empty_hits() -> None:
    verdict = RelevanceGate(0.35).judge([])
    assert verdict.enough is False
    assert verdict.reason == REASON_EMPTY
    assert verdict.top_score == 0.0


def test_gate_rejects_below_threshold() -> None:
    verdict = RelevanceGate(0.35).judge([_hit(0.1), _hit(0.34)])
    assert verdict.enough is False
    assert verdict.reason == REASON_BELOW_THRESHOLD
    assert verdict.top_score == pytest.approx(0.34)


def test_gate_accepts_at_or_above_threshold() -> None:
    verdict = RelevanceGate(0.35).judge([_hit(0.2), _hit(0.35)])
    assert verdict.enough is True
    assert verdict.is_ok
    assert verdict.reason == REASON_OK


def test_gate_threshold_is_not_hardcoded() -> None:
    hits = [_hit(0.3)]
    assert RelevanceGate(0.35).judge(hits).enough is False
    assert RelevanceGate(0.25).judge(hits).enough is True


def test_gate_rejects_bad_threshold() -> None:
    with pytest.raises(ValueError):
        RelevanceGate(1.5)


def _analysis(**kwargs: object) -> Analysis:
    base: dict[str, object] = {"scope": Scope.IN_KB, "question": "сколько стоит"}
    base.update(kwargs)
    return Analysis.model_validate(base)


def test_policy_off_kb_declines() -> None:
    decision = Policy().decide(_analysis(scope=Scope.OFF_KB, question="про гипопотамов"), DialogState.empty())
    assert decision.action is Action.DECLINE_OFFTOPIC


def test_policy_clarify_rephrases() -> None:
    decision = Policy().decide(_analysis(scope=Scope.CLARIFY), DialogState.empty())
    assert decision.action is Action.REPHRASE


def test_policy_consultation_ready_hands_off() -> None:
    decision = Policy().decide(_analysis(wants_consultation=True, missing=["регион"]), DialogState.empty())
    assert decision.action is Action.HANDOFF


def test_policy_asks_one_new_question() -> None:
    decision = Policy().decide(_analysis(missing=["сумма долга", "регион прописки"]), DialogState.empty())
    assert decision.action is Action.ASK_ONE
    assert decision.ask_about == "сумма долга"
    assert tuple(decision.pending) == ("сумма долга", "регион прописки")


def test_policy_skips_already_asked_question() -> None:
    """Критерий A5: повторно один и тот же вопрос не задаём."""
    state = DialogState.empty().merged(asked=["сумма долга"])
    decision = Policy().decide(_analysis(missing=["сумма долга"]), state)
    assert decision.action is Action.ANSWER
    assert decision.ask_about == ""


def test_policy_answers_when_nothing_missing() -> None:
    decision = Policy().decide(_analysis(missing=[]), DialogState.empty())
    assert decision.action is Action.ANSWER


def test_policy_passes_style_from_model() -> None:
    decision = Policy().decide(_analysis(style=Style.REASSURE, missing=["регион"]), DialogState.empty())
    assert decision.style is Style.REASSURE
