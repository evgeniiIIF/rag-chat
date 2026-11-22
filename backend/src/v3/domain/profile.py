"""Профиль клиента и правила квалификации (КЦ ¶60).

Только данные и чистые функции. Решения о переходах — в route (graph/build.py),
формулировки — в respond (LLM). Здесь нет текстов ответов и нет if/elif по сценарию.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from core.behavior import (
    FILTER_Q_DEBT,
    FILTER_Q_DEBT_RECHECK,
    FILTER_Q_DEBT_SMALL,
    FILTER_Q_REGION,
    FILTER_Q_REGION_BAD,
)

MIN_DEBT_RUB: int = 350_000

# Исключённые регионы (КЦ ¶60). Код-правило, не факт для клиента.
DEFAULT_EXCLUDED_REGIONS: tuple[str, ...] = (
    "чечня",
    "чеченская",
    "днр",
    "лнр",
    "владимирская",
)

_CLOCK = re.compile(r"\b(\d{1,2})[:.](\d{2})\b")
_HOUR = re.compile(r"\b(\d{1,2})\s*(?:час|часа|часов)\b", re.IGNORECASE)
_DAY = re.compile(r"\b(сегодня|завтра|послезавтра|сейчас|утром|днём|днем|вечером)\b", re.IGNORECASE)


class ClientProfile(BaseModel):
    """Что известно о клиенте и где он в воронке.

    Пять слотов для записи: debt_amount, region, phone, consultation_time, ready_to_wait.
    `facts` — контекст из КЦ-0001 (долги, имущество, сделки), не блокер записи.
    """

    debt_amount: int | None = None
    region: str | None = None
    phone: str | None = None
    consultation_time: str | None = None
    ready_to_wait: bool = False
    invited: bool = False
    stage: Literal["collect", "invited", "booked"] = "collect"
    user_is_angry: bool = False
    wants_consultation: bool = False
    disqualified: bool = False
    facts: dict[str, str] = Field(default_factory=dict)

    def is_booked(self) -> bool:
        """Запись возможна: есть регион, телефон, время и готовность ждать.

        Сумма долга здесь НЕ проверяется: квалификация по debt — отдельно в route (до invite).
        После not_debt (МФЦ-путь) сумма может быть < 350k — это допустимо.
        """
        return (
            not self.disqualified
            and self.region is not None
            and not is_excluded_region(self.region)
            and self.phone is not None
            and self.consultation_time is not None
            and self.ready_to_wait
        )

    def merge(self, fresh: ClientProfile) -> ClientProfile:
        """Свежий разбор поверх известного; слоты не теряются."""
        return self.model_copy(
            update={
                "debt_amount": fresh.debt_amount if fresh.debt_amount is not None else self.debt_amount,
                "region": fresh.region if fresh.region is not None else self.region,
                "phone": fresh.phone if fresh.phone is not None else self.phone,
                "consultation_time": (
                    fresh.consultation_time if fresh.consultation_time is not None else self.consultation_time
                ),
                "ready_to_wait": fresh.ready_to_wait or self.ready_to_wait,
                "invited": fresh.invited or self.invited,
                "stage": fresh.stage if fresh.stage != "collect" else self.stage,
                "user_is_angry": fresh.user_is_angry or self.user_is_angry,
                "wants_consultation": fresh.wants_consultation or self.wants_consultation,
                "disqualified": fresh.disqualified or self.disqualified,
                "facts": {**self.facts, **fresh.facts},
            }
        )

    def with_invite(self) -> ClientProfile:
        return self.model_copy(update={"invited": True, "stage": "invited"})

    def with_debt(self, debt: int | None) -> ClientProfile:
        if not debt:
            return self
        return self.model_copy(update={"debt_amount": debt})

    def with_phone(self, phone: str | None) -> ClientProfile:
        if not phone:
            return self
        return self.model_copy(update={"phone": phone})

    def with_time(self, time: str | None) -> ClientProfile:
        if not time:
            return self
        return self.model_copy(update={"consultation_time": time})

    def with_ready(self) -> ClientProfile:
        # stage=booked ставит только route при is_booked(); готовность — отдельный слот
        return self.model_copy(update={"ready_to_wait": True})

    def with_anger(self) -> ClientProfile:
        return self.model_copy(update={"user_is_angry": True})


def is_excluded_region(region: str) -> bool:
    """Регион в списке исключённых (КЦ ¶60)."""
    low = region.casefold()
    return any(word in low for word in DEFAULT_EXCLUDED_REGIONS if word)


def qualifies_by_debt(debt: int | None) -> bool:
    return debt is not None and debt >= MIN_DEBT_RUB


def filter_question(profile: ClientProfile) -> str | None:
    # вопрос, закрывающий ближайший непройденный фильтр; None — фильтры пройдены
    if profile.debt_amount is None:
        return FILTER_Q_DEBT
    if not qualifies_by_debt(profile.debt_amount):
        return FILTER_Q_DEBT_RECHECK if "debt_checked" in profile.facts else FILTER_Q_DEBT_SMALL
    if profile.region is None:
        return FILTER_Q_REGION
    if is_excluded_region(profile.region):
        return FILTER_Q_REGION_BAD
    return None


def extract_time(text: str) -> str | None:
    """Regex-fallback для узла extract: «14:39», «сегодня в 15», «завтра»."""
    clock = _CLOCK.search(text)
    if clock:
        return f"{clock.group(1)}:{clock.group(2)}"
    hour = _HOUR.search(text)
    if hour:
        return f"{hour.group(1)} часов"
    day = _DAY.search(text)
    return day.group(0).strip() if day else None
