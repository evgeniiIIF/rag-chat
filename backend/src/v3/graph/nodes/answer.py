"""Узел ответа: модель пишет реплику на каждом шаге, кроме подтверждения записи.

Роль и тон задаёт `SYSTEM_PROMPT`, знания приходят абзацами из КЦ.docx (без пометок операторам
и без кейсов других клиентов), вопрос шага дописывает код. Ответ собирает `answer_text`:
суть абзацем, пояснения списком, вопрос отдельным блоком. Вопрос шага модель получает готовым
(`ASK_LINE`) и задаёт своими словами последним; подтверждение записи собирает код.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage

from core.behavior import (
    BOOKING_CONFIRMED,
    SHORT_STEPS,
    STAGE_INSTRUCTIONS,
    SYSTEM_PROMPT,
    info_fallback,
    step_question,
)
from core.formatting import (
    _stems,
    answer_text,
    booked_blocks,
    build_blocks,
    knowledge_text,
    split_question,
)
from domain.graph_state import GraphState
from domain.models import Chunk
from domain.profile import ClientProfile
from domain.scenario import CONTEXT_STEPS, next_step
from graph.nodes import NodeFn, NodeResult
from infrastructure.artifacts import write_json
from infrastructure.llm import AnswerDraft, AnswerFn, build_prompt


def _booking(profile: ClientProfile, step: str) -> dict[str, Any] | None:
    """Запись собираем из профиля, а не из ответа модели: телефон и время модель выдумывает."""
    if step != "booked" or profile.phone is None or profile.consultation_time is None:
        return None
    return {"phone": profile.phone, "date_time": profile.consultation_time, "is_confirmed": True}


def _clean_context(state: GraphState, step: str) -> list[Chunk]:
    """Знания только на шагах, где модель объясняет, и только годные для клиента."""
    if step not in CONTEXT_STEPS:
        return []
    cleaned: list[Chunk] = []
    for hit in state.retrieved:
        text = knowledge_text(hit.chunk.text)
        if text:
            cleaned.append(hit.chunk.model_copy(update={"text": text}))
    return cleaned


_NOISE = re.compile(r"[^\w\s]+")


def _flat(text: str) -> str:
    """Текст без пунктуации и регистра: так сравниваем дословные совпадения."""
    return " ".join(_NOISE.sub(" ", text.lower()).split())


# столько слов подряд, совпавших с абзацем знаний, уже считаем копипастой
COPY_WINDOW = 7


def _windows(text: str) -> set[str]:
    words = _flat(text).split()
    return {" ".join(words[index : index + COPY_WINDOW]) for index in range(len(words) - COPY_WINDOW + 1)}


def _own_words(texts: list[str], fragments: list[Chunk]) -> list[str]:
    """Только пересказ: поле, где есть кусок знаний подряд, выбрасываем."""
    copied: set[str] = set()
    for chunk in fragments:
        copied |= _windows(chunk.text)
    kept: list[str] = []
    for text in texts:
        words = _flat(text).split()
        if len(words) < COPY_WINDOW:
            continue
        if _windows(text) & copied:
            continue
        kept.append(text)
    return kept


def _echo_of_prompt(text: str, prompts: list[str], *, ratio: float = 0.6) -> bool:
    """Модель вернула инструкцию вместо ответа: пересечение основ с промптом >= ratio."""
    stems = _stems(text)
    if not stems:
        return False
    for prompt in prompts:
        prompt_stems = _stems(prompt)
        if prompt_stems and len(stems & prompt_stems) / max(1, len(stems)) >= ratio:
            return True
    return False


def make_answer_node(answer_fn: AnswerFn, artifacts_dir: Path | None = None) -> NodeFn:
    def answer(state: GraphState) -> NodeResult:
        step = next_step(state.profile, state.kind)
        ask = step_question(step, state.profile)
        if step == "booked":
            first = state.previous_step != "booked"
            text = answer_text("", [], "", step, state.profile) if first else BOOKING_CONFIRMED
            return {
                "step": step,
                "answer": text,
                "answer_blocks": booked_blocks() if first else [],
                "answer_booking": _booking(state.profile, step),
                "grounded": False,
                "messages": [AIMessage(content=text)],
            }
        context = _clean_context(state, step)
        prompt = build_prompt(
            step=step,
            profile=state.profile,
            question=state.question,
            chunks=context,
            history=state.messages[:-1],
            ask=ask,
            short=step in SHORT_STEPS,
        )
        draft = answer_fn(prompt)
        if _echo_of_prompt(draft.summary, [SYSTEM_PROMPT, STAGE_INSTRUCTIONS.get(step, "")]):
            draft = draft.model_copy(update={"summary": ""})
        # пересказ вместо копипасты: поле с куском знаний подряд клиенту не отдаём
        own = _own_words([draft.summary], context)
        draft = draft.model_copy(update={"summary": " ".join(own or [draft.summary])})
        said = [str(message.content) for message in state.messages[:-1] if message.type == "ai"]
        text = answer_text(draft.summary, [], draft.question, step, ask=ask, said=said[-3:])
        if step == "info":
            # отказ по фильтру объясняет код: модель здесь сочиняла план ответа вместо текста
            text = info_fallback(state.profile)
        elif not text.strip() and step == "rag":
            # на rag не подставляем случайный фрагмент — просим уточнить
            text = "Уточните, пожалуйста, что именно вас интересует — по сути вопроса подскажу точнее."
        body, reply_question = split_question(text)
        # фактов-плашек нет: клиенту не показываем, откуда взят ответ
        blocks = build_blocks(body, "", reply_question)
        if artifacts_dir:
            write_json(
                artifacts_dir / state.request_id / f"answer_{step}.json",
                {
                    "step": step,
                    "profile": state.profile.model_dump(),
                    "prompt": prompt.dump(),
                    "answer": draft.model_dump(),
                    "text": text,
                },
            )
        return {
            "step": step,
            "answer": body,
            "answer_question": reply_question,
            "answer_blocks": blocks,
            "answer_booking": _booking(state.profile, step),
            "grounded": bool(context),
            "messages": [AIMessage(content=text)],
        }

    return answer
