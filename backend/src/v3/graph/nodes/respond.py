# Узел respond: шаги сценария.
# Тексты сценария фиксированные (без LLM): сценарий не «плывёт» и не выдумывает слов.
# LLM пишет только справочные шаги (not_debt, not_region): полезная информация без вопросов.

from __future__ import annotations

from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from core.behavior import FIXED_STEP_TEXTS, SCENARIO_TEXTS, STEP_INSTRUCTIONS, SYSTEM_PROMPT
from domain.graph_state import GraphState
from domain.models import Answer
from domain.profile import ClientProfile, filter_question
from graph.nodes import NodeFn, NodeResult
from infrastructure.artifacts import write_json

MODEL_ERROR_TEXT = "Извините, на моей стороне что-то пошло не так. Давайте попробуем ещё раз."
NO_QUESTIONS_NOTE = " Вопросов не задавай: уточняющий вопрос добавит система."


def _profile_block(p: ClientProfile) -> str:
    parts: list[str] = []
    if p.debt_amount is not None:
        parts.append(f"сумма долга: {p.debt_amount} ₽")
    if p.region:
        parts.append(f"регион: {p.region}")
    if p.phone:
        parts.append(f"телефон: {p.phone}")
    if p.consultation_time:
        parts.append(f"время: {p.consultation_time}")
    if p.ready_to_wait:
        parts.append("готов ждать звонка: да")
    return "; ".join(parts) if parts else "(пока ничего)"


def _money(value: int | None) -> str:
    return f"{value:,}".replace(",", " ") if value is not None else ""


def _scenario_key(step: str, p: ClientProfile) -> str:
    if step != "ask_phone":
        return step
    if p.phone is None and p.consultation_time is None:
        return "ask_phone_both"
    return "ask_phone" if p.phone is None else "ask_time"


def _scenario_text(step: str, p: ClientProfile) -> str | None:
    key = _scenario_key(step, p)
    template = SCENARIO_TEXTS.get(key) or FIXED_STEP_TEXTS.get(key)
    if template is None:
        return None
    return template.format(debt=_money(p.debt_amount), phone=p.phone or "", time=p.consultation_time or "")


def _ask_model(model: BaseChatModel, state: GraphState, step: str) -> tuple[str, bool]:
    instruction = STEP_INSTRUCTIONS.get(step, "") + NO_QUESTIONS_NOTE
    messages = [
        SystemMessage(content=SYSTEM_PROMPT + "\n\n" + instruction),
        *state.messages,
        HumanMessage(
            content=(
                f"Что известно о клиенте: {_profile_block(state.profile)}\n\n"
                f"Сообщение клиента: {state.question.strip()}"
            )
        ),
    ]
    try:
        reply = model.invoke(messages)
    except Exception:
        return MODEL_ERROR_TEXT, False
    content = reply.content
    return (content if isinstance(content, str) else str(content)), True


def make_respond_node(model: BaseChatModel, *, step: str, artifacts_dir: Path | None = None) -> NodeFn:
    def node(state: GraphState) -> NodeResult:
        profile = state.profile
        text = _scenario_text(step, profile)
        model_ok = True
        if text is None:
            text, model_ok = _ask_model(model, state, step)

        # фильтр не пройден: дальше только справка и вопрос фильтра, без записи
        if step in ("not_debt", "not_region"):
            profile = profile.model_copy(update={"disqualified": True})
        if step == "invite":
            profile = profile.with_invite()
        if step == "confirm_debt":
            profile = profile.model_copy(update={"facts": {**profile.facts, "debt_checked": "1"}})
        if step == "angry":
            follow_up = filter_question(profile)
            if follow_up:
                text = f"{text}\n\n**{follow_up}**"

        if artifacts_dir:
            payload: dict[str, object] = {"step": step, "profile": profile.model_dump(), "text": text}
            if not model_ok:
                payload["error"] = "model_error"
            write_json(artifacts_dir / state.request_id / f"respond_{step}.json", payload)
        return {
            "messages": [AIMessage(content=text)],
            "answer": Answer(answer=text, grounded=False),
            "profile": profile,
        }

    return node
