"""Оркестратор /chat (цепочка chat_v2, узел 16) — тонкий слой, только порядок узлов.

19 🛡️ Guardrail → 20 🛡️ SocialBranch → 07 🗄️ SessionStore → 09 🧭 TurnAnalyzer →
10 💎 DialogState.merge → 13 🧭 Policy → 11 🗄️ HybridRetriever(запрос = Analysis.question) →
12 🚦 RelevanceGate → 14 🧭 AnswerGenerator → 15 🚦 AnswerGate → 17 🎛️ Presenter.

Понимание речи, темы, нехватка данных и «знаем/не знаем» — у модели (D2). Правила
выдумывания фактов запрещены (D3): ниже по коду нет ни одной строки с фактами о компании,
кроме аварийных фолбэков guardrail/no-match, которые ничего не утверждают.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ..core.config import Settings
from ..models.analysis import Analysis
from ..models.chunk import Chunk
from ..models.dialog_state import DialogState
from ..models.grounding import Grounding
from ..models.retrieved import RetrievedChunk
from ..models.turn import Turn
from ..schemas.chat import ChatRequest, ChatResponse
from .answer_gate import NO_ANSWER_MARKER, gate
from .answer_generator import AnswerGenerator
from .chat_presenter import present
from .guardrail import InputGuardrail
from .policy import Action, Decision, Policy
from .relevance_gate import RelevanceGate
from .session_store import SessionStore, dedupe_turns
from .social_branch import SocialBranch
from .topics_map import Topics, TopicsMap
from .turn_analyzer import TurnAnalyzer

CONTEXT_NEIGHBORS: int = 2

# Аварийные реплики: ничего не утверждают о продукте, поэтому не могут сгаллюцинировать (D1).
GUARDRAIL_REPLY: str = "Я ассистент по банкротству. Задавайте вопросы про долги и списание."
NO_MATCH_REPLY: str = "По этому вопросу точный ответ даст юрист на бесплатной консультации."

# Действия, которым нужен контекст из базы.
NEEDS_CONTEXT: frozenset[Action] = frozenset({Action.ANSWER, Action.ASK_ONE})
# Действия «по-человечески», без ссылки на документ: не показываем плашку «не найдено».
CONVERSATIONAL: frozenset[Action] = frozenset({Action.HANDOFF, Action.REPHRASE})


class SearchPort(Protocol):
    def search(self, question: str, k: int) -> list[RetrievedChunk]: ...


class ChatService:
    def __init__(
        self,
        retriever: SearchPort,
        generator: AnswerGenerator,
        analyzer: TurnAnalyzer,
        topics_map: TopicsMap,
        store: SessionStore,
        settings: Settings,
        corpus: Sequence[Chunk] | None = None,
        policy: Policy | None = None,
        relevance: RelevanceGate | None = None,
        guardrail: InputGuardrail | None = None,
    ) -> None:
        self._retriever = retriever
        self._generator = generator
        self._analyzer = analyzer
        self._topics_map = topics_map
        self._store = store
        self._settings = settings
        self._corpus: list[Chunk] = list(corpus or [])
        self._policy = policy or Policy()
        self._relevance = relevance or RelevanceGate(settings.score_threshold)
        self._guardrail = guardrail or InputGuardrail()
        self._topics: Topics | None = None

    def ask(self, request: ChatRequest) -> ChatResponse:
        question = request.question.strip()
        history = list(request.history)

        if not question or not self._guardrail.check(question):
            return present(GUARDRAIL_REPLY, Grounding.NOT_ANSWERABLE, [], [])

        canned = SocialBranch.replica(question, history)
        if canned is not None:
            self._commit(request.session_id, history, DialogState.empty(), question, canned)
            return present(canned, Grounding.SOCIAL, [], [])

        session = self._store.load(request.session_id)
        turns = dedupe_turns(session.turns, history)
        analysis = self._analyzer.analyze(question, turns, session.state, self._topics_of_corpus())
        state = session.state.merged(analysis.facts, analysis.asked_already)
        decision = self._policy.decide(analysis, state)

        hits: list[RetrievedChunk] = []
        expanded: list[Chunk] = []
        if decision.action in NEEDS_CONTEXT:
            hits, expanded, decision = self._retrieve(request, analysis, decision)

        if decision.action is Action.ASK_ONE and decision.ask_about:
            # помечаем, о чём спросили, сами и только когда вопрос реально задаётся (A5)
            state = state.merged(asked=[decision.ask_about])

        answer = self._generator.generate(question, [c.text for c in expanded], decision, state, analysis, turns)
        grounding = self._grounding(decision, hits, answer)
        if answer == NO_ANSWER_MARKER:
            answer = NO_MATCH_REPLY

        self._commit(request.session_id, turns, state, question, answer)
        return present(answer, grounding, hits, expanded)

    def _retrieve(
        self,
        request: ChatRequest,
        analysis: Analysis,
        decision: Decision,
    ) -> tuple[list[RetrievedChunk], list[Chunk], Decision]:
        """Поиск по формулировке модели (без истории) + проверка релевантности выдачи."""
        query = analysis.question.strip() or request.question.strip()
        hits = self._retriever.search(query, request.k or self._settings.retriever_k)
        if self._relevance.judge(hits).enough:
            return hits, self._expand(hits), decision
        if decision.action is Action.ASK_ONE:
            # вопрос квалификации задаём и без найденного контекста: факты не выдумываем (D3)
            return hits, [], decision
        return hits, [], Decision(action=Action.DECLINE_OFFTOPIC, style=analysis.style)

    def _grounding(self, decision: Decision, hits: Sequence[RetrievedChunk], answer: str) -> Grounding:
        if decision.action in CONVERSATIONAL:
            return Grounding.SOCIAL
        if decision.action in NEEDS_CONTEXT:
            return gate(hits, answer, self._settings)
        return Grounding.NOT_ANSWERABLE

    def _commit(
        self,
        session_id: str | None,
        turns: Sequence[Turn],
        state: DialogState,
        question: str,
        answer: str,
    ) -> None:
        """Сохранить ход. Без session_id состояние не копится (обратная совместимость)."""
        if not session_id:
            return
        nxt = dedupe_turns(
            turns,
            [Turn(role="user", content=question), Turn(role="assistant", content=answer)],
        )
        self._store.save(session_id, state, nxt)

    def _topics_of_corpus(self) -> Topics:
        if self._topics is None:
            self._topics = self._topics_map.of(self._corpus)
        return self._topics

    def _expand(self, hits: Sequence[RetrievedChunk]) -> list[Chunk]:
        """Дотянуть соседей по документу: окна поиска часто режут мысль пополам."""
        if not self._corpus:
            return [h.chunk for h in hits]
        span_index: dict[tuple[str, int], list[int]] = {}
        for i, c in enumerate(self._corpus):
            span_index.setdefault((c.source, c.span.start), []).append(i)
        seen: set[int] = set()
        out: list[Chunk] = []
        for hit in hits:
            positions = span_index.get((hit.chunk.source, hit.chunk.span.start), [])
            if not positions:
                out.append(hit.chunk)
                continue
            for pos in positions:
                for j in range(
                    max(0, pos - CONTEXT_NEIGHBORS), min(len(self._corpus) - 1, pos + CONTEXT_NEIGHBORS) + 1
                ):
                    if j in seen:
                        continue
                    seen.add(j)
                    out.append(self._corpus[j])
        return out
