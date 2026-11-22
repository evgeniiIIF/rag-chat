"""Узел разбора реплики: слоты профиля через модель + правила по ожидаемому слоту.

Что бот спросил на прошлом ходу (`expected_slot`), то клиент и ответил: «664455» после вопроса
о телефоне это номер, после вопроса о сумме это сумма. Новое значение заменяет старое.
Мусор разбора («RUB» как регион, млрд как долг) не попадает в слоты.
"""

from __future__ import annotations

import re

from domain.graph_state import GraphState
from domain.profile import (
    ClientProfile,
    clean_debt,
    clean_region,
    extract_phone,
    extract_time,
    merge_facts,
    normalize_phone,
    parse_amount,
)
from domain.scenario import expected_slot
from graph.nodes import NodeFn, NodeResult
from infrastructure.llm import IntakeDraft, IntakeFn

# факты, дублирующие слоты профиля или служебные пометки модели: они только путают ответ
_SLOT_KEYS = re.compile(r"(?i)долг|сумм|debt|регион|прописк|region|телефон|phone|врем|запис|note|interest|ранее|ожидан")
_PURE_PHONE = re.compile(r"[\d\s\-+()]*\d[\d\s\-+()]*")
_HOUR_ONLY = re.compile(r"\d{1,2}")


def _drop_slot_facts(facts: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in facts.items() if not _SLOT_KEYS.search(str(key))}


def _apply_expected(profile: ClientProfile, question: str, draft: IntakeDraft) -> IntakeDraft:
    """Ответ на заданный вопрос разбираем кодом: модель-разборщик здесь только запасной вариант."""
    expected = expected_slot(profile)
    text = question.strip()
    update: dict[str, object] = {}
    if expected == "phone" and _PURE_PHONE.fullmatch(text):
        update = {"phone": text, "debt_amount": None, "kind": "situation"}
    elif expected == "time" and _HOUR_ONLY.fullmatch(text) and int(text) <= 23:
        update = {"consultation_time": f"{int(text):02d}:00", "kind": "situation"}
    else:
        amount = parse_amount(text)
        region = clean_region(text)
        if amount is not None:
            update = {"debt_amount": amount, "kind": "situation"}
        elif expected == "region" and draft.region is None and region is not None:
            update = {"region": region, "kind": "situation"}
    return draft.model_copy(update=update) if update else draft


def _merge_phone(
    profile: ClientProfile, question: str, draft: IntakeDraft, *, awaiting: bool
) -> tuple[str | None, str | None]:
    """Телефон: полный номер заменяет старый, неполный запоминается отдельно как phone_raw."""
    phone, raw = profile.phone, profile.phone_raw
    if draft.phone:
        valid = normalize_phone(draft.phone)
        if valid:
            phone, raw = valid, None
        else:
            raw = draft.phone.strip()
    found = extract_phone(question, allow_bare_short=awaiting)
    if found:
        phone, raw = found, None
    return phone, raw


def _merge(profile: ClientProfile, question: str, draft: IntakeDraft) -> ClientProfile:
    # мусорный разбор («3.5 млрд», «RUB» вместо региона) не затирает уже известное значение
    debt = (clean_debt(draft.debt_amount) if draft.debt_amount is not None else None) or profile.debt_amount
    region = (clean_region(draft.region) if draft.region is not None else None) or profile.region
    phone, phone_raw = _merge_phone(profile, question, draft, awaiting=expected_slot(profile) == "phone")
    time_slot = draft.consultation_time or extract_time(question) or profile.consultation_time
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
        draft = _apply_expected(state.profile, state.question, intake(state.question, state.messages[:-1]))
        return {"profile": _merge(state.profile, state.question, draft), "kind": draft.kind}

    return extract
