from __future__ import annotations

import pytest

from src.models.turn import Turn
from src.services.query_condenser import QueryCondenser


def _t(role: str, content: str) -> Turn:
    return Turn(role=role, content=content)  # type: ignore[arg-type]


def test_empty_history_returns_question() -> None:
    c = QueryCondenser()
    assert c.standalone("Сколько процедур?", []) == "Сколько процедур?"


def test_strips_question() -> None:
    c = QueryCondenser()
    assert c.standalone("  привет  ", []) == "привет"


def test_rejects_empty_question() -> None:
    c = QueryCondenser()
    with pytest.raises(ValueError, match="Пустой вопрос"):
        c.standalone("   ", [])


def test_joins_recent_history() -> None:
    c = QueryCondenser(history_limit=4)
    history = [
        _t("user", "Кто Иван?"),
        _t("assistant", "Царь."),
        _t("user", "А должность?"),
        _t("assistant", "Не указана."),
    ]
    result = c.standalone("А Григорий?", history)
    assert "U: Кто Иван?" in result
    assert "A: Царь." in result
    assert result.endswith("Q: А Григорий?")


def test_history_limit_keeps_only_tail() -> None:
    c = QueryCondenser(history_limit=2)
    history = [
        _t("user", "old1"),
        _t("assistant", "old2"),
        _t("user", "new1"),
        _t("assistant", "new2"),
    ]
    result = c.standalone("next?", history)
    assert "old1" not in result
    assert "old2" not in result
    assert "new1" in result and "new2" in result


def test_negative_history_limit_rejected() -> None:
    with pytest.raises(ValueError):
        QueryCondenser(history_limit=-1)
