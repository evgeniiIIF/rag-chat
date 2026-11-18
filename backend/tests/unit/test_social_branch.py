"""Unit: SocialBranch (цепочка chat_v2, узел 19/20, решение D1).

Соц-ветка — единственная деловая «смысловая» строка, которая имеет право быть хардкодом.
Проверяем: короткие строки A3, повтор не совпадает с первым, деловая реплика → None.
"""

from __future__ import annotations

from src.models.turn import Turn
from src.services.social_branch import (
    BYE_REPLY,
    GREETING_FIRST,
    GREETING_REPEAT,
    THANKS_REPLY,
    SocialBranch,
)

NO_HISTORY: list[Turn] = []
GREETED = [Turn(role="assistant", content=GREETING_FIRST)]


def test_first_greeting_matches_acceptance_text() -> None:
    assert SocialBranch.replica("здравствуйте", NO_HISTORY) == GREETING_FIRST
    assert GREETING_FIRST == "Привет! Я ассистент по банкротству. Чем могу помочь?"


def test_repeated_greeting_is_not_the_first_one() -> None:
    assert SocialBranch.replica("привет", GREETED) == GREETING_REPEAT
    assert GREETING_REPEAT == "Мы уже на связи. Расскажите о вашей ситуации — чем помочь?"


def test_punctuation_and_case_do_not_break_detection() -> None:
    for text in ("Здравствуйте!", "ну привет", "  пока  ", "Спасибо.", "добрый день"):
        assert SocialBranch.replica(text, NO_HISTORY) is not None, text


def test_thanks_and_bye_replies() -> None:
    assert SocialBranch.replica("спасибо", NO_HISTORY) == THANKS_REPLY
    assert SocialBranch.replica("пока", NO_HISTORY) == BYE_REPLY


def test_all_social_replies_are_short() -> None:
    """A3: одна реплика = одна строка, без «простыней» и без встречного допроса."""
    for text in (GREETING_FIRST, GREETING_REPEAT, THANKS_REPLY, BYE_REPLY):
        assert len(text) < 90, text
        assert text.count("?") <= 1, text


def test_business_replicas_go_to_the_model_branch() -> None:
    for text in (
        "банкротство надо юрист нужен",
        "давай стоимость",
        "давайте консультацию",
        "рассрочку на 310к платить уже не могу",
        "про гипопотамов",
        "какая разница",
    ):
        assert SocialBranch.replica(text, NO_HISTORY) is None, text
