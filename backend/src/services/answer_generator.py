"""Генерация ответа по контексту (цепочка chat_v2, узел 14).

Принципы зашиты в system-контракт и в инструкцию хода:
* D3 — факты берутся только из контекста, цифр «из головы» не бывает;
* A5 — ровно один уточняющий вопрос и только новый;
* A7 — сначала показать, что услышали клиента, потом ответ, потом шаг к юристу;
* D4 — вне темы отвечаем коротко и без догадок;
* NO_ANSWER допустим только там, где ход опирается на контекст (answer); у остальных действий
  (handoff, decline, rephrase, ask_one) контекст не обязателен, и слово запрещено.

Иерархия внимания как в v1: КОНТЕКСТ идёт первым и ближе всего к вопросу клиента,
история урезана скользящим окном, чтобы диалог не перекрывал документ.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..core.config import Settings
from ..models.analysis import Analysis, Style
from ..models.dialog_state import DialogState
from ..models.turn import Turn
from .llm_port import LLMPort
from .policy import Action, Decision

__all__ = ["AnswerGenerator", "LLMPort", "NO_ANSWER_MARKER", "HISTORY_WINDOW", "build_user_prompt"]

NO_ANSWER_MARKER: str = "NO_ANSWER"

HISTORY_WINDOW: int = 2
HISTORY_TURN_CHARS: int = 300

# Действия, которым нужен блок «Контекст» (поиск по базе).
CONTEXT_ACTIONS: frozenset[Action] = frozenset({Action.ANSWER, Action.ASK_ONE})

SYSTEM_INSTRUCTION: str = (
    "Ты — ассистент первичной консультации по банкротству (списание долгов, "
    "банкротство физлиц). Ты не юрист и не даёшь правовых заключений. Твоя цель — спокойно "
    "выслушать клиента, снять главный страх и подвести его к консультации юриста.\n"
    "Самое важное:\n"
    "1. Факты бери ТОЛЬКО из блока «Контекст». Нет факта в контексте — не выдумывай, а скажи, "
    "что это уточнит юрист на бесплатной консультации.\n"
    "2. Нельзя придумывать суммы, минимальные пороги, сроки, проценты, законы, условия и гарантии "
    "компании. Любая цифра в ответе обязана стоять в контексте.\n"
    "3. Не догадывайся, что клиент «скорее всего имел в виду», и не подменяй его вопрос похожим.\n"
    "4. Клиенту никогда не говори слова «контекст», «база», «документ», «источник», «по тексту»: "
    "говори по делу, как консультант компании.\n"
    "Как говорить:\n"
    "5. Сначала коротко покажи, что услышал ситуацию клиента, затем ответ, затем один следующий шаг.\n"
    "6. Уточняющий вопрос — ровно один, и только если его нет в блоке «О чём уже спрашивали» и "
    "ответа на него ещё нет в блоке «Что известно».\n"
    "7. Пиши по-русски, 2–4 коротких предложения, без заголовков, списков, юридического жаргона, "
    "без давления, запугивания и рекламы. Не спорь с клиентом и не обещай чудес.\n"
)

_ACTION_INSTRUCTION: dict[Action, str] = {
    Action.ANSWER: (
        "Дай ответ строго по контексту. Встречный вопрос не обязателен. Если в блоке «Контекст» "
        "по вопросу ничего нет, верни ровно NO_ANSWER и больше ничего."
    ),
    Action.ASK_ONE: (
        "Дай ответ строго по контексту, а затем задай РОВНО ОДИН уточняющий вопрос по теме: "
        "{ask_about}. Формулируй его сам, естественно и коротко. Если ответа в контексте нет, "
        "скажи, что это уточнит юрист на бесплатной консультации, и всё равно задай вопрос."
    ),
    Action.HANDOFF: (
        "Клиент готов к консультации — не продавай её заново. Предложи согласовать удобное время "
        "консультации с юристом и спроси, готов ли он дождаться её. Способ связи уточни, только "
        "если его ещё нет в блоке «Что известно». Ничего не обещай сверх контекста."
    ),
    Action.DECLINE_OFFTOPIC: (
        "Ответа на этот вопрос у тебя нет. Ответь 1–2 короткими предложениями по-человечески: "
        "если вопрос про долги и банкротство — скажи, что точный ответ даст юрист на бесплатной "
        "консультации; если вопрос вообще не про них — честно скажи, что занимаешься только долгами "
        "и банкротством. НЕ пытайся угадать, что клиент имел в виду. Встречный вопрос — максимум "
        "один и только по теме банкротства, либо вообще без вопроса."
    ),
    Action.REPHRASE: (
        "Клиент не понял предыдущий вопрос. Повтори тот же смысл максимально простыми словами, "
        "1–2 предложения, без новой информации, без извинений и без канцелярита."
    ),
}

# Клиент просит юриста, но критерии квалификации ещё не собраны: сначала вопрос, потом время.
_CONSULTATION_ASK_INSTRUCTION: str = (
    "Клиент просит юриста или консультацию. Не отказывай и не продавай её заново: скажи, что "
    "подготовишь информацию для юриста, и задай РОВНО ОДИН уточняющий вопрос по теме: {ask_about}. "
    "Формулируй его сам, естественно и коротко. Бесплатность и условия консультации называй только "
    "если они есть в контексте."
)

_NO_MARKER_NOTE: str = "Слово NO_ANSWER не используй: ответь по-человечески."

_STYLE_INSTRUCTION: dict[Style, str] = {
    Style.ONE_LINE: "Формат: одно короткое предложение.",
    Style.REASSURE: "Тон: спокойный, клиенту тревожно — покажи, что ситуация решаемая, не пугай.",
    Style.EXPLAIN: "Тон: деловой и понятный, разбери ситуацию коротко.",
}


def _clip(text: str, limit: int) -> str:
    """В одну строку и не длиннее limit (одна реплика не должна перекрывать контекст)."""
    flat = " ".join(text.split())
    if limit <= 0 or len(flat) <= limit:
        return flat
    return flat[: limit - 1].rstrip() + "…"


def _format_history(history: Sequence[Turn], window: int = HISTORY_WINDOW, chars: int = HISTORY_TURN_CHARS) -> str:
    recent = [t for t in history if t.content.strip()][-window:] if window > 0 else list(history)
    who = {"user": "Клиент", "assistant": "Ассистент"}
    return "\n".join(f"{who.get(t.role, t.role)}: {_clip(t.content, chars)}" for t in recent)


def _task(decision: Decision, analysis: Analysis) -> str:
    """Инструкция хода: действие + тон; без маркера NO_ANSWER там, где контекст не нужен."""
    template = _ACTION_INSTRUCTION[decision.action]
    if decision.action is Action.ASK_ONE and analysis.wants_consultation:
        template = _CONSULTATION_ASK_INSTRUCTION
    task = template.format(ask_about=decision.ask_about) + " " + _STYLE_INSTRUCTION[analysis.style]
    if decision.action not in CONTEXT_ACTIONS:
        task += " " + _NO_MARKER_NOTE
    return task


def build_user_prompt(
    question: str,
    context: Sequence[str],
    decision: Decision,
    state: DialogState,
    analysis: Analysis,
    history: Sequence[Turn] = (),
) -> str:
    """Сборка промпта: контекст первым (если нужен), дальше состояние, история и задача хода."""
    blocks: list[str] = []
    if decision.action in CONTEXT_ACTIONS:
        joined = "\n\n".join(part.strip() for part in context if part.strip())
        blocks.append("Контекст:\n" + (joined if joined else "(по этому вопросу ничего не найдено)"))

    known = state.as_prompt_block()
    blocks.append("Что известно о клиенте:\n" + (known if known else "(ничего)"))
    asked = state.asked_as_prompt_block()
    blocks.append("О чём уже спрашивали:\n" + (asked if asked else "(ещё не спрашивали)"))

    dialog = _format_history(history)
    if dialog:
        blocks.append("Последние реплики (только для связки, не источник фактов):\n" + dialog)

    blocks.append("Задача этого хода: " + _task(decision, analysis))
    blocks.append(f"Вопрос клиента: {question.strip()}\n\nОтвет:")

    return "\n\n".join(blocks)


class AnswerGenerator:
    def __init__(self, llm: LLMPort, settings: Settings) -> None:
        self._llm = llm
        self._settings = settings

    def generate(
        self,
        question: str,
        context: Sequence[str],
        decision: Decision,
        state: DialogState,
        analysis: Analysis,
        history: Sequence[Turn] = (),
    ) -> str:
        if not question.strip():
            raise ValueError("Пустой вопрос")
        if decision.action is Action.ANSWER and not [c for c in context if c.strip()]:
            return NO_ANSWER_MARKER
        user = build_user_prompt(question, context, decision, state, analysis, history)
        return normalize(self._llm.complete(SYSTEM_INSTRUCTION, user))


def normalize(raw: str) -> str:
    text = raw.strip()
    if not text:
        return NO_ANSWER_MARKER
    return text
