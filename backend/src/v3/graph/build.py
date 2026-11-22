"""Сборка графа (LangGraph): state(BaseModel) → узлы → условные рёбра.

Поток:
  START → gate (фиктивный: social vs extract)
  gate ─social─→ social → END
  gate ─extract─→ extract
  extract → route (условное ребро, возвращает step)
    ├─ angry        → respond_angry       → END
    ├─ not_debt     → respond_not_debt    → END
    ├─ not_region   → respond_not_region  → END
    ├─ ask_debt     → respond_ask_debt    → END
    ├─ ask_region   → respond_ask_region  → END
    ├─ invite       → respond_invite      → END
    ├─ ask_phone    → respond_ask_phone   → END
    ├─ ask_time     → respond_ask_time    → END
    ├─ ask_ready    → respond_ask_ready   → END
    ├─ book_done    → respond_book_done   → END
    └─ rag          → condense → retrieve → grade → generate | refuse → END
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from domain.graph_state import GraphState
from domain.profile import qualifies_by_debt, is_excluded_region
from domain.social import Intent, detect
from graph.nodes import NodeFn
from graph.nodes.condense import make_condense_node
from graph.nodes.extract import make_extract_node
from graph.nodes.generate import make_generate_node
from graph.nodes.grade import make_grade_node
from graph.nodes.refuse import make_refuse_node
from graph.nodes.respond import make_respond_node
from graph.nodes.retrieve import SearchFn, make_retrieve_node
from graph.nodes.social import make_social_node
from infrastructure.llm import CondenseFn, IntakeFn, StructuredInvoke

STEP_ANGRY = "angry"
STEP_NOT_DEBT = "not_debt"
STEP_NOT_REGION = "not_region"
STEP_ASK_DEBT = "ask_debt"
STEP_ASK_REGION = "ask_region"
STEP_INVITE = "invite"
STEP_ASK_PHONE = "ask_phone"
STEP_ASK_TIME = "ask_time"
STEP_ASK_READY = "ask_ready"
STEP_BOOK_DONE = "book_done"
STEP_CONFIRM_DEBT = "confirm_debt"
STEP_DECLINE = "decline_booking"
STEP_RAG = "rag"

NODE_GATE = "gate"
NODE_SOCIAL = "social"
NODE_EXTRACT = "extract"
NODE_CONDENSE = "condense"
NODE_RETRIEVE = "retrieve"
NODE_GRADE = "grade"
NODE_GENERATE = "generate"
NODE_REFUSE = "refuse"

_RESPOND_STEPS = (
    STEP_ANGRY, STEP_NOT_DEBT, STEP_NOT_REGION,
    STEP_ASK_DEBT, STEP_ASK_REGION, STEP_INVITE,
    STEP_ASK_PHONE, STEP_ASK_TIME, STEP_ASK_READY, STEP_BOOK_DONE, STEP_DECLINE, STEP_CONFIRM_DEBT,
)


def _node_respond(step: str) -> str:
    return f"respond_{step}"


def route_gate(state: GraphState) -> str:
    return NODE_SOCIAL if detect(state.question) is not Intent.QUESTION else NODE_EXTRACT


def _last_ai_text(state: GraphState) -> str:
    for msg in reversed(list(state.messages)):
        if msg.type == "ai":
            return str(msg.content)
    return ""


def _answered_scenario(state: GraphState) -> bool:
    """Последний AI-вопрос был шагом сценария (а не RAG)."""
    text = _last_ai_text(state)
    markers = ("сумма долга", "какая сумма", "в каком регионе", "регион прописки")
    return any(m in text for m in markers)


def route(state: GraphState) -> str:
    """Условное ребро extract → шаг сценария | RAG. Чистая функция."""
    p = state.profile
    logger.info("route: debt=%s region=%s phone=%s time=%s ready=%s invited=%s disq=%s", p.debt_amount, p.region, p.phone, p.consultation_time, p.ready_to_wait, p.invited, p.disqualified)

    if p.user_is_angry:
        return STEP_ANGRY

    # отсеянный клиент просит запись / даёт телефон или время: вежливый отказ, без RAG и без LLM
    if p.disqualified and p.wants_consultation:
        return STEP_DECLINE

    # сумма уже уточнялась и всё ещё мала: отказ по сумме, не зависит от kind
    if (
        p.debt_amount is not None
        and "debt_checked" in p.facts
        and not p.disqualified
        and not qualifies_by_debt(p.debt_amount)
    ):
        return STEP_NOT_DEBT

    # RAG: содержательный вопрос, не ответ на шаг сценария
    if state.kind == "question":
        return STEP_RAG

    # фильтр не пройден, клиент не спрашивает: полезная информация + вопрос фильтра, без записи
    if p.disqualified:
        return STEP_NOT_REGION if p.region and is_excluded_region(p.region) else STEP_NOT_DEBT

    # пока фильтры не собраны — задаём вопросы
    if p.debt_amount is None:
        return STEP_ASK_DEBT
    if not qualifies_by_debt(p.debt_amount):
        # малая сумма может быть частью долга: сначала уточняем, потом отказываем
        return STEP_NOT_DEBT if "debt_checked" in p.facts else STEP_CONFIRM_DEBT
    if p.region is None:
        return STEP_ASK_REGION
    if is_excluded_region(p.region):
        return STEP_NOT_REGION

    # фильтры пройдены — приглашение
    if not p.invited:
        return STEP_INVITE

    # запись: телефон+время (один вопрос) → готовность → booked
    if p.phone is None or p.consultation_time is None:
        return STEP_ASK_PHONE
    if not p.ready_to_wait:
        return STEP_ASK_READY
    # защита: disqualified или is_booked() False → не пускаем в book_done
    if p.disqualified:
        return STEP_RAG
    if not p.is_booked():
        if p.debt_amount is None:
            return STEP_ASK_DEBT
        if p.region is None:
            return STEP_ASK_REGION
        return STEP_ASK_READY
    logger.info("route → book_done (is_booked=True)")
    return STEP_BOOK_DONE


def route_after_grade(state: GraphState) -> str:
    return NODE_REFUSE if state.refused else NODE_GENERATE


def _gate_node(state: GraphState) -> dict:
    # фиктивный узел: только чтобы start был узлом (см. статью)
    return {}


def build_graph(
    *,
    model: BaseChatModel,
    search: SearchFn,
    threshold: float,
    invoke: StructuredInvoke,
    artifacts_dir: Path,
    condense: CondenseFn | None = None,
    intake: IntakeFn | None = None,
    checkpointer: Any = None,
) -> Any:
    rewrite: CondenseFn = condense if condense is not None else (lambda q, h: q)

    def fallback_intake(q: str, h: Sequence) -> Any:
        from infrastructure.llm import IntakeDraft
        return IntakeDraft(kind="situation")

    read: IntakeFn = intake if intake is not None else fallback_intake

    nodes: dict[str, NodeFn] = {
        NODE_GATE: _gate_node,
        NODE_SOCIAL: make_social_node(),
        NODE_EXTRACT: make_extract_node(read),
        NODE_CONDENSE: make_condense_node(rewrite),
        NODE_RETRIEVE: make_retrieve_node(search),
        NODE_GRADE: make_grade_node(threshold),
        NODE_GENERATE: make_generate_node(invoke, artifacts_dir=artifacts_dir),
        NODE_REFUSE: make_refuse_node(),
    }
    for step in _RESPOND_STEPS:
        nodes[_node_respond(step)] = make_respond_node(model, step=step, artifacts_dir=artifacts_dir)

    graph: StateGraph[GraphState] = StateGraph(GraphState)
    for name, node in nodes.items():
        graph.add_node(name, cast(Any, node))

    # START → gate → social | extract
    graph.add_edge(START, NODE_GATE)
    graph.add_conditional_edges(NODE_GATE, route_gate, {NODE_SOCIAL: NODE_SOCIAL, NODE_EXTRACT: NODE_EXTRACT})
    graph.add_edge(NODE_SOCIAL, END)

    # extract → route (шаг сценария или RAG)
    graph.add_conditional_edges(
        NODE_EXTRACT,
        route,
        {
            **{step: _node_respond(step) for step in _RESPOND_STEPS},
            STEP_RAG: NODE_CONDENSE,
        },
    )
    for step in _RESPOND_STEPS:
        graph.add_edge(_node_respond(step), END)

    # RAG
    graph.add_edge(NODE_CONDENSE, NODE_RETRIEVE)
    graph.add_edge(NODE_RETRIEVE, NODE_GRADE)
    graph.add_conditional_edges(
        NODE_GRADE, route_after_grade, {NODE_GENERATE: NODE_GENERATE, NODE_REFUSE: NODE_REFUSE}
    )
    graph.add_edge(NODE_GENERATE, END)
    graph.add_edge(NODE_REFUSE, END)

    return graph.compile(checkpointer=checkpointer)
