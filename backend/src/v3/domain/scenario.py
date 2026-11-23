"""Шаг разговора: чистая функция от профиля и типа реплики.

Шагов ровно шесть, и каждый — это то, что модель делает прямо сейчас:
  ask_debt  — не знаем сумму долга
  ask_region — не знаем регион
  info      — клиент не проходит известный фильтр (сумма/регион): сразу справка, без записи
  invite    — фильтры пройдены: сначала предложение консультации, затем сбор телефона/времени
  booked    — телефон и время есть: подтверждение записи
  rag       — клиент задал вопрос: ответ по фрагментам документа
"""

from __future__ import annotations

import re
from typing import Literal

from core.behavior import INFO_QUERIES, KNOWLEDGE_STEPS, STEP_QUERIES

__all__ = [
    "CONTEXT_STEPS",
    "INFO_QUERIES",
    "STEP_QUERIES",
    "client_topic",
    "expected_slot",
    "next_step",
    "search_query",
]
from domain.profile import ClientProfile

type Step = Literal["ask_debt", "ask_region", "info", "invite", "booked", "rag"]

# шаги, на которых ответ строится по фрагментам документа
# знания нужны только там, где модель объясняет; на шагах сбора данных она только спрашивает
CONTEXT_STEPS: frozenset[str] = KNOWLEDGE_STEPS


# «310 000», «+7 999 666-55-44», «310 тысяч рублей» — данные слота, а не тема разговора
_SLOT_ONLY = re.compile(r"(?i)^[\d\s\-+()₽.,]*(?:тыс\w*|тысяч\w*|руб\w*|млн\w*|миллион\w*|к)?[\d\s\-+()₽.,]*$")

# «ну и что», «а как же», «да нет» — реплика без темы, искать по ней нечего
_TOPIC_STOP = frozenset(
    {
        "а",
        "и",
        "но",
        "да",
        "нет",
        "не",
        "ну",
        "что",
        "как",
        "так",
        "это",
        "вот",
        "же",
        "ли",
        "бы",
        "вы",
        "ты",
        "мы",
        "мне",
        "вас",
        "ему",
        "еще",
        "ещё",
        "уже",
        "теперь",
        "тогда",
        "дальше",
        "делать",
    }
)

# «долг 800 тысяч» — тоже данные слота, хотя в реплике есть слово
_SLOT_WORDS = frozenset({"долг", "долга", "долгов", "сумма", "сумму", "всего", "общий", "общая"})


def client_topic(question: str) -> str:
    """Слова клиента, если в них есть тема: «имущество есть, платить нечем» — тема, «310к» — нет."""
    text = " ".join(question.split())
    words = text.split()
    if not text or _SLOT_ONLY.match(text) or len(words) < 2:
        return ""
    meaningful = [word for word in words if not _SLOT_ONLY.match(word.strip(".,?!:;-"))]
    if all(word.strip(".,?!:;-").lower() in _TOPIC_STOP | _SLOT_WORDS for word in meaningful):
        return ""
    return text


def search_query(step: str, question: str, profile: ClientProfile, kind: str = "situation") -> str:
    """Что искать: проваленный фильтр или тема шага плюс тема реплики клиента.

    Раньше на сборе данных искали одну зашитую фразу и отвечали не на то, о чём спросил клиент.
    """
    if step == "info":
        base = INFO_QUERIES.get(profile.failed_filter() or "", question.strip())
    elif kind != "question" and step in STEP_QUERIES:
        base = STEP_QUERIES[step]
    else:
        return question.strip()
    topic = client_topic(question)
    return f"{base}. Клиент спрашивает: {topic}" if topic and topic not in base else base


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
