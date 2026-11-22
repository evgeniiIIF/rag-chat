"""Трассировка LLM: запись вызовов, сообщений и сырого ответа за один ход."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from langchain_core.messages import HumanMessage, SystemMessage

from core.trace import LlmTrace, capture, record_call, record_output


def test_capture_collects_messages_and_output() -> None:
    trace = LlmTrace()
    with capture(trace):
        call = record_call("answer", "gpt-test", [SystemMessage(content="правила"), HumanMessage(content="вопрос")])
        record_output(call, '{"answer": "ок"}')

    assert len(trace.calls) == 1
    entry = trace.calls[0]
    assert entry.purpose == "answer"
    assert entry.model == "gpt-test"
    assert [message.role for message in entry.messages] == ["system", "human"]
    assert entry.messages[1].content == "вопрос"
    assert entry.output == '{"answer": "ок"}'


def test_recording_outside_capture_is_noop() -> None:
    assert record_call("answer", "gpt-test", [HumanMessage(content="вопрос")]) is None
    trace = LlmTrace()
    with capture(trace):
        pass
    assert trace.calls == []
