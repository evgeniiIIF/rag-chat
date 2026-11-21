"""Профиль клиента и сценарий консультации (документ ¶59-¶60).

Сценарий — правило, а не модель: сначала выясняем сумму долга, потом регион прописки,
потом имущество. Как только ситуация квалифицирована — зовём на бесплатную консультацию.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from core.behavior import (
    ASK_DEBT,
    ASK_PROPERTY,
    ASK_REGION,
    INVITE,
    NOT_OUR_CASE_DEBT,
    NOT_OUR_CASE_REGION,
)

type Qualification = Literal["ok", "small_debt", "excluded_region"]


@dataclass(frozen=True)
class ClientProfile:
    """Что уже известно о клиенте из беседы."""

    debt_amount: int | None = None
    region: str | None = None
    has_property: bool | None = None


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
    """Следующий шаг сценария: чего не хватает, чтобы пригласить на консультацию."""
    if profile.debt_amount is None:
        return ASK_DEBT
    if profile.region is None:
        return ASK_REGION
    if profile.has_property is None:
        return ASK_PROPERTY
    return None


def scenario_reply(profile: ClientProfile, qualification: Qualification) -> str:
    """Реплика сценария: отказ по квалификации, следующий вопрос или приглашение."""
    if qualification == "small_debt":
        return NOT_OUR_CASE_DEBT
    if qualification == "excluded_region":
        return NOT_OUR_CASE_REGION
    return next_question(profile) or INVITE
