"""Трассировка вызовов LLM: что именно уходит в модель и что она вернула.

Прозрачность для отладки: сервис открывает запись на один ход (`capture`), узлы графа
и адаптеры модели пишут в неё полные сообщения (system / human / история) и сырой ответ.
Записи попадают в HTTP-ответ (`state.llm`) и печатаются в консоль браузера.

Контекст запроса — `ContextVar`: граф исполняется синхронно в том же контексте, что и
`ChatService.ask`, поэтому глобального состояния и блокировок не нужно.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field


class LlmMessage(BaseModel):
    """Одно сообщение запроса: роль и полный текст."""

    role: str
    content: str


class LlmCall(BaseModel):
    """Один вызов модели, разложенный по частям: промпт, история, вход, что ушло и что вернулось."""

    purpose: str = Field(description="что делает вызов: turn:<шаг> — один вызов на ход")
    model: str
    stage: str | None = Field(
        default=None,
        description="шаг разговора: ask_debt / ask_region / info / invite / booked / rag",
    )
    system: str | None = Field(default=None, description="системный промпт целиком")
    history: list[LlmMessage] = Field(default_factory=list, description="история диалога после обрезки")
    inputs: dict[str, str] = Field(default_factory=dict, description="именованные части запроса")
    messages: list[LlmMessage] = Field(default_factory=list, description="сообщения ровно как ушли")
    output: str | None = None


class LlmTrace(BaseModel):
    """Все вызовы модели за один ход диалога."""

    calls: list[LlmCall] = Field(default_factory=list)


_RECORDER: ContextVar[LlmTrace | None] = ContextVar("llm_trace", default=None)


@contextmanager
def capture(trace: LlmTrace) -> Iterator[LlmTrace]:
    """Открыть запись вызовов модели на один ход."""
    token = _RECORDER.set(trace)
    try:
        yield trace
    finally:
        _RECORDER.reset(token)


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return str(content)


def _as_messages(messages: Sequence[BaseMessage]) -> list[LlmMessage]:
    return [LlmMessage(role=str(message.type), content=_text(message.content)) for message in messages]


def record_call(
    purpose: str,
    model: str,
    messages: Sequence[BaseMessage],
    *,
    stage: str | None = None,
    system: str | None = None,
    history: Sequence[BaseMessage] = (),
    inputs: dict[str, str] | None = None,
) -> LlmCall | None:
    """Записать начало вызова модели; вернуть запись, чтобы дописать ответ."""
    trace = _RECORDER.get()
    if trace is None:
        return None
    call = LlmCall(
        purpose=purpose,
        model=model,
        stage=stage,
        system=system,
        history=_as_messages(history),
        inputs=inputs or {},
        messages=_as_messages(messages),
    )
    trace.calls.append(call)
    return call


def record_output(call: LlmCall | None, output: Any) -> None:
    """Дописать сырой ответ модели к записи вызова."""
    if call is None or output is None:
        return
    call.output = output if isinstance(output, str) else str(output)


def model_name(model: Any) -> str:
    """Имя модели из клиента LangChain (для прозрачности в ответе)."""
    for attr in ("model_name", "model"):
        value = getattr(model, attr, None)
        if isinstance(value, str) and value:
            return value
    return type(model).__name__
