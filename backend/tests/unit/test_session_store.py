"""Unit: SessionStore + dedupe_turns (цепочка chat_v2, узлы 07/17). In-memory, TTL, LRU."""

from __future__ import annotations

import pytest

from src.models.dialog_state import DialogState
from src.models.turn import Turn
from src.services.session_store import Session, SessionStore, dedupe_turns


def _u(text: str) -> Turn:
    return Turn(role="user", content=text)


def _a(text: str) -> Turn:
    return Turn(role="assistant", content=text)


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_load_unknown_session_returns_empty() -> None:
    assert SessionStore().load("nope").state.facts == {}
    assert SessionStore().load(None).turns == ()


def test_save_then_load_roundtrip() -> None:
    store = SessionStore()
    state = DialogState.empty().merged({"сумма долга": "310 000 ₽"})
    store.save("s1", state, [_u("рассрочку на 310к не могу"), _a("Понял.")])
    loaded = store.load("s1")
    assert loaded.state.facts == {"сумма долга": "310 000 ₽"}
    assert [t.content for t in loaded.turns] == ["рассрочку на 310к не могу", "Понял."]


def test_expired_session_is_dropped() -> None:
    clock = _Clock()
    store = SessionStore(ttl_seconds=10, clock=clock)
    store.save("s1", DialogState.empty(), [_u("привет")])
    clock.advance(11)
    assert store.load("s1") == Session.empty()
    assert store.size() == 0


def test_max_turns_keeps_tail() -> None:
    store = SessionStore(max_turns=3)
    turns = [_u(f"реплика {i}") for i in range(10)]
    saved = store.save("s1", DialogState.empty(), turns)
    assert [t.content for t in saved.turns] == ["реплика 7", "реплика 8", "реплика 9"]


def test_lru_evicts_oldest_over_capacity() -> None:
    store = SessionStore(max_sessions=2)
    for i in range(3):
        store.save(f"s{i}", DialogState.empty().merged({"факт": str(i)}), [_u("q")])
    assert store.size() == 2
    assert store.load("s0") == Session.empty()
    assert store.load("s2").state.facts == {"факт": "2"}


def test_load_refreshes_lru_order() -> None:
    store = SessionStore(max_sessions=2)
    store.save("s1", DialogState.empty().merged({"факт": "1"}), [_u("q")])
    store.save("s2", DialogState.empty().merged({"факт": "2"}), [_u("q")])
    store.load("s1")  # s1 снова свежайший → вытесняется s2
    store.save("s3", DialogState.empty().merged({"факт": "3"}), [_u("q")])
    assert store.load("s2") == Session.empty()
    assert store.load("s1").state.facts == {"факт": "1"}


def test_zero_limits_rejected() -> None:
    with pytest.raises(ValueError):
        SessionStore(ttl_seconds=0)
    with pytest.raises(ValueError):
        SessionStore(max_sessions=0)
    with pytest.raises(ValueError):
        SessionStore(max_turns=0)


def test_dedupe_turns_merges_chronologically_without_duplicates() -> None:
    stored = [_u("здравствуйте"), _a("Привет!")]
    incoming = [_u("здравствуйте"), _u("банкротство надо")]
    merged = dedupe_turns(stored, incoming)
    assert [(t.role, t.content) for t in merged] == [
        ("user", "здравствуйте"),
        ("assistant", "Привет!"),
        ("user", "банкротство надо"),
    ]
