"""Понимание одной реплики клиента (цепочка chat_v2, узел 09).

Один вызов LLM-порта → JSON → Analysis. Модель понимает речь и извлекает факты (D2); код лишь
нормализует структуру: значения фактов — строки, ключи фактов о критериях приводятся к
дословным меткам условий корпуса, missing = условия без известных значений. Знаний о предметной
области в модуле нет: условия, их формат и примеры приходят из корпуса (Topics.qualify).
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

from pydantic import ValidationError

from ..models.analysis import Analysis
from ..models.criteria import Criterion, CriterionKind
from ..models.dialog_state import DialogState
from ..models.turn import Turn
from .llm_port import LLMPort
from .qualification import same_label
from .topics_map import Topics

HISTORY_TURNS: int = 10
TURN_CHARS: int = 500

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
    "- scope=off_kb, только если сообщение вообще не про долги, банкротство, услуги, цену, регионы и "
    "условия работы компании, юриста или консультацию. Не угадывай, что клиент «скорее всего имел в "
    "виду», и не подменяй его вопрос похожим.\n"
    "- scope=clarify, если клиент не понял вопрос ассистента или просит объяснить проще.\n"
    "- scope=in_kb для всего остального.\n"
    "- question — самостоятельная формулировка запроса для поиска по базе: без «он/это/там», целиком "
    "из смысла текущего сообщения (при необходимости — с учётом последнего вопроса ассистента).\n"
    "- facts — только то, что клиент САМ сообщил в текущем сообщении или в истории. Все значения — "
    "строки. Пустой объект, если ничего нового. Ничего не додумывай.\n"
    "- Значение критерия квалификации записывай под меткой критерия дословно и в формате, указанном в "
    "списке критериев. Ответ клиента на недавний вопрос ассистента о критерии (например, «310к всего») "
    "— это значение этого критерия.\n"
    "- Часть величины, отдельный платёж, рассрочка или другая смежная величина — НЕ значение критерия, "
    "если клиент не сказал, что это и есть всё: не записывай её под меткой критерия.\n"
    "- missing — метки критериев, значений которых у клиента ещё нет (дословно из списка); если все "
    "известны — пустой массив.\n"
    "- asked_already — метки критериев, о которых ассистент УЖЕ спрашивал в истории (дословно).\n"
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


def _stringify_facts(data: dict[str, object]) -> dict[str, object]:
    """Значения фактов → строки: модель может вернуть число (310000), схема ждёт str."""
    facts = data.get("facts")
    if not isinstance(facts, dict):
        return data
    return {**data, "facts": {str(k): str(v) for k, v in facts.items() if v is not None}}


def _snap(analysis: Analysis, criteria: Sequence[Criterion], state: DialogState) -> Analysis:
    """Ключи фактов → метки условий; missing = условия без значений; asked_already — метки условий."""
    labels = [c.label for c in criteria]
    facts: dict[str, str] = {}
    for key, value in analysis.facts.items():
        canonical = next((label for label in labels if same_label(label, key)), key)
        facts[canonical] = value
    known = [key for key, value in {**state.facts, **facts}.items() if str(value).strip()]
    missing = [label for label in labels if not any(same_label(label, key) for key in known)]
    asked = [label for label in labels if any(same_label(label, item) for item in analysis.asked_already)]
    return analysis.model_copy(update={"facts": facts, "missing": missing, "asked_already": asked})


def _criteria_block(criteria: Sequence[Criterion]) -> str:
    """Список условий с форматом значения: сумма цифрами, территория — официальным названием."""
    lines: list[str] = []
    for criterion in criteria:
        if criterion.kind is CriterionKind.MIN_AMOUNT:
            hint = "значение — целое число рублей, только цифры (например, «250к» → 250000, «1,5 млн» → 1500000)"
        else:
            hint = (
                "значение — официальное полное название в именительном падеже в том же виде, что в этих "
                "примерах формата: " + "; ".join(criterion.excluded) + " (примеры показывают только формат, "
                "не подсказывают ответ). Если клиент назвал город, район или аббревиатуру, запиши "
                "официальное название территории (субъекта РФ), в которую они входят"
            )
        lines.append(criterion.label + " — " + hint)
    return "\n".join(lines)


def _clip_tail(text: str, limit: int) -> str:
    """Реплика ассистента: вопрос стоит в конце, поэтому режем начало, а не хвост."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else "…" + flat[-(limit - 1) :].lstrip()


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
            analysis = Analysis.model_validate(_stringify_facts(data))
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
        criteria_block = _criteria_block(topics.qualify)
        blocks.append("Критерии квалификации (по порядку):\n" + (criteria_block if criteria_block else "(нет)"))
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
            if turn.role == "assistant":
                text = _clip_tail(turn.content, self._turn_chars)
            else:
                text = " ".join(turn.content.split())[: self._turn_chars]
            lines.append(f"{who.get(turn.role, turn.role)}: {text}")
        return "\n".join(lines)
