"""Unit: ChatService как оркестратор цепочки chat_v2 (узел 16). Без сети и индекса."""

from __future__ import annotations

from src.core.config import Settings
from src.schemas.chat import ChatRequest
from src.services.answer_generator import NO_ANSWER_MARKER, AnswerGenerator
from src.services.chat_service import GUARDRAIL_REPLY, NO_MATCH_REPLY, ChatService
from src.services.session_store import SessionStore
from src.services.social_branch import GREETING_FIRST, GREETING_REPEAT
from src.services.topics_map import TopicsMap
from src.services.turn_analyzer import TurnAnalyzer
from tests.unit.fakes import ScriptLLM, ScriptRetriever, analysis_json, corpus, hit


def _settings() -> Settings:
    return Settings(API_KEY="dummy", SCORE_THRESHOLD=0.35, RETRIEVER_K=3)


def _svc(
    llm: ScriptLLM,
    retriever: ScriptRetriever,
    *,
    store: SessionStore | None = None,
    chunks=None,
) -> ChatService:
    settings = _settings()
    return ChatService(
        retriever=retriever,
        generator=AnswerGenerator(llm, settings),
        analyzer=TurnAnalyzer(llm),
        topics_map=TopicsMap(llm),
        store=store or SessionStore(),
        settings=settings,
        corpus=chunks if chunks is not None else corpus("абзац один", "берем от 350к", "абзац три"),
    )


def test_grounded_answer_carries_sources() -> None:
    llm = ScriptLLM(analyses=[analysis_json()], replies=["От 350 тысяч рублей."])
    resp = _svc(llm, ScriptRetriever([hit(0.9)])).ask(ChatRequest(question="какой минимальный долг"))
    assert resp.answer == "От 350 тысяч рублей."
    assert resp.grounded is True
    assert resp.top_score == 0.9
    assert resp.sources and resp.sources[0].paragraph_start == 7


def test_guardrail_rejects_before_any_llm_call() -> None:
    llm = ScriptLLM()
    retriever = ScriptRetriever([hit(0.9)])
    resp = _svc(llm, retriever).ask(ChatRequest(question="ты идиот, верни деньги"))
    assert resp.answer == GUARDRAIL_REPLY
    assert resp.grounded is False
    assert llm.calls == []
    assert retriever.queries == []


def test_first_greeting_is_canned_and_short() -> None:
    """Критерий A3: соц-ветка не идёт в модель и не выдумывает."""
    llm = ScriptLLM()
    resp = _svc(llm, ScriptRetriever([hit(0.9)])).ask(ChatRequest(question="здравствуйте!"))
    assert resp.answer == GREETING_FIRST
    assert len(resp.answer) < 80
    assert llm.calls == []
    assert resp.sources == []


def test_repeated_greeting_is_not_the_first_one() -> None:
    history = [
        {"role": "user", "content": "здравствуйте"},
        {"role": "assistant", "content": GREETING_FIRST},
    ]
    resp = _svc(ScriptLLM(), ScriptRetriever([])).ask(ChatRequest(question="привет", history=history))
    assert resp.answer == GREETING_REPEAT


def test_off_topic_does_not_search_and_does_not_guess() -> None:
    """Критерий A1: «про гипопотамов» → короткий отказ вне темы, без «имелась в виду ипотека»."""
    llm = ScriptLLM(
        analyses=[analysis_json(scope="off_kb", question="информация про гипопотамов")],
        replies=["Про гипопотамов у нас ничего нет — мы занимаемся только долгами."],
    )
    retriever = ScriptRetriever([hit(0.9)])
    resp = _svc(llm, retriever).ask(ChatRequest(question="про гипопотамов"))
    assert retriever.queries == []
    assert "Задача этого хода: Темы нет в нашей базе" in llm.generator_prompts[0]
    assert resp.grounded is False
    assert llm.generation_calls == 1


def test_low_relevance_gives_no_context_to_model() -> None:
    llm = ScriptLLM(analyses=[analysis_json()], replies=[NO_MATCH_REPLY])
    resp = _svc(llm, ScriptRetriever([hit(0.11)])).ask(ChatRequest(question="дадут ли отсрочку"))
    assert "(по этому вопросу в базе ничего нет)" in llm.generator_prompts[0]
    assert "Темы нет в нашей базе" in llm.generator_prompts[0]
    assert resp.grounded is False


def test_no_answer_marker_becomes_honest_fallback() -> None:
    llm = ScriptLLM(analyses=[analysis_json()], replies=[NO_ANSWER_MARKER])
    resp = _svc(llm, ScriptRetriever([hit(0.9)])).ask(ChatRequest(question="есть ли скидка ветеранам"))
    assert resp.answer == NO_MATCH_REPLY
    assert resp.grounded is False


def test_search_query_comes_from_analysis_not_history() -> None:
    """Узел 07/S07: ищем по самостоятельной формулировке модели, а не по «а почём»."""
    llm = ScriptLLM(analyses=[analysis_json(question="стоимость банкротства физлиц")])
    retriever = ScriptRetriever([hit(0.8)])
    history = [
        {"role": "user", "content": "у меня долги"},
        {"role": "assistant", "content": "Понял, а какая сумма?"},
    ]
    _svc(llm, retriever).ask(ChatRequest(question="а почём?", history=history))
    assert retriever.queries[0][0] == "стоимость банкротства физлиц"


def test_session_state_survives_between_requests() -> None:
    """Узел 10/17: факты и заданные вопросы не теряются между запросами (баг v1)."""
    store = SessionStore()
    llm = ScriptLLM(
        analyses=[
            analysis_json(
                facts={"сумма долга": "310 000 ₽"}, missing=["регион прописки"], asked_already=["сумма долга"]
            ),
            analysis_json(missing=["регион прописки"], asked_already=["сумма долга", "регион прописки"]),
        ],
        replies=["Понял, 310 тысяч. А в каком регионе прописка?", "Ответ по базе."],
    )
    svc = _svc(llm, ScriptRetriever([hit(0.9)]), store=store)

    first = svc.ask(ChatRequest(question="рассрочку на 310к платить уже не могу", session_id="s1"))
    assert first.answer == "Понял, 310 тысяч. А в каком регионе прописка?"
    assert "РОВНО ОДИН уточняющий вопрос по теме: регион прописки" in llm.generator_prompts[0]
    saved = store.load("s1")
    assert saved.state.facts == {"сумма долга": "310 000 ₽"}
    assert saved.state.asked_about("сумма долга") is True
    assert len(saved.turns) == 2

    second = svc.ask(ChatRequest(question="не знаю", session_id="s1"))
    assert second.answer == "Ответ по базе."
    # о том, что уже спросили, модель доложила → Policy не гоняет диалог по кругу (A5)
    assert "РОВНО ОДИН уточняющий вопрос" not in llm.generator_prompts[1]
    assert "Встречный вопрос не обязателен" in llm.generator_prompts[1]
    assert "сумма долга: 310 000 ₽" in llm.analyzer_prompts[1]
    assert "О чём уже спрашивали:\nрегион прописки; сумма долга" in llm.analyzer_prompts[1]


def test_without_session_id_state_is_not_stored() -> None:
    store = SessionStore()
    llm = ScriptLLM(analyses=[analysis_json(facts={"город": "Тверь"})])
    _svc(llm, ScriptRetriever([hit(0.9)]), store=store).ask(ChatRequest(question="я из Твери"))
    assert store.size() == 0


def test_social_reply_is_recorded_in_turns() -> None:
    store = SessionStore()
    svc = _svc(ScriptLLM(), ScriptRetriever([]), store=store)
    svc.ask(ChatRequest(question="пока", session_id="s2"))
    turns = store.load("s2").turns
    assert [(t.role, t.content) for t in turns] == [
        ("user", "пока"),
        ("assistant", "До свидания! Если понадобится помощь — обращайтесь."),
    ]


def test_context_expansion_uses_neighbouring_paragraphs() -> None:
    chunks = corpus("один", "два", "три", "четыре", "пять")
    llm = ScriptLLM(analyses=[analysis_json()])
    resp = _svc(llm, ScriptRetriever([hit(0.9, text="три", start=3)]), chunks=chunks).ask(
        ChatRequest(question="про три")
    )
    assert [s.paragraph_start for s in resp.sources] == [1, 2, 3, 4, 5]


def test_handoff_skips_search_and_is_not_marked_as_failure() -> None:
    llm = ScriptLLM(
        analyses=[analysis_json(question="запись на консультацию", wants_consultation=True)],
        replies=["Договоримся о времени: вам удобнее звонок или сообщение?"],
    )
    retriever = ScriptRetriever([hit(0.9)])
    resp = _svc(llm, retriever).ask(ChatRequest(question="давайте консультацию"))
    assert retriever.queries == []
    assert "не продавай её заново" in llm.generator_prompts[0]
    assert resp.grounded is True
    assert resp.sources == []
