"""Узел разбора реплики: вопрос по правилам, ситуация клиента или мета-реплика сценария.

Состояние сценария живёт в профиле и переживает ходы: агрессия не идёт в поиск,
запись фиксирует время, приглашение не повторяется. Решение «документ или сценарий»
принимает этот узел, маршрут — `graph/build.py`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from core.behavior import ASK_REGION, NOT_OUR_CASE_DEBT, NOT_OUR_CASE_REGION
from domain.graph_state import GraphState
from domain.models import Answer
from dataclasses import replace

from core.behavior import ASK_DEBT
from domain.profile import ClientProfile, extract_time, next_question, qualify, scenario_reply
from domain.social import Intent, detect
from graph.nodes import NodeFn, NodeResult
from infrastructure.llm import IntakeDraft, IntakeFn

_YES = re.compile(r"(да|ага|угу|конечно|запишите|записывай|запиши|давайте|давай|хорошо|ок|ok|окей)", re.IGNORECASE)
_PHONE = re.compile(r"(?:\+7|8)?[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}")


def _is_yes(text: str) -> bool:
    return bool(_YES.search(text))


def _is_phone(text: str) -> bool:
    return bool(_PHONE.search(text))


def _extract_phone(text: str) -> str | None:
    match = _PHONE.search(text)
    return match.group(0) if match else None


_CONSULT = re.compile(r"(консультац|юрист|запиш|запис|перезвон|звонок|созвон)\w*", re.IGNORECASE)


def _wants_consultation(text: str) -> bool:
    return bool(_CONSULT.search(text))


def _is_answer_to_scenario(messages: Sequence[object]) -> bool:
    """Последняя реплика ассистента — вопрос сценария (ASK_DEBT/ASK_REGION)."""
    last_ai = next(
        (msg for msg in reversed(list(messages)) if getattr(msg, "type", "") == "ai"),
        None,
    )
    if last_ai is None:
        return False
    text = str(getattr(last_ai, "content", ""))
    return ASK_DEBT in text or ASK_REGION in text


def make_intake_node(
    intake: IntakeFn,
    *,
    min_debt_rub: int,
    excluded_regions: Sequence[str],
) -> NodeFn:
    """Понимает реплику, сливает с прошлым профилем и решает: документ или сценарий."""

    def node(state: GraphState) -> NodeResult:
        previous = state.get("profile") or ClientProfile()
        question = state["question"]

        # 1. агрессия: не зовём модель, помечаем профиль и ведём в сценарий
        if detect(question) is Intent.RUDE:
            profile = previous.with_anger()
            text = scenario_reply(profile, "ok")
            return {
                "profile": profile,
                "next_step": "ask",
                "answer": Answer(answer=text, grounded=False),
            }

        # 2. запись уже идёт: клиент мог назвать время, телефон или просто согласиться
        if previous.stage in ("invited", "booked"):
            time = extract_time(question)
            if time:
                profile = previous.with_time(time)
            elif _is_phone(question):
                # телефон — отдельный слот, stage=booked, BOOK_DONE со звонком по номеру
                profile = previous.with_phone(_extract_phone(question))
            elif previous.stage == "invited" and _is_yes(question):
                # «да, запишите» без времени/телефона — просим время или телефон, не повторяем INVITE
                profile = previous
            else:
                profile = previous
            text = scenario_reply(profile, "ok")
            return {
                "profile": profile,
                "next_step": "ask",
                "answer": Answer(answer=text, grounded=False),
            }

        # 3. обычный ход: разбор реплики, слияние с прошлым профилем
        draft = intake(question, state.get("messages", [])[:-1])
        # клиент только что ответил на вопрос сценария, но LLM вернул kind=question
        # (частый случай для коротких «800», «ставрополь»): принудительно ведём сценарий
        if draft.kind == "question" and _is_answer_to_scenario(state.get("messages", [])):
            draft = IntakeDraft(
                kind="situation",
                debt_amount=draft.debt_amount,
                region=draft.region,
                has_property=draft.has_property,
                wants_consultation=True,
            )
        # клиент просит консультацию/юриста — по LLM (draft.wants_consultation) или по regex
        if draft.wants_consultation or _wants_consultation(question):
            draft = IntakeDraft(
                kind="situation",
                debt_amount=draft.debt_amount,
                region=draft.region,
                has_property=draft.has_property,
                wants_consultation=True,
            )
        profile = previous.merge(draft.profile())
        qualification = qualify(profile, min_debt_rub=min_debt_rub, excluded_regions=excluded_regions)
        result: NodeResult = {"profile": profile, "next_step": "retrieve"}

        # 3a. нецелевой клиент: отказ по сумме или региону
        if qualification != "ok":
            text = NOT_OUR_CASE_DEBT if qualification == "small_debt" else NOT_OUR_CASE_REGION
            return {**result, "next_step": "ask", "answer": Answer(answer=text, grounded=False)}

        # 3b. клиент рассказал о ситуации (или задал общий вопрос): ведём сценарий
        if draft.kind == "situation":
            # защита: если хочет консультацию, но критерии не собраны — сначала собираем
            if draft.wants_consultation and not profile.is_complete():
                # снимаем ошибочный invited, если он есть, и ведём сбор заново
                if profile.invited:
                    profile = replace(profile, invited=False, stage="qualify")
                text = next_question(profile) or ASK_DEBT
                return {**result, "profile": profile, "next_step": "ask", "answer": Answer(answer=text, grounded=False)}
            text = scenario_reply(profile, qualification)
            # приглашение уходит один раз: если все слоты собраны — фиксируем факт
            if (
                profile.is_complete()
                and not profile.invited
                and text == scenario_reply(profile.with_invite(), qualification)
            ):
                profile = profile.with_invite()
            return {**result, "profile": profile, "next_step": "ask", "answer": Answer(answer=text, grounded=False)}

        return result

    return node
