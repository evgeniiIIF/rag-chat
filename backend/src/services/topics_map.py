"""Карта тем корпуса и критерии квалификации (цепочка chat_v2, узел 08).

Темы и критерии извлекает модель из ВСЕГО корпуса (D2): текст режется на пакеты по абзацам,
чтобы хвост документа не терялся. Критерии квалификации (qualify) — то, что по тексту
консультант обязан выяснить у клиента до записи на консультацию; порядок — как в корпусе.
В коде нет ни слов-критериев, ни названий компании.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from ..models.chunk import Chunk


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
Найди в тексте КЛЮЧЕВЫЕ КРИТЕРИИ, которые консультант должен выяснить у клиента до записи
на консультацию к юристу: условия, по которым клиента берут в работу или не берут.
Верни СТРОГО JSON-массив из 1–4 коротких меток (1–4 слова каждая) в порядке из текста.
Бери только критерии, которые в тексте прямо названы ключевыми или условиями приёма клиента.
Не включай то, на что юрист смотрит уже на самой консультации. Не выдумывай.
Если таких критериев в тексте нет — верни [].
"""

_MAX_TOPICS = 25
_MAX_TOTAL_TOPICS = 40
_MAX_QUALIFY = 4
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


def parse_qualify(raw: str) -> tuple[str, ...]:
    """Критерии квалификации: только JSON-массив, никакого построчного фолбэка."""
    return tuple(_json_labels(raw)[:_MAX_QUALIFY])


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
    """Неизменяемое значение: темы корпуса + критерии квалификации (VO)."""

    lines: tuple[str, ...]
    qualify: tuple[str, ...] = ()

    @classmethod
    def empty(cls) -> Topics:
        return Topics(lines=())

    def as_prompt_block(self) -> str:
        return "\n".join(self.lines)

    def qualify_as_prompt_block(self) -> str:
        return "\n".join(self.qualify)

    def is_empty(self) -> bool:
        return len(self.lines) == 0


class TopicsMap:
    """Кэш карты тем по хешу корпуса. Строится один раз, дальше берётся из кэша."""

    def __init__(self, llm: _LLM) -> None:
        self._llm = llm
        self._cache: dict[str, Topics] = {}

    def of(self, corpus: Sequence[Chunk], cache_key: str = "") -> Topics:
        """Построить/взять карту тем и критерии квалификации из корпуса.

        cache_key — доп. ключ (например, версия индекса). Иначе по хешу текста корпуса.
        """
        if not corpus:
            return Topics.empty()

        text = _corpus_text(corpus)
        digest = hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()[:16]
        key = f"{cache_key}:{digest}" if cache_key else digest

        if key in self._cache:
            return self._cache[key]

        topics = Topics(
            lines=_merge([self._topics_of_batch(batch) for batch in _batches(corpus)]),
            qualify=self._qualify_of(text),
        )
        self._cache[key] = topics
        return topics

    def _topics_of_batch(self, batch: str) -> tuple[str, ...]:
        try:
            return parse_topics(self._llm.complete(TOPICS_SYSTEM, batch))
        except Exception:
            return ()

    def _qualify_of(self, text: str) -> tuple[str, ...]:
        try:
            return parse_qualify(self._llm.complete(QUALIFY_SYSTEM, text[:_QUALIFY_TEXT_LIMIT]))
        except Exception:
            return ()
