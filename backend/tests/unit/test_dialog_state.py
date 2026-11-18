"""Unit: DialogState (цепочка chat_v2, узел 10). Чистое значение, без LLM."""

from __future__ import annotations

from src.models.dialog_state import DialogState


def test_empty_has_nothing() -> None:
    state = DialogState.empty()
    assert state.facts == {}
    assert state.asked == frozenset()
    assert state.as_prompt_block() == ""
    assert state.asked_as_prompt_block() == ""


def test_merged_keeps_old_and_adds_new_facts() -> None:
    state = DialogState.empty().merged({"сумма долга": "310 000 ₽"})
    state = state.merged({"регион": "Москва"})
    assert state.facts == {"сумма долга": "310 000 ₽", "регион": "Москва"}


def test_merged_overwrites_same_key_and_strips_blanks() -> None:
    state = DialogState.empty().merged({"сумма долга": "310 000 ₽"})
    state = state.merged({"сумма долга": " 400 000 ₽ ", "город": "   "})
    assert state.facts == {"сумма долга": "400 000 ₽"}


def test_merged_accumulates_asked_topics_with_normalization() -> None:
    state = DialogState.empty().merged(asked=["Общая сумма долгов"])
    state = state.merged(asked=["  общая   сумма   долгов ", "Регион прописки"])
    assert len(state.asked) == 2


def test_asked_about_matches_substring_both_ways() -> None:
    state = DialogState.empty().merged(asked=["сумма долга"])
    assert state.asked_about("общая сумма долга") is True
    assert state.asked_about("Сумма") is True
    assert state.asked_about("город") is False
    assert state.asked_about("   ") is False


def test_pending_drops_already_asked_topics() -> None:
    """Критерий A5: уже заданный вопрос не возвращается как новый."""
    state = DialogState.empty().merged(asked=["сумма долга"])
    assert state.pending(["сумма долга", "регион прописки", "город"]) == ["регион прописки", "город"]
    assert state.pending([]) == []


def test_prompt_blocks_are_sorted_and_human_readable() -> None:
    state = DialogState.empty().merged({"регион": "Казань", "сумма долга": "310 000 ₽"}, ["сумма долга"])
    assert state.as_prompt_block() == "регион: Казань; сумма долга: 310 000 ₽"
    assert state.asked_as_prompt_block() == "сумма долга"


def test_merged_does_not_mutate_original() -> None:
    original = DialogState.empty().merged({"сумма долга": "310 000 ₽"})
    original.merged({"город": "Тверь"})
    assert original.facts == {"сумма долга": "310 000 ₽"}
