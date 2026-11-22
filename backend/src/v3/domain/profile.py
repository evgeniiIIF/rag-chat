"""Профиль клиента и правила фильтров.

Только данные и чистые функции: решения о шаге — в `domain/scenario.py`, формулировки — в модели.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

MIN_DEBT_RUB: int = 350_000
# больше 100 млн — не долг физлица, а склейка цифр или ошибка разбора
MAX_DEBT_RUB: int = 100_000_000
REGION_MAX_LENGTH: int = 64

# регионы, с которыми компания не работает (КЦ ¶60)
EXCLUDED_REGIONS: tuple[str, ...] = ("чечня", "чеченская", "днр", "лнр", "владимирская")

_REGION_OK = re.compile(r"^[а-яё][а-яё\s\-.]*$", re.IGNORECASE)
_PHONE = re.compile(
    r"(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}"
    r"|\d{10,11}"
    r"|\d{2}[\s\-]\d{2}[\s\-]\d{2,4}(?:[\s\-]\d{2,4})?"
)
_CLOCK = re.compile(r"\b(\d{1,2})[:.](\d{2})\b")
_HOUR = re.compile(r"\b(\d{1,2})\s*(?:час|часа|часов)\b", re.IGNORECASE)
_DAY = re.compile(r"\b(сегодня|завтра|послезавтра|сейчас|утром|днём|днем|вечером)\b", re.IGNORECASE)


class ClientProfile(BaseModel):
    """Слоты разговора. Любое поле можно изменить на любом шаге.

    debt_amount и region — обязательные фильтры; phone и consultation_time нужны для записи.
    facts — контекст клиента из реплик (какие долги, имущество), фильтры не затрагивает.
    """

    debt_amount: int | None = None
    region: str | None = None
    phone: str | None = None
    consultation_time: str | None = None
    facts: dict[str, str] = Field(default_factory=dict)

    def missing_filter(self) -> str | None:
        """Какого обязательного слота не хватает: debt | region | None."""
        if self.debt_amount is None:
            return "debt"
        if self.region is None:
            return "region"
        return None

    def failed_filter(self) -> str | None:
        """Какой известный фильтр уже не проходит: debt | region | None.

        Проверяется раньше нехватки данных: если сумма меньше 350к, спрашивать регион уже незачем.
        """
        if self.debt_amount is not None and not qualifies_by_debt(self.debt_amount):
            return "debt"
        if self.region is not None and is_excluded_region(self.region):
            return "region"
        return None

    def filters_ok(self) -> bool:
        """Сумма от 350к и регион не в списке исключённых."""
        return qualifies_by_debt(self.debt_amount) and self.region is not None and not is_excluded_region(self.region)


def qualifies_by_debt(debt: int | None) -> bool:
    return debt is not None and debt >= MIN_DEBT_RUB


def is_excluded_region(region: str) -> bool:
    low = region.casefold()
    return any(word in low for word in EXCLUDED_REGIONS)


def clean_debt(value: int | None) -> int | None:
    """Сумма в разумных пределах: 0 < сумма ≤ 100 млн, иначе мусор разбора."""
    if value is None or value <= 0 or value > MAX_DEBT_RUB:
        return None
    return value


def clean_region(value: str | None) -> str | None:
    """Регион — только кириллица: латиница и цифры это мусор разбора («RUB»)."""
    if not value:
        return None
    flat = " ".join(value.split()).strip(" .,;:")
    if len(flat) < 3 or len(flat) > REGION_MAX_LENGTH or not _REGION_OK.match(flat):
        return None
    return flat


def filter_state_text(profile: ClientProfile) -> str:
    """Состояние фильтров для промпта."""
    if profile.debt_amount is None:
        debt = "не указан"
    elif qualifies_by_debt(profile.debt_amount):
        debt = f"{profile.debt_amount} ₽ (подходит)"
    else:
        debt = f"{profile.debt_amount} ₽ (меньше 350 000 ₽)"
    if profile.region is None:
        region = "не указан"
    elif is_excluded_region(profile.region):
        region = f"{profile.region} (не обслуживается)"
    else:
        region = f"{profile.region} (подходит)"
    return f"долг: {debt}; регион: {region}; фильтры: {'пройдены' if profile.filters_ok() else 'не пройдены'}"


def profile_text(profile: ClientProfile) -> str:
    """Что известно о клиенте, для промпта."""
    parts: list[str] = []
    if profile.debt_amount is not None:
        parts.append(f"сумма долга: {profile.debt_amount} ₽")
    if profile.region:
        parts.append(f"регион: {profile.region}")
    if profile.phone:
        parts.append(f"телефон: {profile.phone}")
    if profile.consultation_time:
        parts.append(f"удобное время: {profile.consultation_time}")
    if profile.facts:
        parts.append("; ".join(f"{key}: {value}" for key, value in profile.facts.items()))
    return "; ".join(parts) if parts else "(пока ничего)"


def extract_phone(text: str) -> str | None:
    match = _PHONE.search(text)
    return match.group(0).strip() if match else None


def extract_time(text: str) -> str | None:
    """Fallback разбора времени: «14:39», «в 15 часов», «завтра вечером»."""
    clock = _CLOCK.search(text)
    if clock:
        return f"{clock.group(1)}:{clock.group(2)}"
    hour = _HOUR.search(text)
    if hour:
        return f"{hour.group(1)} часов"
    day = _DAY.search(text)
    return day.group(0).strip() if day else None
