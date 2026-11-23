"""Узел хода: один запрос модели — разбор реплики, текст клиенту и вопрос.

Что делает код до вызова: тип реплики и шаг по профилю прошлого хода, ожидаемый слот, теневой профиль
по регуляркам (чтобы искать знания уже под тот шаг, который бот озвучит), запросы в индекс и отбор
фрагментов. Модель получает готовый снимок хода и делает две вещи: заполняет слоты и пишет текст.
Что делает код после: применяет слоты правилами, собирает текст, блоки, запись и источники.

Модель не вызывается вовсе: соц-реплика (её забирает `greet`), подтверждение записи, пустая выдача
или отказ по порогу. Повторных запросов нет: непригодный ответ заменяется текстом шага из кода.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage

from core.behavior import (
    BOOKING_CONFIRMED,
    COLLECT_FALLBACK,
    FALLBACK_ANSWER,
    INVITE_FALLBACK,
    KNOWLEDGE_STEPS,
    RAG_FALLBACK,
    SYSTEM_PROMPT,
    TURN_TASKS,
    info_advice,
    info_fallback,
    step_question,
)
from core.formatting import (
    _SENTENCE,
    _stems,
    answer_text,
    booked_blocks,
    build_blocks,
    knowledge_text,
    split_question,
    strip_source_refs,
)
from domain.graph_state import GraphState
from domain.intake import apply_turn, rule_kind, rules_draft
from domain.models import Chunk, RetrievedChunk, TurnDraft
from domain.profile import ClientProfile
from domain.scenario import client_topic, expected_slot, next_step, turn_query
from graph.nodes import NodeFn, NodeResult, SearchFn
from infrastructure.artifacts import write_json
from infrastructure.llm import Prompt, TurnFn, build_turn_prompt

# фрагмент знаний: два первых целиком, остальные короче — так нужный факт не уезжает за обрезку
FULL_CHUNK_CHARS = 1200
SHORT_CHUNK_CHARS = 600
# сколько последних ответов бота учитывать в антиповторе
SAID_WINDOW = 3

# причина отказа должна быть названа клиенту словами, а не подразумеваться
_REGION_REASON = re.compile(
    r"(?i)(?:регион|прописк)\w*[^.?!]{0,60}(?:не\s+(?:провод|работа|обслуж|возьм|бер))"
    r"|(?:не\s+(?:провод|работа|возьм|бер))\w*[^.?!]{0,40}(?:регион|прописк)"
)
_DEBT_REASON = re.compile(r"350[\s\u00a0]?000|порог\w*")


def _gate(step: str, profile: ClientProfile) -> str:
    """Жёсткий гейт: без пройденных фильтров записи и консультации не бывает."""
    if not profile.filters_ok() and step in {"invite", "booked"}:
        return "info"
    return step


def _booking(profile: ClientProfile, step: str) -> dict[str, Any] | None:
    """Запись собираем из профиля, а не из ответа модели: телефон и время модель выдумывает."""
    if step != "booked" or profile.phone is None or profile.consultation_time is None:
        return None
    return {"phone": profile.phone, "date_time": profile.consultation_time, "is_confirmed": True}


def _said(state: GraphState) -> list[str]:
    """Что бот уже говорил: прошлые ответы для антиповтора."""
    return [str(message.content) for message in state.messages[:-1] if message.type == "ai"]


def _previous_question(state: GraphState) -> str:
    """Прошлая реплика клиента: по ней ищем, если текущая — короткий follow-up."""
    for message in reversed(state.messages[:-1]):
        if message.type == "human":
            return str(message.content)
    return ""


def _fuse(batches: Sequence[Sequence[RetrievedChunk]], limit: int) -> list[RetrievedChunk]:
    """Слияние выдач по нескольким запросам: лучший score на фрагмент, затем порядок по score."""
    best: dict[str, RetrievedChunk] = {}
    for batch in batches:
        for hit in batch:
            current = best.get(hit.chunk.id)
            if current is None or hit.score > current.score:
                best[hit.chunk.id] = hit
    ordered = sorted(best.values(), key=lambda hit: hit.score, reverse=True)[:limit]
    return [hit.model_copy(update={"rank": index}) for index, hit in enumerate(ordered, 1)]


def _knowledge(hits: Sequence[RetrievedChunk], question: str) -> list[Chunk]:
    """Текст фрагментов для промпта: без инструкций операторам, по теме реплики, с обрезкой.

    Если по теме не осталось ни одного предложения (реплика «да, давайте»), берём фрагмент целиком:
    на шагах сбора данных клиенту нужен ответ по существу, а не пустой блок знаний.
    """
    topic = client_topic(question)
    chunks: list[Chunk] = []
    for index, hit in enumerate(hits):
        text = knowledge_text(hit.chunk.text, topic) or knowledge_text(hit.chunk.text)
        if not text:
            continue
        limit = FULL_CHUNK_CHARS if index < 2 else SHORT_CHUNK_CHARS
        if len(text) > limit:
            text = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
        chunks.append(hit.chunk.model_copy(update={"text": text}))
    return chunks


def _combine(base: TurnDraft, draft: TurnDraft) -> TurnDraft:
    """Слоты модели поверх правил: правила заполняют то, что модель пропустила."""
    return draft.model_copy(
        update={
            "kind": draft.kind or base.kind,
            "debt_amount": draft.debt_amount if draft.debt_amount is not None else base.debt_amount,
            "region": draft.region or base.region,
            "phone": draft.phone or base.phone,
            "consultation_time": draft.consultation_time or base.consultation_time,
            "facts": {**base.facts, **draft.facts},
        }
    )


def _fallback_text(step: str, profile: ClientProfile) -> str:
    """Ответ шага без модели: причина отказа, текст сбора данных или просьба уточнить."""
    if step == "info":
        return info_fallback(profile)
    if step in COLLECT_FALLBACK:
        return COLLECT_FALLBACK[step]
    if step == "invite":
        return INVITE_FALLBACK
    if step == "rag":
        return RAG_FALLBACK
    return FALLBACK_ANSWER


def _names_reason(text: str, profile: ClientProfile) -> bool:
    """Клиент узнал, почему процедура не подходит: названа причина, а не только «препятствий нет»."""
    if profile.failed_filter() == "region":
        return bool(_REGION_REASON.search(text))
    return bool(_DEBT_REASON.search(text))


def _repeats(text: str, said: Sequence[str], *, ratio: float = 0.7) -> bool:
    """Ответ повторяет предыдущий: те же основы слов в той же доле — клиент читает одно и то же дважды."""
    if not said or not text.strip():
        return False
    new = _stems(text)
    if not new:
        return False
    return max((len(new & _stems(old)) / len(new) for old in said), default=0.0) >= ratio


def _echo_of_prompt(text: str, prompts: Sequence[str], *, ratio: float = 0.6) -> bool:
    """Модель вернула инструкцию вместо ответа: пересечение основ с промптом >= ratio."""
    stems = _stems(text)
    if not stems:
        return False
    for prompt in prompts:
        prompt_stems = _stems(prompt)
        if prompt_stems and len(stems & prompt_stems) / max(1, len(stems)) >= ratio:
            return True
    return False


def _without_question(text: str) -> str:
    """Убрать вопрос из конца текста модели: вопрос задаёт код, иначе клиент получит два вопроса подряд."""
    sentences = [sentence.strip() for sentence in _SENTENCE.split(" ".join(text.split())) if sentence.strip()]
    while sentences and sentences[-1].endswith("?"):
        sentences.pop()
    return " ".join(sentences)


def _accept_text(text: str, step: str, profile: ClientProfile, said: Sequence[str]) -> str:
    """Текст модели или детерминированный ответ шага: второй попытки у модели нет."""
    clean = strip_source_refs(text).strip()
    if not clean or _echo_of_prompt(clean, [SYSTEM_PROMPT, TURN_TASKS.get(step, "")]):
        clean = _fallback_text(step, profile)
    elif step == "info" and not _names_reason(clean, profile):
        # причину отказа называет код: без неё клиент не понимает, почему не подходит
        clean = info_fallback(profile)
    answered = clean
    if said and _repeats(answered, said[-1:]):
        # тот же абзац второй раз не отправляем: на info есть вторая грань — что делать
        answered = info_advice(profile) if step == "info" else _fallback_text(step, profile)
    return answered


def make_turn_node(
    turn_fn: TurnFn,
    search: SearchFn,
    threshold: float,
    artifacts_dir: Path | None = None,
) -> NodeFn:
    def turn(state: GraphState) -> NodeResult:
        previous = state.profile
        said = _said(state)
        expected = expected_slot(previous)  # что бот спросил прошлой репликой
        kind = rule_kind(state.question)
        base = rules_draft(state.question, expected)
        shadow, _ = apply_turn(previous, state.question, base, expected=expected)
        step = _gate(next_step(shadow, kind), shadow)

        queries: list[str] = []
        hits: list[RetrievedChunk] = []
        chunks: list[Chunk] = []
        if step in KNOWLEDGE_STEPS:
            queries = turn_query(step, state.question, shadow, kind, _previous_question(state))
            hits = _fuse([search(query, state.k) for query in queries], state.k)
            hits = [hit for hit in hits if hit.score >= threshold]
            chunks = _knowledge(hits, state.question)

        prompt: Prompt | None = None
        draft: TurnDraft | None = None
        model_text = ""
        profile, kind_final = shadow, kind
        if step == "booked":  # запись: слоты уже разобраны правилами, модель не нужна
            pass
        elif chunks:  # единственный запрос модели за ход
            prompt = build_turn_prompt(
                step=step,
                profile=shadow,
                question=state.question,
                chunks=chunks,
                history=state.messages[:-1],
                expected_slot=expected,
                said=said,
            )
            draft = turn_fn(prompt)
            model_text = draft.text
            profile, kind_final = apply_turn(previous, state.question, _combine(base, draft), expected=expected)

        step_final = _gate(next_step(profile, kind_final), profile)
        ask = step_question(step_final, profile, state.previous_step)
        if step_final == "booked":
            first = state.previous_step != "booked"
            text = answer_text("", [], "", "booked", profile=profile) if first else BOOKING_CONFIRMED
            body, reply_question = text, ""
            blocks = booked_blocks() if first else []
            answer = text
        else:
            clean = _accept_text(model_text, step_final, profile, said)
            if ask:  # свой вопрос модель не пишет: вопрос шага задаёт код
                clean = _without_question(clean) or clean
            text = answer_text(clean, [], "", step_final, profile=profile, ask=ask, said=said[-SAID_WINDOW:])
            body, reply_question = split_question(text)
            blocks = build_blocks(body, "", reply_question)
            answer = body

        if artifacts_dir:
            write_json(
                artifacts_dir / state.request_id / f"turn_{step_final}.json",
                {
                    "step": step_final,
                    "expected_slot": expected,
                    "kind": kind_final,
                    "queries": queries,
                    "profile_before": previous.model_dump(),
                    "profile": profile.model_dump(),
                    "retrieved": [hit.chunk.id for hit in hits],
                    "prompt": prompt.dump() if prompt is not None else None,
                    "draft": draft.model_dump() if draft is not None else None,
                    "text": text,
                },
            )
        return {
            "profile": profile,
            "kind": kind_final,
            "step": step_final,
            "search_query": " | ".join(queries),
            "retrieved": hits,
            "grounded": bool(chunks),
            "answer": answer,
            "answer_question": reply_question,
            "answer_blocks": blocks,
            "answer_booking": _booking(profile, step_final),
            "messages": [AIMessage(content=text)],
        }

    return turn
