"""Профиль клиента и сценарий консультации (документ ¶59-¶60).

Сценарий — правило, а не модель: сначала выясняем сумму долга, потом регион прописки,
потом имущество. Как только ситуация квалифицирована — зовём на бесплатную консультацию.

Состояние сценария (этап, приглашение, время, агрессия) живёт в самом профиле: так
приглашение не повторяется, а «да» фиксирует запись. Слияние с прошлым ходом — `merge`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal

from core.behavior import (
    ANGRY_REPLY,
    ASK_DEBT,
    ASK_REGION,
    BOOK_CONFIRM,
    BOOK_DONE,
    INVITE,
    NOT_OUR_CASE_DEBT,
    NOT_OUR_CASE_REGION,
)

type Qualification = Literal["ok", "small_debt", "excluded_region"]
type Stage = Literal["qualify", "invited", "booked"]

_CLOCK = re.compile(r"\b(\d{1,2})[:.](\d{2})\b")
_HOUR = re.compile(r"\b(\d{1,2})\s*(?:час|часа|часов)\b", re.IGNORECASE)
_DAY = re.compile(r"\b(сегодня|завтра|послезавтра|сейчас|утром|днём|днем|вечером)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ClientProfile:
    """Что уже известно о клиенте из беседы и где он в сценарии."""

    debt_amount: int | None = None
    region: str | None = None
    has_property: bool | None = None
    stage: Stage = "qualify"
    invited: bool = False
    consultation_time: str | None = None
    phone: str | None = None
    user_is_angry: bool = False

    def merge(self, fresh: ClientProfile) -> ClientProfile:
        """Слить свежий разбор с уже известным состоянием сценария.

        Слоты берём из свежего, если он их назвал; состояние (этап, приглашение,
        время, агрессию) сохраняем, если новый разбор его не переопределил.
        """
        return replace(
            self,
            debt_amount=fresh.debt_amount if fresh.debt_amount is not None else self.debt_amount,
            region=fresh.region if fresh.region is not None else self.region,
            has_property=fresh.has_property if fresh.has_property is not None else self.has_property,
            stage=fresh.stage if fresh.stage != "qualify" else self.stage,
            invited=fresh.invited or self.invited,
            consultation_time=fresh.consultation_time or self.consultation_time,
            phone=fresh.phone or self.phone,
            user_is_angry=fresh.user_is_angry or self.user_is_angry,
        )

    def with_invite(self) -> ClientProfile:
        """Зафиксировать, что приглашение отправлено."""
        return replace(self, invited=True, stage="invited")

    def with_time(self, time: str | None) -> ClientProfile:
        """Зафиксировать названное клиентом время консультации."""
        if not time:
            return self
        return replace(self, consultation_time=time, stage="booked")

    def with_phone(self, phone: str | None) -> ClientProfile:
        """Зафиксировать номер телефона клиента."""
        if not phone:
            return self
        return replace(self, phone=phone, stage="booked")

    def with_anger(self) -> ClientProfile:
        """Пометить, что клиент раздражён."""
        return replace(self, user_is_angry=True)

    def is_complete(self) -> bool:
        """Слоты квалификации заполнены — можно приглашать.

        По КЦ.docx ¶60 критериев приёма два: сумма долга и регион прописки.
        Имущество (has_property) — контекст для разъяснений, но не блокер записи.
        """
        return self.debt_amount is not None and self.region is not None


def qualify(
    profile: ClientProfile,
    *,
    min_debt_rub: int,
    excluded_regions: Sequence[str],
) -> Qualification:
    """Квалификация по правилам документа: сумма долга и регион прописки."""
    if profile.debt_amount is not None and profile.debt_amount < min_debt_rub:
        return "small_debt"
    if profile.region is not None:
        region = profile.region.casefold()
        if any(word in region for word in excluded_regions if word):
            return "excluded_region"
    return "ok"


def next_question(profile: ClientProfile) -> str | None:
    """Следующий шаг сценария: чего не хватает, чтобы пригласить на консультацию.

    Если приглашение уже отправлено, повторно его не возвращаем: сценарий ждёт
    время консультации (см. scenario_reply).
    """
    if profile.stage == "booked":
        return None
    if profile.invited:
        return None
    if profile.debt_amount is None:
        return ASK_DEBT
    if profile.region is None:
        return ASK_REGION
    return None


def scenario_reply(profile: ClientProfile, qualification: Qualification) -> str:
    """Реплика сценария: отказ по квалификации, подтверждение, вопрос или приглашение.

    Состояние важнее текста: запись фиксируется один раз, приглашение не повторяется.
    """
    if qualification == "small_debt":
        return NOT_OUR_CASE_DEBT
    if qualification == "excluded_region":
        return NOT_OUR_CASE_REGION
    if profile.user_is_angry:
        return ANGRY_REPLY
    if profile.stage == "booked":
        if profile.phone:
            return BOOK_DONE.format(time="звонок по номеру " + profile.phone)
        time = profile.consultation_time or "согласованное время"
        return BOOK_DONE.format(time=time)
    if profile.invited and profile.consultation_time:
        return BOOK_CONFIRM.format(time=profile.consultation_time)
    if profile.invited and not profile.consultation_time:
        # защита: если критерии не собраны, а invited=True — это битый стейт, ведём сбор заново
        if not profile.is_complete():
            return next_question(profile) or INVITE
        # приглашение уже ушло, время не названо — просим время или телефон, не повторяем INVITE
        return (
            "Подскажите, пожалуйста, удобное время для звонка юриста "
            "или оставьте номер телефона — перезвоним и согласуем."
        )
    return next_question(profile) or INVITE


def extract_time(question: str) -> str | None:
    """Вытащить из реплики время/день консультации: «14:39», «сегодня в 14.39», «завтра».

    Время в приоритете: если назван и день, и час — возвращаем час («14:39»),
    день — запасной вариант, когда часа нет.
    """
    clock = _CLOCK.search(question)
    if clock:
        return f"{clock.group(1)}:{clock.group(2)}"
    hour = _HOUR.search(question)
    if hour:
        return f"{hour.group(1)} часов"
    day = _DAY.search(question)
    return day.group(0).strip() if day else None
