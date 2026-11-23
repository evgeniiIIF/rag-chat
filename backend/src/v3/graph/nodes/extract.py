"""Узел разбора реплики: слоты профиля через модель + правила по ожидаемому слоту.

Что бот спросил на прошлом ходу (`expected_slot`), то клиент и ответил: «664455» после вопроса
о телефоне это номер, после вопроса о сумме это сумма. Новое значение заменяет старое.
Мусор разбора («RUB» как регион, млрд как долг) не попадает в слоты.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from langchain_core.messages import BaseMessage

from domain.graph_state import GraphState
from domain.profile import (
    ClientProfile,
    amount_in_text,
    clean_debt,
    clean_region,
    extract_phone,
    extract_time,
    merge_facts,
    normalize_phone,
    normalize_time,
    parse_amount,
)
from domain.scenario import expected_slot
from graph.nodes import NodeFn, NodeResult
from infrastructure.llm import IntakeDraft, IntakeFn

# факты, дублирующие слоты профиля или служебные пометки модели: они только путают ответ
# без «?» и без вопросительного слова реплика — просьба или рассказ, а не вопрос
_QUESTION_WORD = re.compile(
    r"(?i)\b(?:как|что|сколько|где|когда|почему|зачем|какой|какая|какие|каков|можно|нужно|стоит|есть)\s*(?:ли)?\b"
)
_SLOT_KEYS = re.compile(r"(?i)долг|сумм|debt|регион|прописк|region|телефон|phone|врем|запис|note|interest|ранее|ожидан")
# сумма рядом со словом «долг/сумма» — это и есть общий долг; «рассрочка на 310к» — нет
_DEBT_AROUND = re.compile(
    r"(?i)(?:долг\w*|задолженност\w*|сумм\w*)[^\d.!?]{0,15}\d"
    r"|\d[^\d.!?]{0,15}(?:долг\w*|задолженност\w*|сумм\w*)"
)
# сумма внутри фразы: «рассрочку на 310к платить не могу» — клиент назвал цифру
_AMOUNT_IN_TEXT = re.compile(r"(?i)(?:\d{1,3}(?:\s\d{3})+|\d+)\s*(?:тыс\w*|к\b|k\b|млн\w*|миллион\w*|руб\w*|р\.|₽)")
_PURE_PHONE = re.compile(r"[\d\s\-+()]*\d[\d\s\-+()]*")
_HOUR_ONLY = re.compile(r"\d{1,2}")
# регион — короткое название, а не фраза-просьба: «консультацию давай» регионом не становится
_REGION_WORD = re.compile(r"^[а-яё][а-яё\s\-.]*$", re.IGNORECASE)
_REGION_STOP = re.compile(
    r"(?i)давай|дайте|хочу|можно|надо|нужно|подскаж|скаж|спас|привет|здравств"
    r"|консультац|банкрот|долг|сумм|телефон|время|запис"
)
# слова-обёртки вокруг названия региона: «я прописан в Дагестане» → «Дагестане»
_REGION_NOISE = re.compile(
    r"(?i)\b(?:я|мы|вы|в|во|на|из|регион|регионе|город|городе|прописан\w*|проживаю|живу|это|там)\b"
)


def _region_from_text(text: str) -> str:
    """Регион из реплики клиента: только когда он назвал именно регион, а не попросил консультацию."""
    flat = " ".join(text.split()).strip(" .,;:!?")
    if not flat or _REGION_STOP.search(flat):
        return ""
    words = [word for word in _REGION_NOISE.sub(" ", flat).split() if len(word) > 2]
    return " ".join(words) if 0 < len(words) <= 3 else ""


def _drop_slot_facts(facts: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in facts.items() if not _SLOT_KEYS.search(str(key))}


def _expected_from_history(history: Sequence[BaseMessage], profile: ClientProfile) -> str | None:
    """Что бот спросил в прошлой реплике — по последнему ai-сообщению, а не по next_step.

    Баг: expected_slot(profile) пересчитывался от профиля, и при kind=question
    («310к» после вопроса о сумме) возвращал None — ответ клиента терялся.
    """
    for message in reversed(list(history)):
        if message.type != "ai":
            continue
        text = str(message.content).casefold()
        if "телефон" in text or ("время" in text and "звонк" in text):
            return "phone" if profile.phone is None else "time"
        if "регион" in text or "прописан" in text or "город" in text:
            return "region"
        if "сумм" in text or "долг" in text:
            return "debt"
        break
    return expected_slot(profile)


def _apply_expected(
    profile: ClientProfile,
    question: str,
    draft: IntakeDraft,
    history: Sequence[BaseMessage] = (),
    expected: str | None = None,
) -> IntakeDraft:
    """Ответ на заданный вопрос разбираем кодом: модель-разборщик здесь только запасной вариант."""
    if draft.kind == "question":  # числа из вопроса («а если долг 500 тысяч?») в слоты не пишем
        return draft
    if expected is None:
        expected = _expected_from_history(history, profile)
    text = question.strip()
    update: dict[str, object] = {}
    if expected == "phone" and _PURE_PHONE.fullmatch(text):
        update = {"phone": text, "debt_amount": None, "kind": "situation"}
    elif expected == "time" and _HOUR_ONLY.fullmatch(text) and int(text) <= 23:
        update = {"consultation_time": f"{int(text):02d}:00", "kind": "situation"}
    else:
        amount = parse_amount(text)
        if amount is None and expected == "debt":  # бот спросил сумму — берём цифру из фразы
            amount = amount_in_text(text)
        region = clean_region(_region_from_text(text))
        if amount is not None:
            update = {"debt_amount": amount, "kind": "situation"}
        elif expected == "region" and draft.region is None and profile.region is None and region is not None:
            # регион из сырого текста берём, только когда бот его и спросил: иначе «просрочки»
            # затирают уже известный регион, фильтр перестаёт срабатывать и бот зовёт на консультацию
            update = {"region": region, "kind": "situation"}
    return draft.model_copy(update=update) if update else draft


def _debt_is_total(question: str, expected: str | None) -> bool:
    """Сумма становится общим долгом, только если клиент так её и назвал.

    «Рассрочку на 310к платить не могу» — обстоятельство, а не долг: иначе бот ошибочно
    отказывает по сумме, которой клиент ещё не называл.
    """
    text = " ".join(question.split())
    return (
        parse_amount(text) is not None
        or _DEBT_AROUND.search(text) is not None
        or (expected == "debt" and _AMOUNT_IN_TEXT.search(text) is not None)
        or (expected == "debt" and len(text.split()) <= 4)
    )


def _merge_phone(profile: ClientProfile, question: str, draft: IntakeDraft) -> tuple[str | None, str | None]:
    """Телефон: полный номер заменяет старый, неполный запоминается отдельно как phone_raw."""
    phone, raw = profile.phone, profile.phone_raw
    if draft.phone:
        valid = normalize_phone(draft.phone)
        if valid:
            phone, raw = valid, None
        else:
            raw = draft.phone.strip()
    found = extract_phone(question)
    if found:
        phone, raw = found, None
    return phone, raw


def _merge(profile: ClientProfile, question: str, draft: IntakeDraft) -> ClientProfile:
    # мусорный разбор («3.5 млрд», «RUB» вместо региона) не затирает уже известное значение
    debt = (clean_debt(draft.debt_amount) if draft.debt_amount is not None else None) or profile.debt_amount
    region = (clean_region(draft.region) if draft.region is not None else None) or profile.region
    phone, phone_raw = _merge_phone(profile, question, draft)
    time_slot = normalize_time(draft.consultation_time or extract_time(question)) or profile.consultation_time
    facts = merge_facts(_drop_slot_facts(profile.facts), _drop_slot_facts(draft.facts))
    return profile.model_copy(
        update={
            "debt_amount": debt,
            "region": region,
            "phone": phone,
            "phone_raw": phone_raw,
            "consultation_time": time_slot,
            "facts": facts,
        }
    )


def make_extract_node(intake: IntakeFn) -> NodeFn:
    def extract(state: GraphState) -> NodeResult:
        draft = intake(state.question, state.messages[:-1])
        if draft.kind == "question" and "?" not in state.question and not _QUESTION_WORD.search(state.question):
            draft = draft.model_copy(update={"kind": "situation"})
        expected = _expected_from_history(state.messages[:-1], state.profile)
        draft = _apply_expected(state.profile, state.question, draft, expected=expected)
        if not _debt_is_total(state.question, expected):
            draft = draft.model_copy(update={"debt_amount": None})
        return {"profile": _merge(state.profile, state.question, draft), "kind": draft.kind}

    return extract
