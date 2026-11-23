"""Адаптер модели: ровно один запрос на ход диалога.

Текст промптов живёт в `core/behavior.py`, здесь — сборка сообщений, схема ответа и вызов модели.
Ответ один: `TurnDraft` с полями разбора реплики и готовым текстом клиенту. Повторных запросов нет,
поэтому пустой или неразобранный ответ не переспрашивается — текст на такой случай собирает узел хода.
Каждый вызов пишется в трейс (`core/trace.py`): что ушло и что вернулось.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.messages.utils import count_tokens_approximately, trim_messages
from langchain_openai import ChatOpenAI

from core.behavior import HISTORY_TOKEN_BUDGET, build_turn_system, build_turn_user, state_text
from core.config import Settings
from core.trace import model_name, record_call, record_output
from domain.models import Chunk, TurnDraft
from domain.profile import ClientProfile

logger = logging.getLogger(__name__)

type TurnFn = Callable[["Prompt"], TurnDraft]


@dataclass(frozen=True)
class Prompt:
    """Запрос к модели, разложенный по частям: шаг, промпт, история, блоки входа, сообщения."""

    stage: str
    system: str
    history: Sequence[BaseMessage]
    state: str
    chunks: str
    question: str
    messages: list[BaseMessage] = field(default_factory=list)

    def dump(self) -> dict[str, object]:
        """Как запрос сохраняется в артефакты и уходит на фронтенд."""
        return {
            "stage": self.stage,
            "system": self.system,
            "history": [_message(message) for message in self.history],
            "state": self.state,
            "chunks": self.chunks,
            "question": self.question,
            "messages": [_message(message) for message in self.messages],
        }


def _message(message: BaseMessage) -> dict[str, str]:
    return {"role": message.type, "content": str(message.content)}


def _fragments(chunks: Sequence[Chunk]) -> str:
    """Только текст знаний: ни id, ни имён файлов, ни номеров абзацев модель не видит."""
    return "\n\n".join(chunk.text for chunk in chunks)


def trim_history(history: Sequence[BaseMessage]) -> list[BaseMessage]:
    """История в пределах бюджета токенов: свежие реплики важнее."""
    return trim_messages(
        list(history),
        max_tokens=HISTORY_TOKEN_BUDGET,
        token_counter=count_tokens_approximately,
        strategy="last",
        start_on="human",
        include_system=False,
    )


def _history_note(total: int, kept: int) -> str:
    return f"{kept} из {total} реплик, бюджет {HISTORY_TOKEN_BUDGET} токенов"


def build_turn_prompt(
    *,
    step: str,
    profile: ClientProfile,
    question: str,
    chunks: Sequence[Chunk] = (),
    history: Sequence[BaseMessage] = (),
    expected_slot: str | None = None,
    said: Sequence[str] = (),
) -> Prompt:
    """Сообщения одного хода: роль и контракт в системном, состояние и знания — в реплике.

    Порядок блоков в сообщении фиксирован (`build_turn_user`): состояние → знания → реплика → задача.
    Реплика и задача стоят в конце — на хвост входа модель опирается сильнее всего.
    """
    kept = trim_history(history)
    state = state_text(step, profile, expected_slot, said)
    fragments = _fragments(chunks)
    system = build_turn_system(step, profile)
    messages: list[BaseMessage] = [
        SystemMessage(content=system),
        *kept,
        HumanMessage(
            content=build_turn_user(step=step, state=state, fragments=fragments, question=question),
        ),
    ]
    return Prompt(
        stage=step,
        system=system,
        history=kept,
        state=state,
        chunks=fragments,
        question=question,
        messages=messages,
    )


def build_chat_model(settings: Settings, max_tokens: int | None = None) -> BaseChatModel:
    """Клиент модели провайдера (ключ только из настроек).

    `max_retries=0` — жёсткое требование «один запрос на ход»: иначе SDK сам повторит запрос
    при 429/5xx. Лимит ответа уходит как `max_tokens` через `extra_body`: langchain-openai 1.8
    переименовал поле в `max_completion_tokens`, а OpenAI-совместимый прокси (polza.ai) понимает
    `max_tokens`.
    """
    return ChatOpenAI(
        model=settings.llm_model,
        base_url=settings.base_url,
        api_key=settings.api_key,
        temperature=settings.temperature,
        timeout=settings.llm_timeout,
        max_retries=0,
        extra_body={"max_tokens": max_tokens if max_tokens is not None else settings.max_tokens},
    )


def build_turn_fn(model: BaseChatModel) -> TurnFn:
    """Функция «промпт хода → поля ответа»: один вызов модели, без повторов и добивок."""

    # json_schema есть не у каждого провайдера: function_calling работает на любом OpenAI-совместимом
    structured = model.with_structured_output(TurnDraft, method="function_calling")

    def turn(prompt: Prompt) -> TurnDraft:
        call = record_call(
            f"turn:{prompt.stage}",
            model_name(model),
            prompt.messages,
            stage=prompt.stage,
            system=prompt.system,
            history=prompt.history,
            inputs={
                "шаг": prompt.stage,
                "состояние": prompt.state,
                "знания": prompt.chunks,
                "реплика клиента": prompt.question.strip(),
            },
        )
        try:
            draft = cast(TurnDraft, structured.invoke(prompt.messages))
        except Exception:
            # второго запроса нет: пустой текст означает «собери ответ кодом»
            logger.exception("модель не ответила на шаге %s", prompt.stage)
            record_output(call, "ошибка: ответ собирает код")
            return TurnDraft()
        record_output(call, draft.model_dump_json())
        return draft

    return turn
