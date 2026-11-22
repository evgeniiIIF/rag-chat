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

from domain.profile import ClientProfile

type Step = Literal["ask_debt", "ask_region", "info", "invite", "booked", "rag"]

# шаги, на которых ответ строится по фрагментам документа
CONTEXT_STEPS: frozenset[str] = frozenset({"rag", "info"})

# что искать в КЦ на каждом шаге: реплика клиента подходит не всегда («800 тысяч», «ставрополь»)
STEP_QUERIES: dict[str, str] = {
    "ask_debt": "минимальная сумма долга, с которой берут в процедуру банкротства",
    "ask_region": "в каких регионах компания работает, регион прописки клиента",
    "info": "что делать, если сумма долга меньше 350 000 или регион не обслуживается",
    "invite": "бесплатная консультация юриста: как проходит, что входит, сколько ждать",
    "booked": "что подготовить клиенту к консультации с юристом",
}


# на шаге info важно, какой именно фильтр провален: ищем то, что предложить вместо процедуры
INFO_QUERIES: dict[str, str] = {
    "debt": "сумма долга меньше 350 000 — что предложить клиенту вместо банкротства",
    "region": "регион вне работы компании — что предложить клиенту вместо банкротства",
}


def info_query(profile: ClientProfile) -> str:
    return INFO_QUERIES.get(profile.failed_filter() or "", STEP_QUERIES["info"])


def search_query(step: str, question: str, profile: ClientProfile) -> str:
    """Поисковый запрос шага: вопрос клиента как есть, иначе — суть того, что делаем сейчас."""
    if step == "rag":
        return question.strip()
    if step == "info":
        return info_query(profile)
    return STEP_QUERIES.get(step, question.strip())


def next_step(profile: ClientProfile, kind: str) -> Step:
    if kind == "question":
        return "rag"
    # непрохождение любого известного фильтра — сразу справка: следующие вопросы не задаём
    if profile.failed_filter() is not None:
        return "info"
    missing = profile.missing_filter()
    if missing == "debt":
        return "ask_debt"
    if missing == "region":
        return "ask_region"
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
