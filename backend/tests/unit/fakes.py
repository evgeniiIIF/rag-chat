"""Фейковые порты для тестов оркестратора (цепочка chat_v2).

Один скриптованный LLM-порт обслуживает все три узла, которые ходят в модель:
TopicsMap (08), TurnAnalyzer (09) и AnswerGenerator (14) — разбор по системному промпту.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from src.models.chunk import Chunk, ParagraphSpan
from src.models.retrieved import RetrievedChunk
from src.services.topics_map import TOPICS_SYSTEM
from src.services.turn_analyzer import ANALYZER_SYSTEM

DEFAULT_TOPICS: str = '["списание долгов", "стоимость и рассрочка", "регионы работы"]'


def analysis_json(
    scope: str = "in_kb",
    question: str = "сколько стоит банкротство",
    facts: dict[str, str] | None = None,
    missing: Sequence[str] = (),
    asked_already: Sequence[str] = (),
    wants_consultation: bool = False,
    style: str = "explain",
) -> str:
    return json.dumps(
        {
            "scope": scope,
            "question": question,
            "facts": facts or {},
            "missing": list(missing),
            "asked_already": list(asked_already),
            "wants_consultation": wants_consultation,
            "style": style,
        },
        ensure_ascii=False,
    )


def hit(score: float, text: str = "берем в процедуру только с суммой от 350к", start: int = 7) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=Chunk(source="КЦ.docx", text=text, span=ParagraphSpan(start=start, end=start)),
        score=score,
    )


def corpus(*texts: str) -> list[Chunk]:
    return [Chunk(source="КЦ.docx", text=t, span=ParagraphSpan(start=i + 1, end=i + 1)) for i, t in enumerate(texts)]


class ScriptLLM:
    """LLM-порт по скрипту: темы → анализ (по очереди) → генерация (по очереди)."""

    def __init__(
        self,
        topics: str = DEFAULT_TOPICS,
        analyses: Sequence[str] = (),
        replies: Sequence[str] = (),
    ) -> None:
        self.topics = topics
        self.analyses: list[str] = list(analyses)
        self.replies: list[str] = list(replies)
        self.analyzer_prompts: list[str] = []
        self.generator_prompts: list[str] = []
        self.calls: list[tuple[str, str]] = []

    @property
    def analysis_calls(self) -> int:
        return len(self.analyzer_prompts)

    @property
    def generation_calls(self) -> int:
        return len(self.generator_prompts)

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if system == TOPICS_SYSTEM:
            return self.topics
        if system == ANALYZER_SYSTEM:
            self.analyzer_prompts.append(user)
            return self.analyses.pop(0) if self.analyses else analysis_json()
        self.generator_prompts.append(user)
        return self.replies.pop(0) if self.replies else "Ответ по контексту."


class ScriptRetriever:
    """Возвращает заранее заданные хиты и запоминает, каким запросом искали."""

    def __init__(self, hits: Sequence[RetrievedChunk] = ()) -> None:
        self.hits: list[RetrievedChunk] = list(hits)
        self.queries: list[tuple[str, int]] = []

    def search(self, question: str, k: int) -> list[RetrievedChunk]:
        self.queries.append((question, k))
        return self.hits[:k]
