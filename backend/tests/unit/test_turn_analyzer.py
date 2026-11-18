"""Unit: TurnAnalyzer (цепочка chat_v2, узел 09). Fake LLM-порт, сети нет."""

from __future__ import annotations

from src.models.analysis import Analysis, Scope, Style
from src.models.dialog_state import DialogState
from src.models.turn import Turn
from src.services.topics_map import Topics
from src.services.turn_analyzer import TurnAnalyzer

TOPICS = Topics(("списание долгов", "стоимость и рассрочка", "регионы работы"))


class _FakeLLM:
    def __init__(self, response: str, raises: bool = False) -> None:
        self.response = response
        self.raises = raises
        self.system = ""
        self.user = ""

    def complete(self, system: str, user: str) -> str:
        self.system = system
        self.user = user
        if self.raises:
            raise RuntimeError("LLM недоступен")
        return self.response


def _analyze(
    response: str,
    question: str = "сколько стоит",
    raises: bool = False,
    state: DialogState | None = None,
    history: list[Turn] | None = None,
) -> tuple[Analysis, _FakeLLM]:
    llm = _FakeLLM(response, raises=raises)
    analysis = TurnAnalyzer(llm).analyze(question, history or [], state or DialogState.empty(), TOPICS)
    return analysis, llm


def test_valid_json_maps_to_analysis() -> None:
    raw = (
        '{"scope":"in_kb","question":"стоимость банкротства физлиц",'
        '"facts":{"сумма долга":"310 000 ₽"},"missing":["регион прописки"],'
        '"asked_already":["сумма долга"],"wants_consultation":false,"style":"one_line"}'
    )
    analysis, _ = _analyze(raw)
    assert analysis.scope is Scope.IN_KB
    assert analysis.question == "стоимость банкротства физлиц"
    assert analysis.facts == {"сумма долга": "310 000 ₽"}
    assert analysis.missing == ["регион прописки"]
    assert analysis.asked_already == ["сумма долга"]
    assert analysis.style is Style.ONE_LINE


def test_off_topic_message_is_off_kb() -> None:
    """Критерий A1: «про гипопотамов» — вне корпуса, без догадки «имелась в виду ипотека»."""
    analysis, _ = _analyze(
        '{"scope":"off_kb","question":"про гипопотамов","facts":{},"missing":[],"asked_already":[],"wants_consultation":false}'
    )
    assert analysis.scope is Scope.OFF_KB
    assert analysis.question == "про гипопотамов"


def test_consultation_agreement_sets_flag() -> None:
    analysis, _ = _analyze('{"scope":"in_kb","question":"хочу консультацию","wants_consultation":true}')
    assert analysis.wants_consultation is True


def test_markdown_fence_and_noise_are_parsed() -> None:
    analysis, _ = _analyze('```json\n{"scope":"in_kb","question":"дадут ли рассрочку"}\n```')
    assert analysis.question == "дадут ли рассрочку"


def test_json_with_extra_fields_is_accepted() -> None:
    analysis, _ = _analyze('{"scope":"in_kb","question":"q","reason":"много букв"}')
    assert analysis.question == "q"


def test_garbage_response_falls_back_to_original_question() -> None:
    """Несмакшеванный JSON не должен ронять чат и не должен выдумывать запрос."""
    analysis, _ = _analyze("извини, я не смог ответить по формату", question="какие документы нужны")
    assert analysis == Analysis.fallback("какие документы нужны")
    assert analysis.scope is Scope.IN_KB


def test_llm_failure_falls_back_without_calling_again() -> None:
    analysis, llm = _analyze("", question="сколько стоит", raises=True)
    assert analysis.question == "сколько стоит"
    assert llm.user.count("Сообщение клиента") == 1


def test_empty_question_from_model_is_replaced_by_user_text() -> None:
    analysis, _ = _analyze('{"scope":"in_kb","question":"   "}', question="а какие гарантии")
    assert analysis.question == "а какие гарантии"


def test_prompt_carries_topics_state_history_and_message() -> None:
    state = DialogState.empty().merged({"сумма долга": "310 000 ₽"}, ["регион прописки"])
    history = [Turn(role="user", content="рассрочку на 310к"), Turn(role="assistant", content="Подскажите регион")]
    _, llm = _analyze('{"scope":"in_kb","question":"q"}', state=state, history=history)
    assert "стоимость и рассрочка" in llm.user
    assert "сумма долга: 310 000 ₽" in llm.user
    assert "О чём уже спрашивали:\nрегион прописки" in llm.user
    assert "Клиент: рассрочку на 310к" in llm.user
    assert "Ассистент: Подскажите регион" in llm.user
    assert "про гипопотамов" not in llm.user
    assert "Не угадывай" in llm.system


def test_history_window_is_limited_and_clipped() -> None:
    history = [Turn(role="user", content=f"реплика {i} " + "д" * 400) for i in range(25)]
    _, llm = _analyze('{"scope":"in_kb","question":"q"}', history=history)
    assert "реплика 24" in llm.user
    assert "реплика 14" not in llm.user
    assert "д" * 301 not in llm.user
