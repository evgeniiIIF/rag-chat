# Узел extract: слоты профиля. Долг, телефон, время — regex; регион и kind — LLM (IntakeDraft).
# Фильтры (сумма долга от 350к, регион) пересчитываются на каждом ходу: клиент мог вспомнить долг или переехать.

from __future__ import annotations

import re

from domain.graph_state import GraphState
from domain.profile import ClientProfile, extract_time, is_excluded_region, qualifies_by_debt
from domain.social import Intent, detect
from graph.nodes import NodeFn, NodeResult
from infrastructure.llm import IntakeFn

_PHONE = re.compile(
    r"(?:\+7|8)?[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}"
    r"|\d{10,11}"
    r"|\d{2}[\s\-]\d{2}[\s\-]\d{2,4}(?:[\s\-]\d{2,4})?"
)
_DEBT = re.compile(r"(\d[\d\s]{2,})(?:\s*(?:к|тыс|тысяч|млн|миллион|руб|₽))?", re.IGNORECASE)
_MONEY = re.compile(r"\d\s*(?:к\b|тыс|млн|миллион|руб|₽)", re.IGNORECASE)
_ADD = re.compile(r"\b(ещё|еще|плюс|кроме|помимо|вдобавок)\b", re.IGNORECASE)
_YEAR = re.compile(r"\b(?:19|20)\d{2}\s*(?:г\b|год)", re.IGNORECASE)
_YES = re.compile(
    r"\b(да|ага|угу|конечно|готов|готова|жду|согласен|согласна|запишите|записывай|хорошо|ок|ok|окей)\b",
    re.IGNORECASE,
)
_CONSULT = re.compile(r"\b(консультац|юрист|запиш|запис|перезвон|звонок|созвон)\w*", re.IGNORECASE)


def _phone(text: str) -> str | None:
    match = _PHONE.search(text)
    return match.group(0).strip() if match else None


def _is_yes(text: str) -> bool:
    return bool(_YES.search(text))


def _wants(text: str) -> bool:
    return bool(_CONSULT.search(text))


def _parse_debt(text: str) -> int | None:
    # «310к» -> 310000, «800» -> 800000, «1,5 млн» -> 1500000
    match = _DEBT.search(text)
    if not match:
        return None
    raw = match.group(0).lower().replace(" ", "").replace(",", ".")
    number = re.search(r"\d+(?:\.\d+)?", raw)
    if number is None:
        return None
    try:
        value = float(number.group(0))
    except ValueError:
        return None
    if "млн" in raw or "миллион" in raw:
        return int(value * 1_000_000)
    if "к" in raw or "тыс" in raw:
        return int(value * 1000)
    return int(value) if value >= 10_000 else int(value * 1000)


def _expecting_debt(profile: ClientProfile) -> bool:
    # сумма ещё не названа или меньше порога: ждём от клиента сумму
    return profile.debt_amount is None or not qualifies_by_debt(profile.debt_amount)


def _expecting_region(profile: ClientProfile) -> bool:
    return not _expecting_debt(profile) and (profile.region is None or is_excluded_region(profile.region))


def _is_amount_reply(text: str, profile: ClientProfile) -> bool:
    # реплика — сумма долга: денежная фраза либо число, пока мы ждём сумму
    if _YEAR.search(text):
        return False
    if _MONEY.search(text):
        return True
    return _expecting_debt(profile) and len(re.sub(r"\D", "", text)) >= 3


def _filters_failed(profile: ClientProfile) -> bool:
    debt_small = (
        profile.debt_amount is not None
        and not qualifies_by_debt(profile.debt_amount)
        and "debt_checked" in profile.facts
    )
    region_bad = profile.region is not None and is_excluded_region(profile.region)
    return debt_small or region_bad


def make_extract_node(intake: IntakeFn) -> NodeFn:
    def node(state: GraphState) -> NodeResult:
        prev = state.profile.model_copy(update={"user_is_angry": False})
        text = state.question
        if detect(text) is Intent.RUDE:
            return {"profile": prev.with_anger(), "kind": "situation"}

        profile = prev
        phone = _phone(text)
        if phone:
            profile = profile.with_phone(phone)
        time_slot = extract_time(text)
        if time_slot:
            profile = profile.with_time(time_slot)

        # запись идёт: фильтры пройдены, клиент приглашён
        if profile.invited or profile.stage == "booked":
            if not profile.ready_to_wait and (_is_yes(text) or (profile.phone and profile.consultation_time)):
                profile = profile.with_ready()
            return {"profile": profile, "kind": "situation"}

        draft = intake(text, state.messages[:-1] if state.messages else [])

        answered = False
        if not phone and _is_amount_reply(text, profile):
            amount = _parse_debt(text)
            if amount:
                adds = profile.debt_amount is not None and bool(_ADD.search(text))
                total = (profile.debt_amount or 0) + amount if adds else amount
                profile = profile.with_debt(total)
                answered = True
        if not answered and not phone and draft.kind == "situation" and _expecting_debt(profile) and draft.debt_amount:
            profile = profile.with_debt(draft.debt_amount)
            answered = True
        if draft.region and (profile.region is None or _expecting_region(profile)):
            profile = profile.model_copy(update={"region": draft.region})
            answered = True

        wants = bool(_wants(text) or phone or time_slot)
        profile = profile.model_copy(
            update={"disqualified": _filters_failed(profile), "wants_consultation": wants}
        )
        kind = "situation" if (answered or wants) else draft.kind
        return {"profile": profile, "kind": kind}

    return node
