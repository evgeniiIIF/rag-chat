"""Генерация ответа по контексту с учётом истории диалога. LLM — порт, промпт — константа.

Иерархия внимания: КОНТЕКСТ (документ) ближе всего к «Вопрос:», история — только для
разрешения ссылок и урезана скользящим окном, чтобы диалог не вытеснял документ.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ..core.config import Settings
from ..models.turn import Turn

NO_ANSWER_MARKER: str = "NO_ANSWER"

HISTORY_WINDOW: int = 6
HISTORY_TURN_CHARS: int = 300

SYSTEM_INSTRUCTION: str = (
    "Ты — вежливый ассистент по банкротству, ведёшь живой диалог с пользователем.\n"
    "В запросе три вида данных: «Контекст» — выдержки из документа (единственный источник фактов); "
    "«Резюме диалога»/«История диалога» — только чтобы понять, о чём речь; «Вопрос» — что спрашивают сейчас.\n"
    "Правила:\n"
    "1. Лаконичность: 1–3 предложения, без воды и повторов. Отвечай по делу.\n"
    "2. История нужна ТОЛЬКО чтобы понять смысл ссылки (местоимения «он», «мне», город, сумма долга, стадия). "
    "Не переноси из истории и резюме факты, суммы, сроки и условия — там мог быть текст без опоры на документ.\n"
    "3. Факты бери ИСКЛЮЧИТЕЛЬНО из блока «Контекст». Если фактов не хватает — честно скажи и задай "
    "1 уточняющий вопрос по теме, не выдумывай.\n"
    "4. При любом противоречии прав Контекст: числа и условия из своих прошлых ответов повторяй только "
    "если они есть в Контексте; если их там нет — не повторяй, а уточни по документу.\n"
    "5. Если вопрос по теме и в контексте есть информация — ответь, обобщи по смыслу.\n"
    "6. Если ответ отрицательный (например, «не работаем в X»), добавь позитивную альтернативу из контекста.\n"
    "7. Если вопрос СОВЕРШЕННО не по теме и в контексте нет ни слова — верни ровно одно слово: NO_ANSWER.\n"
)


@runtime_checkable
class LLMPort(Protocol):
    def complete(self, system: str, user: str) -> str: ...


def _clip(text: str, limit: int) -> str:
    """В одну строку и не длиннее limit (чтобы одна реплика не перекрывала контекст)."""
    flat = " ".join(text.split())
    if limit <= 0 or len(flat) <= limit:
        return flat
    return flat[: limit - 1].rstrip() + "…"


def _format_history(
    history: Sequence[Turn],
    window: int = HISTORY_WINDOW,
    chars: int = HISTORY_TURN_CHARS,
) -> str:
    if not history:
        return ""
    recent = list(history)[-window:] if window > 0 else list(history)
    lines: list[str] = []
    for turn in recent:
        role = "Пользователь" if turn.role == "user" else "Ассистент"
        lines.append(f"{role}: {_clip(turn.content, chars)}")
    return "\n".join(lines)


def build_user_prompt(
    question: str,
    context: Sequence[str],
    history: Sequence[Turn] = (),
    summary: str | None = None,
) -> str:
    """Контекст идёт ПЕРВЫМ и ближе всех к «Вопрос:» — документ не должен проигрывать диалогу."""
    joined = "\n\n".join(part.strip() for part in context if part.strip())
    dialog = _format_history(history)
    meta = ""
    if summary and summary.strip():
        meta += f"Резюме диалога:\n{summary.strip()}\n\n"
    if dialog:
        meta += f"История диалога:\n{dialog}\n\n"
    return f"Контекст:\n{joined}\n\n{meta}Вопрос: {question.strip()}\n\nОтвет:"


class AnswerGenerator:
    def __init__(self, llm: LLMPort, settings: Settings) -> None:
        self._llm = llm
        self._settings = settings

    def generate(
        self,
        question: str,
        context: Sequence[str],
        history: Sequence[Turn] = (),
        summary: str | None = None,
    ) -> str:
        if not question.strip():
            raise ValueError("Пустой вопрос")
        if not context:
            return NO_ANSWER_MARKER
        user = build_user_prompt(question, context, history, summary)
        raw = self._llm.complete(SYSTEM_INSTRUCTION, user)
        return normalize(raw)


def normalize(raw: str) -> str:
    text = raw.strip()
    if not text:
        return NO_ANSWER_MARKER
    return text
