"""Оркестратор /chat: Guardrail -> Small Talk -> Поиск -> Генерация."""

from __future__ import annotations

from collections.abc import Sequence

from ..core.config import Settings
from ..models.chunk import Chunk
from ..models.grounding import Grounding
from ..models.retrieved import RetrievedChunk
from ..schemas.chat import ChatRequest, ChatResponse
from .answer_gate import NOT_ANSWERABLE_TEXT, gate
from .answer_generator import NO_ANSWER_MARKER, AnswerGenerator
from .chat_presenter import present
from .guardrail import InputGuardrail
from .query_condenser import QueryCondenser

CONTEXT_NEIGHBORS: int = 2

GREETINGS = {"привет", "прив", "здравствуйте", "здрасьте", "добрый день", "добрый вечер", "хай", "ку", "здорово", "салют", "hi", "hello", "дароу"}
THANKS = {"спасибо", "благодарю", "спс"}
BYE = {"пока", "до свидания", "бай"}


class ChatService:
    def __init__(
        self,
        retriever: object,
        generator: AnswerGenerator,
        condenser: QueryCondenser,
        settings: Settings,
        corpus: Sequence[Chunk] | None = None,
    ) -> None:
        self._retriever = retriever
        self._generator = generator
        self._condenser = condenser
        self._settings = settings
        self._corpus: list[Chunk] = list(corpus or [])
        self._guardrail = InputGuardrail()

    def ask(self, request: ChatRequest) -> ChatResponse:
        q = request.question.strip()

        # 1. Input Guardrail (защита от мусора)
        if not self._guardrail.check(q):
            return present("Я ассистент по банкротству. Пожалуйста, задавайте вопросы по делу.", Grounding.NOT_ANSWERABLE, [], [])

        # 2. Small talk (без поиска)
        if self._is_small_talk(q):
            return present(self._small_talk_answer(q), Grounding.GROUNDED, [], [])

        # 3. Поиск по документу
        standalone = self._condenser.standalone(q, request.history)
        k = request.k or self._settings.retriever_k
        hits: list[RetrievedChunk] = self._retriever.search(standalone, k)  # type: ignore[attr-defined]
        expanded = self._expand(hits)

        # 4. Генерация
        answer: str | None
        if not hits or _top(hits) < self._settings.score_threshold:
            answer = None
        else:
            context = [c.text for c in expanded]
            answer = self._generator.generate(standalone, context)

        grounding = gate(hits, answer, self._settings)
        final = answer if grounding is Grounding.GROUNDED and answer else NOT_ANSWERABLE_TEXT
        return present(final, grounding, hits, expanded)

    def _is_small_talk(self, q: str) -> bool:
        low = q.lower().strip()
        return any(word in low for word in GREETINGS | THANKS | BYE)

    def _small_talk_answer(self, q: str) -> str:
        low = q.lower().strip()
        if any(word in low for word in GREETINGS):
            return "Привет! Я ассистент по банкротству. Чем могу помочь?"
        if any(word in low for word in THANKS):
            return "Пожалуйста! Рад был помочь. Если есть ещё вопросы — спрашивайте."
        if any(word in low for word in BYE):
            return "До свидания! Если понадобится помощь — обращайтесь."
        return "Я на связи. Задайте вопрос по банкротству."

    def _expand(self, hits: Sequence[RetrievedChunk]) -> list[Chunk]:
        if not self._corpus:
            return [h.chunk for h in hits]
        seen: set[tuple[str, int, int, int]] = set()
        out: list[Chunk] = []
        span_index: dict[tuple[str, int], list[int]] = {}
        for i, c in enumerate(self._corpus):
            span_index.setdefault((c.source, c.span.start), []).append(i)
        for hit in hits:
            key = (hit.chunk.source, hit.chunk.span.start)
            positions = span_index.get(key, [])
            if not positions:
                out.append(hit.chunk)
                continue
            for pos in positions:
                lo = max(0, pos - CONTEXT_NEIGHBORS)
                hi = min(len(self._corpus) - 1, pos + CONTEXT_NEIGHBORS)
                for j in range(lo, hi + 1):
                    c = self._corpus[j]
                    k2 = (c.source, c.span.start, c.span.end, j)
                    if k2 in seen:
                        continue
                    seen.add(k2)
                    out.append(c)
        return out


def _top(hits: Sequence[RetrievedChunk]) -> float:
    return max((hit.score for hit in hits), default=0.0)
