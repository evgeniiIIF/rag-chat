"""Понимание одной реплики клиента (цепочка chat_v2, узел 09).

Один вызов LLM-порта → JSON → Analysis. Здесь живёт ФОРМАТ ответа модели и сборка входов
(темы корпуса, критерии квалификации, история, известное состояние). Понимание речи и
извлечение фактов — у модели (D2). Код лишь нормализует структуру: приводит asked_already к
дословным меткам критериев корпуса и считает missing как «критерии минус известные факты».
Знаний о предметной области в этом модуле нет.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

from pydantic import ValidationError

from ..models.analysis import Analysis
from ..models.dialog_state import DialogState
from ..models.turn import Turn
from .llm_port import LLMPort
from .topics_map import Topics

HISTORY_TURNS: int = 10
TURN_CHARS: int = 300
MIN_LABEL_CHARS: int = 5

_REPLY_SHAPE: str = json.dumps(
    {
        "scope": "in_kb|off_kb|clarify",
        "question": "...",
        "facts": {"метка": "значение"},
        "missing": ["метка"],
        "asked_already": ["метка"],
        "wants_consultation": False,
        "style": "one_line|explain|reassure",
    },
    ensure_ascii=False,
    separators=(",", ":"),
)

ANALYZER_SYSTEM: str = (
    "Ты анализируешь сообщение клиента в чате компании по списанию долгов и банкротству физлиц.\n"
    "Тебе дают: темы базы знаний, критерии квалификации, известные факты, о чём уже спрашивали, "
    "историю диалога и текущее сообщение.\n"
    "Верни ТОЛЬКО один JSON-объект без пояснений и без markdown:\n"
    + _REPLY_SHAPE
    + "\nПравила:\n"
    "- scope=off_kb, если сообщение не про долги, банкротство, услуги и условия работы компании и его темы "
    "нет в списке тем базы знаний. Не угадывай, что клиент «скорее всего имел в виду», и не подменяй его "
    "вопрос похожим.\n"
    "- scope=clarify, если клиент не понял вопрос ассистента или просит объяснить проще.\n"
    "- scope=in_kb для всего остального, что касается долгов, списания, банкротства, денег, документов, "
    "регионов, рассрочки, стоимости услуг, юриста и консультации.\n"
    "- question — самостоятельная формулировка запроса для поиска по базе: без «он/это/там», целиком из "
    "смысла текущего сообщения.\n"
    "- facts — только то, что клиент САМ сообщил в текущем сообщении или в истории. Пустой объект, если "
    "ничего нового. Ничего не додумывай. Если клиент назвал значение критерия квалификации, ключ факта — "
    "метка критерия дословно. Часть величины, похожая или смежная величина — НЕ значение критерия: не "
    "записывай её под меткой критерия.\n"
    "- missing — критерии квалификации из списка, значений которых ещё нет в известных фактах. Метки "
    "копируй из списка дословно, в порядке списка. Если список пуст или все критерии известны — пустой "
    "массив.\n"
    "- asked_already — критерии из того же списка, о которых ассистент УЖЕ спрашивал в истории (метка "
    "дословно).\n"
    "- wants_consultation=true, если клиент сам просит юриста, консультацию, встречу или звонок либо "
    "согласен на них. Определяй это независимо от scope.\n"
    "- style: one_line — когда вопрос простой; reassure — когда клиент нервничает или стыдится; "
    "explain — иначе."
)


def _extract_json(raw: str) -> dict[str, object] | None:
    """Достать JSON-объект из ответа модели (терпимо к markdown-обёртке и шуму)."""
    text = raw.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _norm(text: str) -> str:
    return " ".join(text.lower().replace("ё", "е").split())


def _same(left: str, right: str) -> bool:
    """Одна и та же метка: совпадение или вхождение (короткая сторона не короче MIN_LABEL_CHARS)."""
    a, b = _norm(left), _norm(right)
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return bool(short) and (short == long_ or (len(short) >= MIN_LABEL_CHARS and short in long_))


def _canonical(labels: Sequence[str], qualify: Sequence[str]) -> list[str]:
    """Метки модели → дословные метки критериев (порядок корпуса); чужие метки отбрасываются."""
    return [q for q in qualify if any(_same(q, label) for label in labels)]


def _snap(analysis: Analysis, qualify: Sequence[str], state: DialogState) -> Analysis:
    """missing = критерии корпуса минус известные факты; asked_already — дословные метки критериев."""
    values = {**state.facts, **analysis.facts}
    known = [key for key, value in values.items() if str(value).strip()]
    missing = [q for q in qualify if not any(_same(q, key) for key in known)]
    asked = _canonical(analysis.asked_already, qualify)
    return analysis.model_copy(update={"missing": missing, "asked_already": asked})


class TurnAnalyzer:
    def __init__(
        self,
        llm: LLMPort,
        history_turns: int = HISTORY_TURNS,
        turn_chars: int = TURN_CHARS,
    ) -> None:
        self._llm = llm
        self._history_turns = history_turns
        self._turn_chars = turn_chars

    def analyze(
        self,
        question: str,
        history: Sequence[Turn],
        state: DialogState,
        topics: Topics,
    ) -> Analysis:
        """Реплика → Analysis. Любой сбой модели/парсинга = fallback, а не 500."""
        user = self._user_prompt(question, history, state, topics)
        try:
            raw = self._llm.complete(ANALYZER_SYSTEM, user)
        except Exception:
            return _snap(Analysis.fallback(question), topics.qualify, state)
        return _snap(self._to_analysis(raw, question), topics.qualify, state)

    def _to_analysis(self, raw: str, question: str) -> Analysis:
        data = _extract_json(raw)
        if data is None:
            return Analysis.fallback(question)
        try:
            analysis = Analysis.model_validate(data)
        except ValidationError:
            return Analysis.fallback(question)
        if not analysis.question.strip():
            analysis = analysis.model_copy(update={"question": question.strip()})
        return analysis

    def _user_prompt(
        self,
        question: str,
        history: Sequence[Turn],
        state: DialogState,
        topics: Topics,
    ) -> str:
        blocks: list[str] = []
        topic_block = topics.as_prompt_block()
        blocks.append("Темы базы знаний:\n" + (topic_block if topic_block else "(не удалось извлечь)"))
        qualify_block = topics.qualify_as_prompt_block()
        blocks.append("Критерии квалификации (по порядку):\n" + (qualify_block if qualify_block else "(нет)"))
        known = state.as_prompt_block()
        blocks.append("Что известно о клиенте:\n" + (known if known else "(ничего)"))
        asked = state.asked_as_prompt_block()
        blocks.append("О чём уже спрашивали:\n" + (asked if asked else "(ещё не спрашивали)"))
        blocks.append("История диалога:\n" + self._format_history(history))
        blocks.append(f"Сообщение клиента:\n{question.strip()}")
        return "\n\n".join(blocks)

    def _format_history(self, history: Sequence[Turn]) -> str:
        recent = [t for t in history if t.content.strip()][-self._history_turns :]
        if not recent:
            return "(это первое сообщение)"
        who = {"user": "Клиент", "assistant": "Ассистент"}
        lines: list[str] = []
        for turn in recent:
            text = " ".join(turn.content.split())[: self._turn_chars]
            lines.append(f"{who.get(turn.role, turn.role)}: {text}")
        return "\n".join(lines)
