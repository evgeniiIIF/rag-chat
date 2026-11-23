"""Узел ответа: модель пишет реплику на каждом шаге, кроме подтверждения записи.

Роль и тон задаёт `SYSTEM_PROMPT`, знания приходят абзацами из КЦ.docx целиком (примеры из практики
тоже: модель объясняет ими правила), вопрос шага дописывает код. Ответ собирает `answer_text`:
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
    COLLECT_FALLBACK,
    SHORT_STEPS,
    STAGE_INSTRUCTIONS,
    SYSTEM_PROMPT,
    info_advice,
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
from domain.scenario import CONTEXT_STEPS, client_topic, next_step
from graph.nodes import NodeFn, NodeResult
from infrastructure.artifacts import write_json
from infrastructure.llm import AnswerFn, build_prompt


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
        text = knowledge_text(hit.chunk.text, client_topic(state.question))
        if text:
            cleaned.append(hit.chunk.model_copy(update={"text": text}))
    return cleaned


# причина отказа должна быть названа клиенту словами, а не подразумеваться
_REGION_REASON = re.compile(
    r"(?i)(?:регион|прописк)\w*[^.?!]{0,60}(?:не\s+(?:провод|работа|обслуж|возьм|бер))"
    r"|(?:не\s+(?:провод|работа|возьм|бер))\w*[^.?!]{0,40}(?:регион|прописк)"
)
_DEBT_REASON = re.compile(r"350[\s\u00a0]?000|порог\w*")


def _names_reason(text: str, profile: ClientProfile) -> bool:
    """Клиент узнал, почему процедура не подходит: названа причина, а не только «препятствий нет»."""
    if profile.failed_filter() == "region":
        return bool(_REGION_REASON.search(text))
    return bool(_DEBT_REASON.search(text))


def _repeats(text: str, said: list[str], *, ratio: float = 0.7) -> bool:
    """Ответ повторяет предыдущий: те же основы слов в той же доле — клиент читает одно и то же дважды."""
    if not said or not text.strip():
        return False
    new = _stems(text)
    if not new:
        return False
    return max((len(new & _stems(old)) / len(new) for old in said), default=0.0) >= ratio


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
        if not state.profile.filters_ok() and step in {"invite", "booked"}:
            # жёсткий гейт: без пройденных фильтров записи и консультации не бывает
            step = "info"
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
        prompts = [SYSTEM_PROMPT, STAGE_INSTRUCTIONS.get(step, "")]
        draft = answer_fn(prompt)
        attempts = 0
        while attempts < 2 and (
            not draft.text.strip()
            or not answer_text(draft.text, [], "", step, ask="").strip()
            or _echo_of_prompt(draft.text, prompts)
        ):
            # модель описала ответ или написала о клиенте в третьем лице — просим текст ещё раз
            attempts += 1
            retry = answer_fn(
                build_prompt(
                    step=step,
                    profile=state.profile,
                    question=state.question,
                    chunks=context,
                    history=state.messages[:-1],
                    ask=ask,
                    short=step in SHORT_STEPS,
                    strict=True,
                ),
            )
            if answer_text(retry.text, [], "", step, ask="").strip() and not _echo_of_prompt(retry.text, prompts):
                draft = retry
                break
            draft = retry.model_copy(update={"text": ""})
        said = [str(message.content) for message in state.messages[:-1] if message.type == "ai"]
        text = answer_text(draft.text, [], draft.question, step, ask=ask, said=said[-3:])
        body_only = answer_text(draft.text, [], "", step, ask="")
        if step == "info" and not body_only.strip():
            # модель промолчала — отказ объясняет код, чтобы клиент не остался без ответа
            text = info_fallback(state.profile)
        elif step == "info" and not _names_reason(text, state.profile):
            # модель сказала «по сумме препятствий нет» и промолчала о настоящей причине — называем её сами
            text = info_fallback(state.profile)
        elif not body_only.strip() and step == "rag":
            # на rag не подставляем случайный фрагмент — просим уточнить
            text = "Уточните, пожалуйста, что именно вас интересует — по сути вопроса подскажу точнее."
        elif not body_only.strip() and step in COLLECT_FALLBACK:
            # вопрос без объяснения клиенту не отправляем: короткая суть из знаний плюс вопрос шага
            text = answer_text(COLLECT_FALLBACK[step], [], "", step, ask=ask)
        if step == "info":
            if said:  # отказ уже прозвучал: повторять тот же абзац нельзя — объясняем, что делать
                text = answer_text(info_advice(state.profile), [], "", step, ask="")
            if not _names_reason(text, state.profile) or _repeats(text, said[-1:]):
                # причина названа всегда; одну и ту же подсказку дважды не отправляем
                text = info_fallback(state.profile)
        elif _repeats(text, said[-1:]) and body_only.strip():
            retry = answer_fn(
                build_prompt(
                    step=step,
                    profile=state.profile,
                    question=state.question,
                    chunks=context,
                    history=state.messages[:-1],
                    ask=ask,
                    short=step in SHORT_STEPS,
                    strict=True,
                ),
            )
            fresh = answer_text(retry.text, [], retry.question, step, ask=ask, said=said[-3:])
            if fresh.strip() and not _repeats(fresh, said[-1:]):
                text = fresh
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
