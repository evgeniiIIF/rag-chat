"""Адаптер модели: промпт консультанта (только по фрагментам) и структурный ответ.

Модель вызывается через `ChatOpenAI.with_structured_output(AnswerDraft)`, поэтому формат
ответа задаёт схема, а не разбор строк (`research.md`, R4/R5).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Literal, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.messages.utils import count_tokens_approximately, trim_messages
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from core.behavior import (
    CONDENSE_SYSTEM_PROMPT,
    FRAGMENTS_HEADER,
    HISTORY_TOKEN_BUDGET,
    INTAKE_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
)
from core.config import Settings
from domain.models import Chunk
from domain.profile import ClientProfile

logger = logging.getLogger(__name__)

CONDENSE_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", CONDENSE_SYSTEM_PROMPT),
        MessagesPlaceholder("history", optional=True),
        ("human", "Последний вопрос: {question}\n\nСамостоятельный вопрос:"),
    ]
)

PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Ты переписываешь последний вопрос клиента в самостоятельный вопрос.\n"
            "Правила:\n"
            "1. Подставь детали из предыдущих реплик (какой долг, какое имущество, о чём шла речь).\n"
            "2. Не отвечай на вопрос и ничего не добавляй от себя.\n"
            "3. Сохрани смысл и язык клиента.\n"
            "4. Верни только текст вопроса, без пояснений.",
        ),
        MessagesPlaceholder("history", optional=True),
        ("human", "Последний вопрос: {question}\n\nСамостоятельный вопрос:"),
    ]
)

PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder("history", optional=True),
        ("human", "Вопрос: {question}\n\n" + FRAGMENTS_HEADER + "\n{fragments}"),
    ]
)


INTAKE_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", INTAKE_SYSTEM_PROMPT),
        MessagesPlaceholder("history", optional=True),
        ("human", "Реплика клиента: {question}"),
    ]
)


class IntakeDraft(BaseModel):
    """Разбор реплики: вопрос по правилам или рассказ о своей ситуации + слоты профиля."""

    kind: Literal["question", "situation"] = Field(
        description="question — вопрос про правила процедуры, situation — про себя или общий вопрос"
    )
    debt_amount: int | None = Field(default=None, description="сумма долга в рублях, если названа")
    region: str | None = Field(default=None, description="регион прописки, если назван")
    has_property: bool | None = Field(default=None, description="есть ли квартира, машина, ипотека, залог")

    def profile(self) -> ClientProfile:
        """Слоты разбора → профиль клиента."""
        return ClientProfile(debt_amount=self.debt_amount, region=self.region, has_property=self.has_property)


class AnswerDraft(BaseModel):
    """Структурный ответ модели: суть, факты пунктами, следующий шаг и опора на выдержки."""

    answer: str = Field(min_length=1, description="одна короткая фраза с сутью ответа")
    points: list[str] = Field(default_factory=list, description="2-4 конкретных факта из выдержек")
    next_step: str | None = Field(default=None, description="что клиенту сделать дальше, одна фраза")
    grounded: bool
    used_chunk_ids: list[str] = Field(default_factory=list)


StructuredInvoke = Callable[[list[BaseMessage]], AnswerDraft]
CondenseFn = Callable[[str, Sequence[BaseMessage]], str]
type IntakeFn = Callable[[str, Sequence[BaseMessage]], IntakeDraft]


def build_messages(question: str, chunks: Sequence[Chunk], history: Sequence[BaseMessage] = ()) -> list[BaseMessage]:
    """Сообщения модели: инструкция + история диалога (обрезанная) + вопрос с фрагментами."""
    fragments = "\n\n".join(
        f"[{chunk.id}] (фрагмент {chunk.paragraph_start}-{chunk.paragraph_end} файла {chunk.source})\n{chunk.text}"
        for chunk in chunks
    )
    return PROMPT.format_messages(history=trim_history(history), question=question, fragments=fragments)


def trim_history(history: Sequence[BaseMessage]) -> list[BaseMessage]:
    """Штатная обрезка истории: последние реплики в пределах бюджета токенов."""
    return trim_messages(
        list(history),
        max_tokens=HISTORY_TOKEN_BUDGET,
        token_counter=count_tokens_approximately,
        strategy="last",
        start_on="human",
        include_system=False,
    )


def build_chat_model(settings: Settings) -> BaseChatModel:
    """Клиент модели провайдера (ключ только из настроек).

    Лимит ответа уходит как `max_tokens` через `extra_body`: langchain-openai 1.8 переименовал
    поле в `max_completion_tokens`, а OpenAI-совместимый прокси (polza.ai) понимает `max_tokens`.
    """
    return ChatOpenAI(
        model=settings.llm_model,
        base_url=settings.base_url,
        api_key=settings.api_key,
        temperature=settings.temperature,
        extra_body={"max_tokens": settings.max_tokens},
    )


def build_structured_model(settings: Settings) -> StructuredInvoke:
    """Функция «сообщения → AnswerDraft» поверх клиента со структурным выводом."""
    model = build_chat_model(settings).with_structured_output(AnswerDraft)

    def invoke(messages: list[BaseMessage]) -> AnswerDraft:
        draft = model.invoke(messages)
        if not isinstance(draft, AnswerDraft):
            raise TypeError(f"модель вернула {type(draft).__name__}, ожидался AnswerDraft")
        return draft

    return invoke


def build_intake(model: BaseChatModel) -> IntakeFn:
    """Функция разбора реплики (узел intake): модель, но с безопасным фолбэком."""
    structured = model.with_structured_output(IntakeDraft)

    def intake(question: str, history: Sequence[BaseMessage]) -> IntakeDraft:
        messages = INTAKE_PROMPT.format_messages(history=trim_history(history), question=question)
        try:
            return cast(IntakeDraft, structured.invoke(messages))
        except Exception:  # сбой разбора не должен ломать сценарий: считаем реплику вопросом
            logger.warning("не удалось разобрать реплику клиента, считаем её вопросом", exc_info=True)
            return IntakeDraft(kind="question")

    return intake


def build_condense(model: BaseChatModel) -> CondenseFn:
    """Функция «вопрос + история → самостоятельный вопрос» (узел condense)."""

    def condense(question: str, history: Sequence[BaseMessage]) -> str:
        messages = CONDENSE_PROMPT.format_messages(history=trim_history(history), question=question)
        try:
            text = model.invoke(messages).content
        except Exception:  # без переписывания ищем по исходному вопросу
            logger.warning("не удалось переписать follow-up, ищем по исходной реплике", exc_info=True)
            return question
        rewritten = text.strip() if isinstance(text, str) else ""
        return rewritten or question

    return condense
