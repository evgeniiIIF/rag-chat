"""Сценарные тесты цепочки chat_v2 (шаг S13): диалоги целиком на приёмку A1–A7.

Без сети и индекса: LLM-порт и ретривер скриптованы (tests/unit/fakes.py). Проверяется
порядок узлов и то, что в модель не уходят выдуманные факты и повторные вопросы.
Сами формулировки — за моделью, поэтому проверяем структуру хода, а не слова.
"""

from __future__ import annotations

from src.core.config import Settings
from src.schemas.chat import ChatRequest
from src.services.answer_generator import SYSTEM_INSTRUCTION, AnswerGenerator
from src.services.chat_service import ChatService
from src.services.session_store import SessionStore
from src.services.social_branch import GREETING_FIRST, GREETING_REPEAT
from src.services.topics_map import TopicsMap
from src.services.turn_analyzer import TurnAnalyzer
from tests.unit.fakes import ScriptLLM, ScriptRetriever, analysis_json, corpus, hit

DEBT_DOC = "берем в процедуру только с суммой от 350к"
SID = "lead"


def _svc(llm: ScriptLLM, retriever: ScriptRetriever, store: SessionStore | None = None) -> ChatService:
    settings = Settings(API_KEY="dummy", SCORE_THRESHOLD=0.35, RETRIEVER_K=3)
    return ChatService(
        retriever=retriever,
        generator=AnswerGenerator(llm, settings),
        analyzer=TurnAnalyzer(llm),
        topics_map=TopicsMap(llm),
        store=store or SessionStore(),
        settings=settings,
        corpus=corpus("о нас", DEBT_DOC, "про рассрочку"),
    )


def test_a1_offtopic_is_declined_without_search_and_without_interrogation() -> None:
    """A1/D4: «про гипопотамов» → короткий отказ; поиск молчит, ипотеку не подставляем."""
    llm = ScriptLLM(
        analyses=[analysis_json(scope="off_kb", question="справка о гипопотамах", missing=["сумма долга"])],
        replies=["Про гипопотамов у нас ничего нет — мы занимаемся только долгами и банкротством."],
    )
    retriever = ScriptRetriever([hit(0.9)])
    resp = _svc(llm, retriever).ask(ChatRequest(question="про гипопотамов", session_id=SID))

    assert retriever.queries == []
    assert "ипотек" not in llm.generator_prompts[0].lower()
    assert "РОВНО ОДИН уточняющий вопрос" not in llm.generator_prompts[0]
    assert resp.grounded is False


def test_a3_greetings_are_short_hardcoded_and_repeat_is_not_first() -> None:
    llm = ScriptLLM()
    svc = _svc(llm, ScriptRetriever([hit(0.9)]))

    first = svc.ask(ChatRequest(question="здравствуйте", session_id=SID))
    assert first.answer == GREETING_FIRST and len(first.answer) < 80

    history = [{"role": "user", "content": "здравствуйте"}, {"role": "assistant", "content": first.answer}]
    second = svc.ask(ChatRequest(question="привет", history=history, session_id=SID))
    assert second.answer == GREETING_REPEAT
    assert llm.calls == []  # соц-ветка (D1) вообще не ходит в модель


def test_a2_a5_a7_answer_first_then_exactly_one_new_question() -> None:
    """A2/A5/A7: ответ по контексту + один вопрос, и не про то, что уже спрашивали."""
    llm = ScriptLLM(
        analyses=[
            analysis_json(
                question="списание долга 310 тысяч через банкротство",
                facts={"сумма долга": "310 000 ₽"},
                missing=["сумма долга", "регион прописки"],
                asked_already=["сумма долга"],
            )
        ],
        replies=["310 тысяч — проходим по минимальному порогу. В каком регионе прописка?"],
    )
    retriever = ScriptRetriever([hit(0.91)])
    resp = _svc(llm, retriever).ask(ChatRequest(question="банкротство надо юрист нужен", session_id=SID))
    prompt = llm.generator_prompts[0]

    assert retriever.queries[0][0] == "списание долга 310 тысяч через банкротство"
    assert "РОВНО ОДИН уточняющий вопрос по теме: регион прописки" in prompt
    assert "по теме: сумма долга" not in prompt
    assert DEBT_DOC in prompt
    assert resp.grounded is True and resp.sources


def test_a5_repeated_question_is_not_asked_twice_across_requests() -> None:
    """Ключевой баг v1: состояние терялось, ассистент переспрашивал по кругу."""
    llm = ScriptLLM(
        analyses=[
            analysis_json(missing=["регион прописки"]),
            analysis_json(
                question="рассрочка при долге 310 тысяч",
                facts={"сумма долга": "310 000 ₽"},
                missing=["регион прописки"],
            ),
        ],
        replies=["А в каком регионе вы прописаны?", "Рассрочка есть — платите частями."],
    )
    svc = _svc(llm, ScriptRetriever([hit(0.8)]))
    svc.ask(ChatRequest(question="хочу узнать про банкротство", session_id=SID))
    svc.ask(ChatRequest(question="рассрочку на 310к платить уже не могу", session_id=SID))

    assert "РОВНО ОДИН уточняющий вопрос по теме: регион прописки" in llm.generator_prompts[0]
    assert "РОВНО ОДИН уточняющий вопрос" not in llm.generator_prompts[1]
    assert "Вопрос клиента: рассрочку на 310к платить уже не могу" in llm.generator_prompts[1]


def test_a4_style_and_tone_come_from_the_model_not_from_code() -> None:
    llm = ScriptLLM(
        analyses=[
            analysis_json(
                question="стоимость банкротства физлиц",
                facts={"эмоция": "боится остаться ни с чем"},
                style="reassure",
            )
        ],
        replies=["Волноваться не о чем — процедура рабочая. Стоимость считает юрист на консультации."],
    )
    svc = _svc(llm, ScriptRetriever([hit(0.7)]))
    svc.ask(ChatRequest(question="давай стоимость, я боюсь что останусь ни с чем", session_id=SID))
    user = llm.generator_prompts[0]

    assert "ситуация решаемая, не пугай" in user
    assert "Дай ответ строго по контексту" in user
    # тон и запрет на выдуманные факты заданы контрактом генератора (D3/A4)
    assert "2–4 коротких предложения" in SYSTEM_INSTRUCTION
    assert "нельзя придумывать" in SYSTEM_INSTRUCTION.lower()
    assert "без давления" in SYSTEM_INSTRUCTION


def test_a6_invented_threshold_never_reaches_the_prompt() -> None:
    """A6/D3: в промпте нет «500 000 ₽» — источники правды только чанки базы."""
    llm = ScriptLLM(
        analyses=[analysis_json(question="минимальная сумма долга для банкротства")],
        replies=["Мы берём в процедуру от 350 тысяч рублей."],
    )
    svc = _svc(llm, ScriptRetriever([hit(0.92)]))
    resp = svc.ask(ChatRequest(question="а точно мне подойдёт?", session_id=SID))

    assert "500" not in llm.generator_prompts[0]
    assert DEBT_DOC in llm.generator_prompts[0]
    assert resp.answer == "Мы берём в процедуру от 350 тысяч рублей."


def test_a7_rephrase_when_client_does_not_understand() -> None:
    llm = ScriptLLM(
        analyses=[analysis_json(scope="clarify", question="просит объяснить предыдущий вопрос проще")],
        replies=["Я спрашиваю, какая у вас общая сумма долгов."],
    )
    retriever = ScriptRetriever([hit(0.9)])
    resp = _svc(llm, retriever).ask(ChatRequest(question="непонял", session_id=SID))

    assert retriever.queries == []
    assert "Повтори тот же смысл максимально простыми словами" in llm.generator_prompts[0]
    assert resp.grounded is True


def test_handy_client_agreement_hands_off_without_new_search() -> None:
    llm = ScriptLLM(
        analyses=[analysis_json(question="запись на бесплатную консультацию", wants_consultation=True)],
        replies=["Отлично, консультация бесплатная. Вам удобнее звонок или сообщение?"],
    )
    retriever = ScriptRetriever([hit(0.9)])
    resp = _svc(llm, retriever).ask(ChatRequest(question="давайте консультацию", session_id=SID))

    assert retriever.queries == []
    assert "не продавай её заново" in llm.generator_prompts[0]
    assert resp.grounded is True and resp.sources == []


def test_low_relevance_never_becomes_a_made_up_fact() -> None:
    """Скор ниже порога: контекст не подмешиваем, вместо цифры — «уточнит юрист»."""
    llm = ScriptLLM(
        analyses=[analysis_json(question="кредит под залог гипопотами")],
        replies=["Такого в нашей базе нет, точный ответ даст юрист на бесплатной консультации."],
    )
    svc = _svc(llm, ScriptRetriever([hit(0.12)]))
    resp = svc.ask(ChatRequest(question="а у вас есть кредит под залог?", session_id=SID))

    assert DEBT_DOC not in llm.generator_prompts[0]
    assert resp.grounded is False and resp.sources == []
