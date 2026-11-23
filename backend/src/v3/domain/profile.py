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
# факты в промпте — только свежие и без повторов: иначе профиль пухнет и подсказывает модели домыслы
MAX_FACTS: int = 5
# значения-заглушки модели: «неизвестно» ничего не сообщает клиенту
_EMPTY_FACTS = frozenset(
    {
        "",
        "нет",
        "неизвестно",
        "не известно",
        "нет данных",
        "не указано",
        "не указан",
        "не уточнено",
        "н/д",
        "none",
        "null",
    }
)

# регионы, с которыми компания не работает (КЦ ¶60); основы слов, чтобы ловить любые падежи
EXCLUDED_REGIONS: tuple[str, ...] = ("чечн", "чечен", "днр", "лнр", "владимир", "донецк", "луганск")

_REGION_OK = re.compile(r"^[а-яё][а-яё\s\-.]*$", re.IGNORECASE)
_PHONE = re.compile(
    r"(?<!\d)(?:\+7|8|7)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}(?!\d)"
    r"|(?<!\d)\(?[3489]\d{2}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}(?!\d)"
)
_CLOCK = re.compile(r"\b(\d{1,2})[:.](\d{2})\b")
_HOUR = re.compile(r"\b(\d{1,2})\s*(?:час|часа|часов)\b", re.IGNORECASE)
_AT_HOUR = re.compile(r"(?<!\w)в\s+(\d{1,2})(?:[:.](\d{2}))?(?!\d)(?!\s*(?:тыс|руб|млн|%|лет))", re.IGNORECASE)
_DAY = re.compile(r"\b(сегодня|завтра|послезавтра|сейчас|утром|днём|днем|вечером)\b", re.IGNORECASE)


class ClientProfile(BaseModel):
    """Слоты разговора. Любое поле можно изменить на любом шаге.

    debt_amount и region — обязательные фильтры; phone и consultation_time нужны для записи.
    phone_raw — номер, который клиент назвал, но он неполный: шаг остаётся invite.
    facts — контекст клиента из реплик (какие долги, имущество), фильтры не затрагивает.
    """

    debt_amount: int | None = None
    region: str | None = None
    phone: str | None = None
    phone_raw: str | None = None
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


# одно и то же под разными именами: модель то «цель», то «goal»
_FACT_ALIASES: dict[str, str] = {
    "goal": "цель",
    "задача": "цель",
    "проблема": "цель",
    "запрос": "цель",
    "current_obligations": "обязательства",
    "обязательства": "обязательства",
    "enforcement_proceeding": "исполнительное производство",
    "enforcement_proceedings": "исполнительное производство",
    "исполнительное производство": "исполнительное производство",
}


def _stems(text: str) -> set[str]:
    """Грубые основы слов: «рассрочка/рассрочкой» — одно и то же."""
    return {word[:5] for word in re.findall(r"\w+", text.casefold()) if len(word) > 3}


def _same_fact(one: str, other: str) -> bool:
    """Один и тот же факт разными словами: больше половины основ совпало."""
    left, right = _stems(one), _stems(other)
    return bool(left and right) and len(left & right) / len(left | right) >= 0.5


def merge_facts(old: dict[str, str], new: dict[str, str]) -> dict[str, str]:
    """Слить факты о клиенте: свежие значения заменяют старые, повторы по смыслу и заглушки уходят."""
    merged = {str(key).strip(): str(value).strip() for key, value in old.items()}
    for key, value in new.items():
        clean_key = _FACT_ALIASES.get(str(key).strip().casefold(), str(key).strip())
        clean_value = str(value).strip()
        if not clean_key or clean_value.lower().strip(".") in _EMPTY_FACTS:
            continue
        # тот же факт под другим именем (долг/debts, цель/goal): старое имя уходит, значение свежее;
        # зеркальная запись («просрочка: не может платить» после «не справляется: просрочка») тоже уходит
        for stale in [
            k
            for k, v in merged.items()
            if k != clean_key and (_same_fact(v, clean_value) or _same_fact(k, clean_value) or _same_fact(v, clean_key))
        ]:
            merged.pop(stale)
        merged[clean_key] = clean_value
    return dict(list(merged.items())[-MAX_FACTS:])


def normalize_phone(raw: str) -> str | None:
    """Номер: 10 → +7XXXXXXXXXX, 11 (7 или 8 в начале) → +7XXXXXXXXXX.

    Меньше десяти цифр — номер неполный, None: по шести цифрам перезвонить нельзя.
    """
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits[0] in "78":
        return "+7" + digits[1:]
    if len(digits) == 10:
        return "+7" + digits
    if len(digits) == 6:
        return f"{digits[:2]}-{digits[2:4]}-{digits[4:]}"
    return None


def extract_phone(text: str) -> str | None:
    """Первый полный номер из текста: 11 или 10 цифр."""
    for match in _PHONE.finditer(text):
        phone = normalize_phone(match.group(0))
        if phone:
            return phone
    return None


_TIME_WORD = re.compile(r"(?i)^\s*(?:в\s+)?(\d{1,2})(?:[:.](\d{2}))?\s*(утра|дня|вечера|ночи)?\s*$")


def normalize_time(value: str | None) -> str | None:
    """Время из модели: «10», «10.00», «10 утра», «10 вечера» → «10:00»/«22:00».

    Остальное (с днём недели) оставляем как есть.
    """
    if not value:
        return value
    flat = value.strip()
    match = _TIME_WORD.match(flat)
    if not match:
        return flat
    hour = int(match.group(1))
    minutes = match.group(2) or "00"
    part = (match.group(3) or "").lower()
    if (part in {"вечера", "ночи"} and hour < 12) or (part == "дня" and hour < 10):
        hour += 12
    if hour > 23:
        return flat
    return f"{hour:02d}:{minutes}"


def extract_time(text: str) -> str | None:
    """Fallback разбора времени: «14:39», «в 15 часов», «завтра в 12» → «завтра 12:00»."""
    day_match = _DAY.search(text)
    day = day_match.group(0).strip() if day_match else None
    clock = _CLOCK.search(text)
    hour = _HOUR.search(text)
    at_hour = _AT_HOUR.search(text)
    slot: str | None = None
    if clock and int(clock.group(1)) <= 23 and int(clock.group(2)) <= 59:
        slot = f"{int(clock.group(1)):02d}:{clock.group(2)}"
    elif hour:
        slot = f"{hour.group(1)} часов"
    elif at_hour and int(at_hour.group(1)) <= 23:
        slot = f"{int(at_hour.group(1)):02d}:{at_hour.group(2) or '00'}"
    if day and slot:
        return f"{day} {slot}"
    return slot or day


_AMOUNT_ONLY = re.compile(
    r"^\s*(?:около\s+|примерно\s+)?(\d{1,3}(?:\s\d{3})+|\d+)([.,]\d+)?\s*"
    r"(тыс\w*|т\.?\s?р\.?|к|k|млн\w*|миллион\w*|руб\w*|р\.?|₽)?\.?\s*$",
    re.IGNORECASE,
)


_AMOUNT_WITH_UNIT = re.compile(
    r"(?i)(\d{1,3}(?:\s\d{3})+|\d+)([.,]\d+)?\s*(тыс\w*|т\.?\s?р\.?|к\b|k\b|млн\w*|миллион\w*|руб\w*|р\.|₽)"
)


def amount_in_text(text: str) -> int | None:
    """Сумма внутри фразы: «рассрочку на 310к платить не могу» — клиент назвал цифру, хотя слов много."""
    match = _AMOUNT_WITH_UNIT.search(text)
    if not match:
        return None
    number = float(re.sub(r"\s", "", match.group(1)) + (match.group(2) or "").replace(",", "."))
    unit = match.group(3).lower()
    if unit.startswith(("млн", "милл")):
        number *= 1_000_000
    elif unit.startswith(("тыс", "т", "к", "k", "руб", "р", "₽")):
        number *= 1_000 if not unit.startswith(("руб", "р", "₽")) or number < 1_000 else 1
    if number < 1_000:
        return None
    return clean_debt(round(number))


def parse_amount(text: str) -> int | None:
    """Сумма из реплики, состоящей только из суммы: «323 тыс», «1,5 млн», «500к», «323 000 рублей».

    Телефон («66 44 55») и час («12») суммой не считаются.
    """
    match = _AMOUNT_ONLY.match(text)
    if not match:
        return None
    number = float(re.sub(r"\s", "", match.group(1)) + (match.group(2) or "").replace(",", "."))
    unit = (match.group(3) or "").lower()
    if unit.startswith(("тыс", "т", "к", "k")):
        number *= 1_000
    elif unit.startswith(("млн", "милл")):
        number *= 1_000_000
    if number < 1_000:
        return None
    return clean_debt(round(number))
