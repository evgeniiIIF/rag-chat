"""Карта тем корпуса и условия приёма клиента (цепочка chat_v2, узел 08).

Темы и условия извлекает модель из ВСЕГО корпуса (D2): текст режется на пакеты по абзацам,
хвост документа не теряется. Условие приёма (Criterion) — то, что по тексту консультант обязан
выяснить до записи на консультацию: «значение не меньше порога» или «значения из перечня не
берём». В коде нет ни слов-условий, ни названий компании и регионов.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from ..models.chunk import Chunk
from ..models.criteria import Criterion, CriterionKind


class _LLM(Protocol):
    def complete(self, system: str, user: str) -> str: ...


TOPICS_SYSTEM = """
Ты — строитель карты тем базы знаний компании по банкротству физических лиц.
Дан текст базы знаний (документы). Верни СТРОГО список тем, которые РЕАЛЬНО раскрыты в тексте.
Формат: JSON-массив строк, 10–25 элементов, каждая 2–8 слов.
Темы берутся из текста, не выдумывай, не добавляй общие («консультация», «помощь»).
"""

QUALIFY_SYSTEM = """
Ты читаешь инструкцию для консультанта первой линии компании по банкротству.
Найди в тексте КЛЮЧЕВЫЕ УСЛОВИЯ ПРИЁМА клиента: то, что консультант обязан выяснить до записи на
консультацию к юристу и по чему компания берёт клиента в работу или не берёт.
Верни СТРОГО JSON-массив объектов (1–4 элемента, порядок как в тексте), других слов не пиши.
Два вида объектов:
{"label": "метка", "kind": "min_amount", "min_rub": 100000} — условие «значение не меньше порога»;
min_rub — целое число рублей без пробелов («от 100к» → 100000).
{"label": "метка", "kind": "excluded_values", "excluded": ["Название 1", "Название 2"]} — условие
«с такими значениями не работаем»; excluded — официальные полные названия в именительном падеже
(аббревиатуры раскрывай до полного названия).
label — короткая метка (1–3 слова) так, как условие названо в тексте.
Бери только условия, которые в тексте прямо названы ключевыми или условиями приёма. Не включай то,
на что юрист смотрит на самой консультации. Не выдумывай. Если таких условий нет — верни [].
"""

_MAX_TOPICS = 25
_MAX_TOTAL_TOPICS = 40
_MAX_QUALIFY = 4
_MAX_QUALIFY_TRIES = 3
_BATCH_CHARS = 12000
_QUALIFY_TEXT_LIMIT = 60000


def _corpus_text(corpus: Sequence[Chunk]) -> str:
    return "\n\n".join(c.text for c in corpus)


def _batches(corpus: Sequence[Chunk], size: int = _BATCH_CHARS) -> list[str]:
    """Пакеты текста ≤ size знаков по границам абзацев; ничего не отбрасывается."""
    batches: list[str] = []
    current: list[str] = []
    length = 0
    for chunk in corpus:
        text = chunk.text.strip()
        for piece in (text[i : i + size] for i in range(0, len(text), size)):
            if current and length + len(piece) > size:
                batches.append("\n\n".join(current))
                current, length = [], 0
            current.append(piece)
            length += len(piece)
    if current:
        batches.append("\n\n".join(current))
    return batches


def _json_labels(raw: str) -> list[str]:
    """Строки из JSON-массива (весь ответ или первый массив в нём); иначе пусто."""
    candidates = [raw.strip()]
    found = re.search(r"\[\s*\"[^\]]+\]", raw, re.DOTALL)
    if found:
        candidates.append(found.group())
    for text in candidates:
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, list):
            out = [str(x).strip().lower() for x in data if str(x).strip()]
            if out:
                return out
    return []


def parse_topics(raw: str) -> tuple[str, ...]:
    """Извлечение списка строк из JSON/Markdown (структурная логика, без домена)."""
    out = _json_labels(raw)
    if out:
        return tuple(out[:_MAX_TOPICS])

    # Фолбэк: построчно, срезая нумерацию и маркеры списка
    lines: list[str] = []
    for line in raw.splitlines():
        clean = re.sub(r"^[\s\-*•–—0-9.)\]]+", "", line).strip()
        if clean and len(clean) < 120:
            lines.append(clean.lower())
    return tuple(lines[:_MAX_TOPICS])


def _json_list(raw: str) -> list[object]:
    """Первый JSON-массив в ответе модели (терпимо к markdown-обёртке и шуму); иначе пусто."""
    start, end = raw.find("["), raw.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(raw[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return []
    return data if isinstance(data, list) else []


def _positive_int(raw: object) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return int(raw) if raw > 0 else None
    if isinstance(raw, str):
        digits = raw.replace(" ", "").replace("\u00a0", "")
        return int(digits) if digits.isdigit() and int(digits) > 0 else None
    return None


def _criterion_of(item: object) -> Criterion | None:
    """Один объект из ответа модели → Criterion; невалидное отбрасывается."""
    if not isinstance(item, dict):
        return None
    label = str(item.get("label", "")).strip().lower()
    kind = str(item.get("kind", "")).strip()
    if not label:
        return None
    if kind == CriterionKind.MIN_AMOUNT.value:
        minimum = _positive_int(item.get("min_rub"))
        return Criterion(label=label, kind=CriterionKind.MIN_AMOUNT, min_rub=minimum) if minimum else None
    if kind == CriterionKind.EXCLUDED_VALUES.value:
        raw_items = item.get("excluded")
        excluded = tuple(str(x).strip() for x in raw_items if str(x).strip()) if isinstance(raw_items, list) else ()
        return Criterion(label=label, kind=CriterionKind.EXCLUDED_VALUES, excluded=excluded) if excluded else None
    return None


def parse_qualify(raw: str) -> tuple[Criterion, ...]:
    """Условия приёма из ответа модели; дубли меток и невалидные объекты отбрасываются."""
    out: list[Criterion] = []
    for item in _json_list(raw):
        criterion = _criterion_of(item)
        if criterion is not None and all(criterion.label != known.label for known in out):
            out.append(criterion)
    return tuple(out[:_MAX_QUALIFY])


def _merge(parts: Sequence[tuple[str, ...]]) -> tuple[str, ...]:
    """Склейка тем пакетов без дублей, порядок сохраняется."""
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        for line in part:
            if line not in seen:
                seen.add(line)
                out.append(line)
    return tuple(out[:_MAX_TOTAL_TOPICS])


@dataclass(frozen=True)
class Topics:
    """Неизменяемое значение: темы корпуса + условия приёма клиента (VO)."""

    lines: tuple[str, ...]
    qualify: tuple[Criterion, ...] = ()

    @classmethod
    def empty(cls) -> Topics:
        return Topics(lines=())

    def as_prompt_block(self) -> str:
        return "\n".join(self.lines)

    def qualify_labels(self) -> tuple[str, ...]:
        return tuple(c.label for c in self.qualify)

    def is_empty(self) -> bool:
        return len(self.lines) == 0


class TopicsMap:
    """Кэш тем и условий по хешу корпуса. Пустой результат не кэшируется навсегда (сбой модели)."""

    def __init__(self, llm: _LLM) -> None:
        self._llm = llm
        self._lines_cache: dict[str, tuple[str, ...]] = {}
        self._qualify_cache: dict[str, tuple[Criterion, ...]] = {}
        self._qualify_tries: dict[str, int] = {}

    def of(self, corpus: Sequence[Chunk], cache_key: str = "") -> Topics:
        """Построить/взять темы и условия приёма из корпуса.

        cache_key — доп. ключ (например, версия индекса). Иначе по хешу текста корпуса.
        """
        if not corpus:
            return Topics.empty()

        text = _corpus_text(corpus)
        digest = hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()[:16]
        key = f"{cache_key}:{digest}" if cache_key else digest
        return Topics(lines=self._lines_for(key, corpus), qualify=self._qualify_for(key, text))

    def _lines_for(self, key: str, corpus: Sequence[Chunk]) -> tuple[str, ...]:
        cached = self._lines_cache.get(key)
        if cached is not None:
            return cached
        lines = _merge([self._topics_of_batch(batch) for batch in _batches(corpus)])
        if lines:
            self._lines_cache[key] = lines
        return lines

    def _qualify_for(self, key: str, text: str) -> tuple[Criterion, ...]:
        cached = self._qualify_cache.get(key)
        if cached is not None:
            return cached
        tries = self._qualify_tries.get(key, 0)
        if tries >= _MAX_QUALIFY_TRIES:
            return ()
        self._qualify_tries[key] = tries + 1
        found = self._qualify_of(text)
        if found:
            self._qualify_cache[key] = found
        return found

    def _topics_of_batch(self, batch: str) -> tuple[str, ...]:
        try:
            return parse_topics(self._llm.complete(TOPICS_SYSTEM, batch))
        except Exception:
            return ()

    def _qualify_of(self, text: str) -> tuple[Criterion, ...]:
        try:
            return parse_qualify(self._llm.complete(QUALIFY_SYSTEM, text[:_QUALIFY_TEXT_LIMIT]))
        except Exception:
            return ()
