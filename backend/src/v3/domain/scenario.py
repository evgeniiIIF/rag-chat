"""Шаг разговора: чистая функция от профиля и типа реплики.

Шагов ровно шесть, и каждый — это то, что модель делает прямо сейчас:
  ask_debt  — не знаем сумму долга
  ask_region — не знаем регион
  info      — клиент не проходит известный фильтр (сумма/регион): сразу справка, без записи
  invite    — фильтры пройдены: предложение консультации и сбор телефона/времени
  booked    — телефон и время есть: подтверждение записи
  rag       — клиент задал вопрос: ответ по фрагментам документа
"""

from __future__ import annotations

from typing import Literal

from core.behavior import INFO_QUERIES, KNOWLEDGE_STEPS, STEP_QUERIES

__all__ = ["CONTEXT_STEPS", "INFO_QUERIES", "STEP_QUERIES", "expected_slot", "next_step", "search_query"]
from domain.profile import ClientProfile

type Step = Literal["ask_debt", "ask_region", "info", "invite", "booked", "rag"]

# шаги, на которых ответ строится по фрагментам документа
# знания нужны только там, где модель объясняет; на шагах сбора данных она только спрашивает
CONTEXT_STEPS: frozenset[str] = KNOWLEDGE_STEPS


def search_query(step: str, question: str, profile: ClientProfile, kind: str = "situation") -> str:
    """Что искать на шаге: проваленный фильтр на info, тема шага на сборе данных, иначе слова клиента."""
    if step == "info":
        return INFO_QUERIES.get(profile.failed_filter() or "", question.strip())
    if kind != "question" and step in STEP_QUERIES:  # «9996665544» — не поисковый запрос
        return STEP_QUERIES[step]
    return question.strip()


def next_step(profile: ClientProfile, kind: str) -> Step:
    # порядок жёсткий: сначала обязательные фильтры, вопросы клиента — только после них
    if profile.failed_filter() is not None:
        return "info"
    missing = profile.missing_filter()
    if missing == "debt":
        return "ask_debt"
    if missing == "region":
        return "ask_region"
    if kind == "question":
        return "rag"
    if profile.phone is None or profile.consultation_time is None:
        return "invite"
    return "booked"


def expected_slot(profile: ClientProfile) -> str | None:
    """Что бот спросил на прошлом ходу, то клиент сейчас и ответил: debt | region | phone | time | None."""
    step = next_step(profile, "situation")
    if step == "ask_debt":
        return "debt"
    if step == "ask_region":
        return "region"
    if step == "invite":
        return "phone" if profile.phone is None else "time"
    return None
