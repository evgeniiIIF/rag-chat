"""Узел разбора реплики: слоты профиля через модель + regex для телефона и времени.

Новое значение заменяет старое: клиент может менять данные на любом шаге.
Мусор разбора («RUB» как регион, млрд как долг) отбрасывается, старое значение остаётся.
"""

from __future__ import annotations

from domain.graph_state import GraphState
from domain.profile import (
    ClientProfile,
    clean_debt,
    clean_region,
    extract_phone,
    extract_time,
)
from graph.nodes import NodeFn, NodeResult
from infrastructure.llm import IntakeDraft, IntakeFn


def _merge(profile: ClientProfile, question: str, draft: IntakeDraft) -> ClientProfile:
    # мусорный разбор («3.5 млрд», «RUB» вместо региона) не затирает уже известное значение
    debt = (clean_debt(draft.debt_amount) if draft.debt_amount is not None else None) or profile.debt_amount
    region = (clean_region(draft.region) if draft.region is not None else None) or profile.region
    phone = draft.phone or extract_phone(question) or profile.phone
    time_slot = draft.consultation_time or extract_time(question) or profile.consultation_time
    facts = {**profile.facts, **{str(key): str(value) for key, value in draft.facts.items()}}
    return profile.model_copy(
        update={
            "debt_amount": debt,
            "region": region,
            "phone": phone,
            "consultation_time": time_slot,
            "facts": facts,
        }
    )


def make_extract_node(intake: IntakeFn) -> NodeFn:
    def extract(state: GraphState) -> NodeResult:
        draft = intake(state.question, state.messages[:-1])
        return {"profile": _merge(state.profile, state.question, draft), "kind": draft.kind}

    return extract
