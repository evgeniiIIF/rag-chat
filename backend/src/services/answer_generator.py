"""Генерация ответа (цепочка chat_v2, узел 14).

Принципы зашиты в system-контракт и в инструкцию хода:
* D3 — факты только из блоков «Контекст» и «Проверка условий», цифр «из головы» не бывает;
* цель диалога — выяснить условия приёма и довести подходящего клиента до консультации юриста,
  неподходящему вежливо объяснить; клиент не уводит разговор: после ответа — возврат к цели;
* порядок реплики: услышать клиента → разъяснить по корпусу → один шаг к цели;
* NO_ANSWER допустим только для действия answer: у остальных действий контекст не обязателен.

Иерархия внимания: КОНТЕКСТ первым и ближе всего к вопросу клиента, история — скользящим окном.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..core.config import Settings
from ..models.analysis import Analysis, Style
from ..models.criteria import Verdict
from ..models.dialog_state import DialogState
from ..models.turn import Turn
from .llm_port import LLMPort
from .policy import Action, Decision
from .qualification import describe

__all__ = ["AnswerGenerator", "LLMPort", "NO_ANSWER_MARKER", "HISTORY_WINDOW", "build_user_prompt"]

NO_ANSWER_MARKER: str = "NO_ANSWER"

HISTORY_WINDOW: int = 4
HISTORY_TURN_CHARS: int = 400

# Действия, которым нужен блок «Контекст» (поиск по базе).
CONTEXT_ACTIONS: frozenset[Action] = frozenset({Action.ANSWER, Action.ASK_ONE, Action.HANDOFF, Action.DISQUALIFY})

SYSTEM_INSTRUCTION: str = (
    "Ты — ассистент первичной консультации по банкротству (списание долгов, банкротство физлиц). "
    "Ты не юрист и не даёшь правовых заключений. Твоя цель — спокойно выслушать клиента, выяснить, "
    "подходит ли он под условия компании (они в блоке «Проверка условий»), подходящего клиента "
    "довести до бесплатной консультации юриста, а неподходящему вежливо всё объяснить.\n"
    "Самое важное:\n"
    "1. Факты о компании, услугах, ценах, сроках, процедуре и гарантиях бери ТОЛЬКО из блоков "
    "«Контекст» и «Проверка условий». Нет факта там — не выдумывай, а скажи, что это уточнит юрист "
    "на бесплатной консультации.\n"
    "2. Нельзя придумывать суммы, пороги, сроки, проценты, законы, статьи, условия и гарантии. Любая "
    "цифра в ответе обязана стоять в этих блоках или быть названа самим клиентом.\n"
    "3. «Проверка условий» посчитана программой: не пересчитывай её, не оспаривай и не додумывай, где "
    "компания работает, а где нет. Чего нет в этом блоке и в контексте — не утверждай.\n"
    "4. Не догадывайся, что клиент «скорее всего имел в виду», и не подменяй его вопрос похожим.\n"
    "5. Клиенту никогда не говори слова «контекст», «база», «документ», «источник», «проверка условий», "
    "«перечень исключений», «вердикт»: говори по делу, как консультант компании.\n"
    "Как говорить (как опытный консультант):\n"
    "6. Сначала коротко покажи, что услышал клиента (его слова и ситуацию, без пафоса). Затем ответь на "
    "его вопрос и разъясни простыми словами, что это значит для него, опираясь на контекст; факт о "
    "компании из контекста приводи, когда клиент сомневается. Затем ОДИН вопрос или шаг к цели.\n"
    "7. Не давай клиенту увести разговор: ответив, мягко возвращайся к недостающему условию. Если об "
    "этом уже спрашивали, не повторяй формулировку дословно: перефразируй и коротко объясни, зачем "
    "это нужно, например чтобы понять, подойдёт ли консультация.\n"
    "8. Острые углы обходи вежливо: не спорь, не давай, не запугивай, не обещай чудес, без рекламы.\n"
    "9. Пиши по-русски, 3–6 предложений короткими абзацами, без заголовков, списков и юридического "
    "жаргона. Вопрос в ответе — не более одного.\n"
)

_ACTION_INSTRUCTION: dict[Action, str] = {
    Action.ANSWER: (
        "Ответь строго по контексту и разъясни простыми словами. Звонок, время и контакты не предлагай. "
        "Если в блоке «Контекст» по вопросу ничего нет, верни ровно NO_ANSWER и больше ничего."
    ),
    Action.ASK_ONE: (
        "Ответь на вопрос клиента и разъясни по контексту, что это значит для него (если вопроса не было — "
        "коротко поддержи и покажи, что понял ситуацию). Затем задай РОВНО ОДИН вопрос про: {ask_about}. "
        "Если клиент уже называл часть этой величины, уточни, это ли всё. Формулируй вопрос сам, "
        "естественно и коротко; если об этом уже спрашивали, перефразируй и объясни, зачем это нужно. "
        "Если ответа на вопрос клиента в контексте нет, скажи, что это уточнит юрист на бесплатной "
        "консультации, и всё равно задай вопрос."
    ),
    Action.HANDOFF: (
        "Клиент подходит под условия компании — скажи ему об этом тепло и без пафоса. Если он задал "
        "вопрос, сначала ответь по контексту. Затем предложи согласовать удобное время консультации с "
        "юристом и убедись, что клиент готов дождаться её. Способ связи уточни, только если его ещё нет "
        "в блоке «Что известно». Если время или способ связи уже названы — подтверди и поблагодари. "
        "Не продавай консультацию заново и ничего не обещай сверх контекста."
    ),
    Action.DISQUALIFY: (
        "Клиент не подходит под условия компании (см. «Проверка условий»). Если он задал вопрос, сначала "
        "ответь на него по контексту. Затем вежливо, тепло и без давления объясни, почему компания не "
        "может взять его дело, опираясь ТОЛЬКО на условие из проверки (названное клиентом значение и "
        "порог или перечень назови как есть). Не придумывай альтернатив и не обещай ничего сверх "
        "контекста. Если клиент мог ошибиться или назвать лишь часть, предложи уточнить: если это не так, "
        "пусть подскажет. Других вопросов не задавай."
    ),
    Action.DECLINE_OFFTOPIC: (
        "Ответа на этот вопрос у тебя нет. Ответь 1–2 короткими предложениями по-человечески: если "
        "вопрос про долги и банкротство — скажи, что точный ответ даст юрист на бесплатной консультации; "
        "если вопрос вообще не про них — честно скажи, что занимаешься только долгами и банкротством. "
        "НЕ пытайся угадать, что клиент имел в виду."
    ),
    Action.REPHRASE: (
        "Клиент не понял предыдущий вопрос. Повтори тот же смысл максимально простыми словами, "
        "1–2 предложения, без новой информации, без извинений и без канцелярита."
    ),
}

# Клиент просит юриста, но условия ещё не выяснены: сначала вопрос, потом время.
_CONSULTATION_ASK_INSTRUCTION: str = (
    "Клиент просит юриста или консультацию. Не отказывай и не продавай её заново: скажи, что "
    "подготовишь информацию для юриста, и задай РОВНО ОДИН вопрос про: {ask_about}. Формулируй его "
    "сам, естественно и коротко; если об этом уже спрашивали, перефразируй и объясни, зачем это нужно. "
    "Бесплатность и условия консультации называй только если они есть в контексте."
)

_STEER_BACK: str = "Затем мягко верни разговор к цели: один вопрос про: {ask_about}."

_NO_MARKER_NOTE: str = "Слово NO_ANSWER не используй: ответь по-человечески."

_STYLE_INSTRUCTION: dict[Style, str] = {
    Style.ONE_LINE: "Формат: коротко, 1–2 предложения, но шаг к цели не пропускай.",
    Style.REASSURE: "Тон: спокойный, клиенту тревожно — покажи, что ситуация решаемая, не пугай.",
    Style.EXPLAIN: "Тон: деловой и понятный, разбери ситуацию коротко.",
}


def _clip(text: str, limit: int) -> str:
    """В одну строку и не длиннее limit (одна реплика не должна перекрывать контекст)."""
    flat = " ".join(text.split())
    if limit <= 0 or len(flat) <= limit:
        return flat
    return flat[: limit - 1].rstrip() + "…"


def _clip_tail(text: str, limit: int) -> str:
    """Реплика ассистента: вопрос стоит в конце, поэтому режем начало, а не хвост."""
    flat = " ".join(text.split())
    if limit <= 0 or len(flat) <= limit:
        return flat
    return "…" + flat[-(limit - 1) :].lstrip()


def _format_history(history: Sequence[Turn], window: int = HISTORY_WINDOW, chars: int = HISTORY_TURN_CHARS) -> str:
    recent = [t for t in history if t.content.strip()][-window:] if window > 0 else list(history)
    who = {"user": "Клиент", "assistant": "Ассистент"}
    lines: list[str] = []
    for turn in recent:
        clip = _clip_tail if turn.role == "assistant" else _clip
        lines.append(f"{who.get(turn.role, turn.role)}: {clip(turn.content, chars)}")
    return "\n".join(lines)


def _task(decision: Decision, analysis: Analysis) -> str:
    """Инструкция хода: действие + тон; без маркера NO_ANSWER везде, кроме действия answer."""
    template = _ACTION_INSTRUCTION[decision.action]
    if decision.action is Action.ASK_ONE and analysis.wants_consultation:
        template = _CONSULTATION_ASK_INSTRUCTION
    task = template.format(ask_about=decision.ask_about)
    if decision.action is Action.DECLINE_OFFTOPIC and decision.ask_about:
        task += " " + _STEER_BACK.format(ask_about=decision.ask_about)
    task += " " + _STYLE_INSTRUCTION[analysis.style]
    if decision.action is not Action.ANSWER:
        task += " " + _NO_MARKER_NOTE
    return task


def build_user_prompt(
    question: str,
    context: Sequence[str],
    decision: Decision,
    state: DialogState,
    analysis: Analysis,
    history: Sequence[Turn] = (),
    verdict: Verdict | None = None,
) -> str:
    """Сборка промпта: контекст первым (если нужен), проверка условий, состояние, история, задача хода."""
    blocks: list[str] = []
    if decision.action in CONTEXT_ACTIONS:
        joined = "\n\n".join(part.strip() for part in context if part.strip())
        blocks.append("Контекст:\n" + (joined if joined else "(по этому вопросу ничего не найдено)"))

    if verdict is not None and verdict.has_criteria:
        blocks.append("Проверка условий (посчитана программой — это факт, не пересчитывай):\n" + describe(verdict))

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
        verdict: Verdict | None = None,
    ) -> str:
        if not question.strip():
            raise ValueError("Пустой вопрос")
        if decision.action is Action.ANSWER and not [c for c in context if c.strip()]:
            return NO_ANSWER_MARKER
        user = build_user_prompt(question, context, decision, state, analysis, history, verdict)
        return normalize(self._llm.complete(SYSTEM_INSTRUCTION, user))


def normalize(raw: str) -> str:
    text = raw.strip()
    if not text:
        return NO_ANSWER_MARKER
    return text
