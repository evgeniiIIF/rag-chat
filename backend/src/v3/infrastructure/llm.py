"""Адаптер модели: сборка запроса по шагу, разбор реплики и переписывание follow-up.

Текст промптов живёт в `core/behavior.py`, здесь — только сборка сообщений и вызов модели.
Каждый вызов пишется в трейс (`core/trace.py`): что ушло и что вернулось.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.messages.utils import count_tokens_approximately, trim_messages
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from core.behavior import (
    CONDENSE_SYSTEM_PROMPT,
    FRAGMENTS_HEADER,
    HISTORY_TOKEN_BUDGET,
    INTAKE_SYSTEM_PROMPT,
    MISSING_HINTS,
    STAGE_INSTRUCTIONS,
    SYSTEM_PROMPT,
)
from core.config import Settings
from core.trace import model_name, record_call, record_output
from domain.models import Chunk
from domain.profile import ClientProfile, filter_state_text, profile_text

logger = logging.getLogger(__name__)

type StepName = Literal["ask_debt", "ask_region", "info", "invite", "booked", "rag"]
type IntakeFn = Callable[[str, Sequence[BaseMessage]], "IntakeDraft"]
type CondenseFn = Callable[[str, Sequence[BaseMessage]], str]
type AnswerFn = Callable[["Prompt"], str]


@dataclass(frozen=True)
class Prompt:
    """Запрос к модели, разложенный по частям: шаг, промпт, история, вход, сообщения."""

    stage: str
    system: str
    history: Sequence[BaseMessage]
    inputs: dict[str, str]
    messages: list[BaseMessage] = field(default_factory=list)

    def dump(self) -> dict[str, object]:
        """Как запрос сохраняется в артефакты и уходит на фронтенд."""
        return {
            "stage": self.stage,
            "system": self.system,
            "history": [_message(message) for message in self.history],
            "inputs": self.inputs,
            "messages": [_message(message) for message in self.messages],
        }


class IntakeDraft(BaseModel):
    """Разбор реплики: тип + слоты профиля."""

    kind: Literal["question", "situation"] = Field(
        description="question — вопрос про правила/сроки/цену; situation — рассказ о себе"
    )
    debt_amount: int | None = Field(default=None, description="общая сумма долга в рублях, если названа")
    region: str | None = Field(default=None, description="регион прописки, если назван")
    phone: str | None = Field(default=None, description="телефон, если назван")
    consultation_time: str | None = Field(default=None, description="удобное время звонка, если названо")
    facts: dict[str, str] = Field(default_factory=dict, description="деловые факты о клиенте своими словами")


def _message(message: BaseMessage) -> dict[str, str]:
    return {"role": message.type, "content": str(message.content)}


def _fragments(chunks: Sequence[Chunk]) -> str:
    """Только текст знаний: ни id, ни имён файлов, ни номеров абзацев модель не видит."""
    return "\n\n".join(chunk.text for chunk in chunks)


def _missing_hint(profile: ClientProfile) -> str:
    missing = profile.missing_filter()
    if missing is None:
        return ""
    return f" В конце задай один вопрос: {MISSING_HINTS[missing]}."


def _offer_guard(profile: ClientProfile) -> str:
    """Запись можно предлагать только тем, кто прошёл фильтры.

    Фильтры собраны и не пройдены — запрет звучит на любом шаге, включая ответ на вопрос:
    иначе модель снова позовёт на консультацию того, кому компания не помогает.
    """
    if profile.missing_filter() is not None or profile.filters_ok():
        return ""
    return " Клиент не проходит условия компании: не предлагай консультацию, звонок и не проси телефон."


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


def build_prompt(
    *,
    step: str,
    profile: ClientProfile,
    question: str,
    chunks: Sequence[Chunk] = (),
    history: Sequence[BaseMessage] = (),
) -> Prompt:
    """Сообщения для модели на текущем шаге: роль + история + профиль + фрагменты + реплика."""
    fragments = _fragments(chunks)
    # подсказку про недостающий фильтр добавляем только к ответу по вопросу:
    # на шагах ask_debt/ask_region об этом уже говорит инструкция шага
    hint = _missing_hint(profile) if step == "rag" else ""
    system = SYSTEM_PROMPT + "\n\n" + STAGE_INSTRUCTIONS.get(step, "") + hint + _offer_guard(profile)
    kept = trim_history(history)
    human_parts = [
        f"Состояние фильтров: {filter_state_text(profile)}",
        f"Что известно о клиенте: {profile_text(profile)}",
    ]
    if fragments:
        human_parts.append(f"{FRAGMENTS_HEADER}\n{fragments}")
    human_parts.append(f"Текущая реплика клиента: {question.strip()}")
    messages: list[BaseMessage] = [SystemMessage(content=system), *kept, HumanMessage(content="\n\n".join(human_parts))]
    return Prompt(
        stage=step,
        system=system,
        history=kept,
        inputs={
            "шаг": step,
            "состояние фильтров": filter_state_text(profile),
            "профиль": profile_text(profile),
            "фрагменты": fragments,
            "реплика клиента": question.strip(),
            "история": _history_note(len(history), len(kept)),
        },
        messages=messages,
    )


def build_chat_model(settings: Settings, max_tokens: int | None = None) -> BaseChatModel:
    """Клиент модели провайдера (ключ только из настроек).

    Лимит ответа уходит как `max_tokens` через `extra_body`: langchain-openai 1.8 переименовал
    поле в `max_completion_tokens`, а OpenAI-совместимый прокси (polza.ai) понимает `max_tokens`.
    """
    return ChatOpenAI(
        model=settings.llm_model,
        base_url=settings.base_url,
        api_key=settings.api_key,
        temperature=settings.temperature,
        extra_body={"max_tokens": max_tokens if max_tokens is not None else settings.max_tokens},
    )


def build_answer_fn(model: BaseChatModel) -> AnswerFn:
    """Функция «промпт шага → текст ответа» с записью в трейс."""

    def answer(prompt: Prompt) -> str:
        call = record_call(
            f"answer:{prompt.stage}",
            model_name(model),
            prompt.messages,
            stage=prompt.stage,
            system=prompt.system,
            history=prompt.history,
            inputs=prompt.inputs,
        )
        try:
            text = model.invoke(prompt.messages).content
        except Exception:
            logger.exception("модель не ответила на шаге %s", prompt.stage)
            record_output(call, "ошибка модели")
            raise
        reply = text.strip() if isinstance(text, str) else str(text).strip()
        record_output(call, reply)
        return reply

    return answer


def build_intake(model: BaseChatModel) -> IntakeFn:
    """Разбор реплики: короткий JSON. Сбой разбора не ломает разговор — считаем реплику вопросом."""
    structured = model.with_structured_output(IntakeDraft)

    def intake(question: str, history: Sequence[BaseMessage]) -> IntakeDraft:
        kept = trim_history(history)
        messages: list[BaseMessage] = [
            SystemMessage(content=INTAKE_SYSTEM_PROMPT),
            *kept,
            HumanMessage(content=f"Реплика клиента: {question}"),
        ]
        call = record_call(
            "intake",
            model_name(model),
            messages,
            stage="intake",
            system=INTAKE_SYSTEM_PROMPT,
            history=kept,
            inputs={"реплика клиента": question, "история": _history_note(len(history), len(kept))},
        )
        try:
            draft = cast(IntakeDraft, structured.invoke(messages))
        except Exception:
            logger.warning("не удалось разобрать реплику, считаем её вопросом", exc_info=True)
            record_output(call, "ошибка разбора: реплика считается вопросом")
            return IntakeDraft(kind="question")
        record_output(call, draft.model_dump_json())
        return draft

    return intake


def build_condense(model: BaseChatModel) -> CondenseFn:
    """Переписывание follow-up в самостоятельный вопрос для поиска."""

    def condense(question: str, history: Sequence[BaseMessage]) -> str:
        kept = trim_history(history)
        messages: list[BaseMessage] = [
            SystemMessage(content=CONDENSE_SYSTEM_PROMPT),
            *kept,
            HumanMessage(content=f"Последний вопрос: {question}\n\nСамостоятельный вопрос:"),
        ]
        call = record_call(
            "condense",
            model_name(model),
            messages,
            stage="condense",
            system=CONDENSE_SYSTEM_PROMPT,
            history=kept,
            inputs={"последняя реплика": question, "история": _history_note(len(history), len(kept))},
        )
        try:
            text = model.invoke(messages).content
        except Exception:
            logger.warning("не удалось переписать follow-up, ищем по исходной реплике", exc_info=True)
            record_output(call, f"ошибка: ищем по исходной реплике «{question}»")
            return question
        rewritten = text.strip() if isinstance(text, str) else ""
        record_output(call, rewritten or question)
        return rewritten or question

    return condense
