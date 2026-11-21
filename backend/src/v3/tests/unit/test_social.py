"""Тесты соц-ветки: детектор намерений и готовые реплики (перенос из v2, решение D1)."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from core.behavior import BYE_REPLY, GREETING_FIRST, GREETING_REPEAT, THANKS_REPLY
from domain.social import Intent, already_greeted, detect, normalize
from graph.nodes.social import make_social_node


def test_detects_greeting_thanks_bye() -> None:
    assert detect("привет") is Intent.GREETING
    assert detect("Здравствуйте!") is Intent.GREETING
    assert detect("добрый день") is Intent.GREETING
    assert detect("спасибо") is Intent.THANKS
    assert detect("до свидания") is Intent.BYE


def test_business_replica_is_a_question() -> None:
    assert detect("как списать долги?") is Intent.QUESTION
    assert detect("здравствуйте, хочу списать долги") is Intent.QUESTION
    assert detect("приветствие в суде") is Intent.QUESTION
    assert detect("пока не знаю") is Intent.QUESTION
    assert detect("   !!!  ") is Intent.QUESTION


def test_normalize_strips_fillers_and_punctuation() -> None:
    assert normalize("Ну, привет!") == "привет"
    assert normalize("  и снова здравствуйте ") == "здравствуйте"


def test_already_greeted_reads_assistant_messages() -> None:
    greeted = [HumanMessage("здравствуйте"), AIMessage(GREETING_FIRST)]
    not_greeted = [HumanMessage("привет"), AIMessage("Расскажите о вашей ситуации.")]

    assert already_greeted(greeted) is True
    assert already_greeted(not_greeted) is False
    assert already_greeted([]) is False


def test_social_replies_are_short() -> None:
    for text in (GREETING_FIRST, GREETING_REPEAT, THANKS_REPLY, BYE_REPLY):
        assert len(text) < 90, text
        assert text.count("?") <= 1, text


def make_state(question: str) -> dict[str, object]:
    return {"request_id": "r", "question": question, "k": 3, "messages": [HumanMessage(question)]}


def test_node_answers_thanks_and_bye_without_model() -> None:
    node = make_social_node()

    assert node(make_state("спасибо"))["answer"].answer == THANKS_REPLY  # type: ignore[union-attr]
    assert node(make_state("до свидания"))["answer"].answer == BYE_REPLY  # type: ignore[union-attr]
    assert node(make_state("пока"))["messages"][0].type == "ai"  # type: ignore[index]
