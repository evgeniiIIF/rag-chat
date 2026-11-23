"""Регрессия по диалогу из закрепа: регионы, телефон, время, ожидаемый слот, факты, дисциплина ответа."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from core.behavior import STAGE_INSTRUCTIONS, SYSTEM_PROMPT, booked_text
from core.formatting import answer_text, build_blocks, enforce_style
from domain.graph_state import GraphState
from domain.models import RetrievedChunk
from domain.profile import (
    ClientProfile,
    extract_phone,
    extract_time,
    is_excluded_region,
    normalize_phone,
    normalize_time,
)
from domain.scenario import expected_slot
from graph.nodes.answer import make_answer_node
from graph.nodes.extract import make_extract_node
from graph.nodes.retrieve import make_retrieve_node
from infrastructure.llm import AnswerDraft, IntakeDraft, build_prompt

QUALIFIED = ClientProfile(debt_amount=899_000, region="Дагестан")


class FakeIntake:
    def __init__(self, draft: IntakeDraft) -> None:
        self.draft = draft

    def __call__(self, question: str, history: Sequence[BaseMessage]) -> IntakeDraft:
        return self.draft


def run(question: str, draft: IntakeDraft, profile: ClientProfile) -> ClientProfile:
    state = make_extract_node(FakeIntake(draft))(GraphState(question=question, profile=profile))
    return cast(ClientProfile, state["profile"])


def test_excluded_regions_in_any_case_form() -> None:
    for region in ["Чечне", "Чечня", "в Чеченской республике", "Владимирской области", "ДНР", "Донецк"]:
        assert is_excluded_region(region), region
    assert not is_excluded_region("Дагестан")
    assert not is_excluded_region("Москва")


def test_phone_accepts_6_10_and_11_digits() -> None:
    assert normalize_phone("66 44 55") == "66-44-55"
    assert normalize_phone("999 123 45 67") == "+79991234567"
    assert normalize_phone("8 999 123-45-67") == "+79991234567"
    assert normalize_phone("6644") is None
    assert normalize_phone("12345678") is None
    assert normalize_phone("123456789012") is None


def test_extract_phone_from_text() -> None:
    assert extract_phone("мой номер 89991234567 в 12:00") == "+79991234567"
    assert extract_phone("66 44 55 завтра в 12") is None  # короткий номер — только в ответ на вопрос


def test_time_with_day_and_hour() -> None:
    assert extract_time("завтра в 12") == "завтра 12:00"
    assert extract_time("в 12") == "12:00"
    assert extract_time("899 тысяч") is None


def test_expected_slot_follows_the_steps() -> None:
    assert expected_slot(ClientProfile()) == "debt"
    assert expected_slot(ClientProfile(debt_amount=899_000)) == "region"
    assert expected_slot(QUALIFIED) == "phone"
    assert expected_slot(QUALIFIED.model_copy(update={"phone": "66-44-55"})) == "time"
    assert expected_slot(ClientProfile(debt_amount=100_000)) is None


def test_bare_digits_are_a_phone_when_phone_was_asked() -> None:
    profile = run("664455", IntakeDraft(kind="situation", debt_amount=664_455), QUALIFIED)

    assert profile.phone == "66-44-55"
    assert profile.debt_amount == 899_000


def test_bare_digits_are_a_debt_when_debt_was_asked() -> None:
    assert run("664455", IntakeDraft(kind="question"), ClientProfile()).debt_amount == 664_455


def test_short_phone_answer_stays_incomplete() -> None:
    profile = run(
        "6644 завтра в 12", IntakeDraft(kind="situation", phone="6644", consultation_time="завтра в 12:00"), QUALIFIED
    )

    assert profile.phone is None
    assert profile.phone_raw == "6644"
    assert profile.consultation_time == "завтра в 12:00"


def test_complete_phone_clears_phone_raw() -> None:
    profile = run("вот номер", IntakeDraft(kind="situation", phone="+7 900 123-45-67"), ClientProfile(phone_raw="6644"))

    assert profile.phone == "+79001234567"
    assert profile.phone_raw is None


def test_hour_only_answer_after_phone() -> None:
    booked = QUALIFIED.model_copy(update={"phone": "66-44-55"})

    assert run("12", IntakeDraft(kind="question"), booked).consultation_time == "12:00"


def test_region_answer_when_region_was_asked() -> None:
    profile = run("дагестан", IntakeDraft(kind="question"), ClientProfile(debt_amount=899_000))

    assert profile.region == "дагестан"


def test_slot_duplicates_are_dropped_from_facts() -> None:
    draft = IntakeDraft(
        kind="situation", facts={"notes": "сумма ниже порога", "долг": "899 тыс", "цель": "банкротство"}
    )

    assert run("расскажу про себя", draft, ClientProfile(facts={"interest": "МФЦ"})).facts == {"цель": "банкротство"}


def test_examples_from_practice_reach_the_client() -> None:
    """Пример из практики компании — объяснение правила, а не запрещённая история."""
    text = "Понял вас. Знаю случай, когда женщина не прошла МФЦ. Вам подойдёт рассрочка."

    styled = enforce_style(text, "info")

    assert "Знаю случай, когда женщина не прошла МФЦ." in styled
    assert "рассрочка" in styled


def test_info_has_no_questions() -> None:
    assert enforce_style("Вы не проходите по сумме. Хотите расскажу про МФЦ?", "info") == "Вы не проходите по сумме."


def test_collecting_step_keeps_ack_and_question() -> None:
    assert enforce_style("Понял. Это важно. Какая сумма долга?", "ask_debt") == "Понял. Какая сумма долга?"


def test_short_warm_ack_reaches_the_client() -> None:
    """Живой отклик — часть ответа, а не мусор: «Понял вас.» остаётся."""
    assert enforce_style("Понял вас. Какая сумма долга?", "ask_debt") == "Понял вас. Какая сумма долга?"
    assert enforce_style("Фильтры. Какая сумма долга?", "ask_debt") == "Какая сумма долга?"


def test_long_answer_is_cut_but_final_question_stays() -> None:
    text = "Раз. Два. Три. Четыре. Пять. Назовите телефон?"

    assert enforce_style(text, "invite") == "Назовите телефон?"


def test_internal_note_is_not_sent_to_client() -> None:
    text = answer_text(
        "Клиент настаивает на консультации, фильтры пройдены.",
        [],
        "",
        "invite",
        ask="Подскажите, пожалуйста, удобное время для звонка.",
    )

    assert text == "Подскажите, пожалуйста, удобное время для звонка."


def test_installment_amount_is_not_the_total_debt_when_asked() -> None:
    """Бот спросил сумму — «именно рассрочку на 310к платить уже не могу» это не общий долг."""
    profile = run(
        "я в целом с долгами справляюсь, но именно рассрочку на 310к платить уже не могу",
        IntakeDraft(kind="situation", debt_amount=310_000),
        ClientProfile(),
    )

    assert profile.debt_amount is None
    assert profile.failed_filter() is None


def test_amount_named_as_debt_is_the_total_debt() -> None:
    profile = run("500к сумма", IntakeDraft(kind="situation", debt_amount=500_000), ClientProfile())

    assert profile.debt_amount == 500_000


def test_search_is_skipped_when_knowledge_is_not_needed() -> None:
    calls: list[str] = []

    def search(query: str, k: int) -> list[RetrievedChunk]:
        calls.append(query)
        return []

    node = make_retrieve_node(search, lambda question, history: question, 0.1)
    client = QUALIFIED.model_copy(update={"phone": "+79991234567", "consultation_time": "12:00"})

    node(GraphState(question="завтра в 12", profile=client))
    assert calls == []

    node(GraphState(question="какие сроки?", profile=QUALIFIED, kind="question"))
    assert calls


def test_time_named_as_a_number_is_normalized() -> None:
    profile = run("554433 в 10", IntakeDraft(kind="situation", phone="554433", consultation_time="10"), ClientProfile())

    assert profile.consultation_time == "10:00"
    assert profile.phone == "55-44-33"


def test_mirrored_facts_collapse_to_one() -> None:
    profile = run(
        "просрочка",
        IntakeDraft(kind="situation", facts={"просрочка": "не может платить рассрочку"}),
        ClientProfile(facts={"не справляется с платежами по рассрочке": "просрочка"}),
    )

    assert profile.facts == {"просрочка": "не может платить рассрочку"}


def test_unknown_slot_note_is_not_shown_to_client() -> None:
    text = answer_text("Регион пока неизвестен.", [], "", "ask_region")

    assert text == ""


def test_blocks_do_not_show_where_the_answer_came_from() -> None:
    blocks = build_blocks("Мы берём в процедуру долги от 350 000 ₽.", "", "Какая у вас общая сумма долга?")

    assert [block["type"] for block in blocks] == ["lead", "question"]
    assert "контекст" not in str(blocks).lower()
    assert "источник" not in str(blocks).lower()


def answer_for(step_profile: ClientProfile, draft: AnswerDraft, kind: str = "question") -> str:
    state = GraphState(question="какого отказа?", profile=step_profile, kind=kind)  # type: ignore[arg-type]
    return cast(str, make_answer_node(lambda prompt: draft)(state)["answer"])


def test_info_answer_comes_from_code_not_from_model_plan() -> None:
    """Модель на info выдавала план («Ничего не гарантировать…») — клиент получает текст кода."""
    draft = AnswerDraft(text="Клиент спрашивает про отказ, надо пояснить и упомянуть МФЦ. Без вопросов.")
    text = answer_for(ClientProfile(debt_amount=310_000), draft)

    assert "350 000" in text
    assert "310 000" in text
    assert "МФЦ" in text
    for leak in ["гарантир", "обещ", "упомянут", "Без вопросов", "Клиент"]:
        assert leak.lower() not in text.lower(), leak


def test_answer_schema_has_no_plan_fields() -> None:
    """Полей под план и заметки в схеме нет: их нечем показать клиенту."""
    assert set(AnswerDraft.model_fields) == {"text", "question"}


def test_answer_description_is_not_sent_to_client() -> None:
    """«Ответ с тёплым откликом…» — описание ответа, а не ответ."""
    text = answer_text("Ответ с тёплым откликом и одним вопросом о сумме. 2–3 предложения.", [], "", "rag")

    assert text == ""


def test_plan_instead_of_answer_is_retried_and_replaced() -> None:
    """Первая попытка = план, вторая = текст: клиент получает текст, а не описание."""
    drafts = iter(
        [
            AnswerDraft(text="Ответ с тёплым откликом и одним вопросом о сумме. 2–3 предложения."),
            AnswerDraft(
                text="Рассрочка 310 тысяч — это заметная нагрузка, но для процедуры важна общая сумма "
                "по всем кредиторам: банки, МФО, налоги, ЖКХ.",
                question="Какая у вас общая сумма долга?",
            ),
        ]
    )
    state = GraphState(question="рассрочку не могу платить", profile=ClientProfile(), kind="situation")

    result = make_answer_node(lambda prompt: next(drafts))(state)

    assert "Ответ с" not in str(result["answer"])
    assert "общая сумма" in str(result["answer"]).lower()
    assert result["answer_question"] == "Подскажите, пожалуйста, какая у вас общая сумма долга?"


def test_plan_residue_is_not_shown_to_client() -> None:
    text = answer_text(
        "Упомянуто внесудебное банкротство через МФЦ. Завершение — можно написать снова. "
        "Мы смотрим общий долг по всем обязательствам.",
        [],
        "",
        "rag",
    )

    assert "Упомянуто" not in text
    assert "Завершение" not in text
    assert "общий долг" in text.lower()


def test_prompt_asks_for_business_tone_and_topic_answer() -> None:
    assert "деловым языком" in SYSTEM_PROMPT
    assert "третьем лице" in SYSTEM_PROMPT
    # логика шагов живёт в коде: правил-фильтров и регалий компании в промпте нет
    assert "с какого года работает" not in SYSTEM_PROMPT
    assert "фильтр" not in SYSTEM_PROMPT.lower()


def test_booking_text_invites_to_fix_wrong_data() -> None:
    text = booked_text(ClientProfile(phone="+79991234567", consultation_time="в 12 сегодня"), "")

    assert "+79991234567" in text
    assert "поправлю" in text


def test_failed_filter_blocks_booking_and_consultation() -> None:
    """Даже с телефоном и временем отказ по фильтру остаётся отказом: записи нет."""
    profile = ClientProfile(debt_amount=500_000, region="чечня", phone="66-68-89", consultation_time="в 14")
    draft = AnswerDraft(text="Записываю вас на консультацию, юрист позвонит.", question="")

    result = make_answer_node(lambda prompt: draft)(GraphState(question="просрочки", profile=profile))

    assert result["step"] == "info"
    assert result["answer_booking"] is None
    assert "консультац" not in str(result["answer"]).lower()


def test_one_line_answer_description_is_retried() -> None:
    """«Ответ клиенту про общую сумму долга…» — описание, а не текст: просим ответ заново."""
    drafts = iter(
        [
            AnswerDraft(text="Ответ клиенту про общую сумму долга при наличии ипотеки и рассрочки"),
            AnswerDraft(
                text=(
                    "С ипотекой процедура возможна, но требования по кредиту остаются залоговыми. "
                    "В общую сумму входит всё: кредиты, займы, налоги, ЖКХ."
                )
            ),
        ]
    )
    state = GraphState(question="рассрочку на 310к платить не могу", profile=ClientProfile())

    result = make_answer_node(lambda prompt: next(drafts))(state)

    assert "ипотек" in str(result["answer"]).lower()
    assert "Ответ клиенту" not in str(result["answer"])


def test_notes_about_client_are_retried_twice_then_code_explains() -> None:
    """Модель дважды писала «Клиент сообщил…» — клиент получает объяснение по знаниям, не голый вопрос."""
    drafts = iter(
        [
            AnswerDraft(text="Клиент сообщил о рассрочке 310 тыс., которую не может платить."),
            AnswerDraft(text="Клиент не может платить рассрочку, общая сумма долга не названа."),
            AnswerDraft(text="Клиент ждёт вопрос о сумме долга."),
        ]
    )
    state = GraphState(question="рассрочку на 310к платить не могу", profile=ClientProfile())

    result = make_answer_node(lambda prompt: next(drafts))(state)

    answer = str(result["answer"]).lower()
    assert "общая сумма обязательств" in answer
    assert "клиент" not in answer
    assert result["answer_question"] == "Подскажите, пожалуйста, какая у вас общая сумма долга?"


def test_internal_refusal_note_is_replaced_by_code_text() -> None:
    """Служебная строка «Отказ по сумме… ниже порога…» до клиента не доходит: объясняет код."""
    draft = AnswerDraft(text="Отказ по сумме долга, 310 000 ₽ ниже порога 350 000 ₽; предложить МФЦ.")
    text = answer_for(ClientProfile(debt_amount=310_000), draft)

    assert "порог" not in text
    assert "350 000" in text
    assert "МФЦ" in text


def test_system_prompt_is_short_and_forbids_sources() -> None:
    """Промпт задаёт только тон и запрет на источники: логика шагов живёт в коде."""
    from core.behavior import SYSTEM_PROMPT

    assert "источник" in SYSTEM_PROMPT
    assert len(SYSTEM_PROMPT) < 1800
    assert "фильтр" not in SYSTEM_PROMPT.lower()


def test_reminder_to_ask_question_is_not_shown() -> None:
    """«В конце задать вопрос об общей сумме долга.» — заметка себе, клиенту она не уходит."""
    drafts = iter([AnswerDraft(text="В конце задать вопрос об общей сумме долга.")] * 3)
    state = GraphState(question="рассрочку платить не могу", profile=ClientProfile(), kind="situation")

    result = make_answer_node(lambda prompt: next(drafts))(state)

    assert "в конце" not in str(result["answer"]).lower()
    assert "задать вопрос" not in str(result["answer"]).lower()
    # вместо заметки клиент получает объяснение по знаниям и вопрос шага
    assert "общая сумма обязательств" in str(result["answer"]).lower()
    assert result["answer_question"] == "Подскажите, пожалуйста, какая у вас общая сумма долга?"


def test_no_instruction_line_is_sent_to_model() -> None:
    """Промпт не содержит задания «что сказать в конце»: модель его переписывала в ответ."""
    prompt = build_prompt(step="ask_debt", profile=ClientProfile(), question="рассрочку не могу", ask="сумма?")

    sent = "\n".join(str(message.content) for message in prompt.messages).lower()
    assert "вопрос, который нужно задать" not in sent
    assert "в конце" not in sent
    assert prompt.inputs["вопрос шага"] == "сумма?"


def test_task_verbs_anywhere_in_a_sentence_are_dropped() -> None:
    """Любая фраза-задание («Далее спросить…», «В конце задать вопрос…») вырезается."""
    draft = AnswerDraft(
        text=(
            "Рассрочка на 310 тысяч входит в общую сумму долга. "
            "Далее спросить про регион. Затем предложить консультацию. "
            "В конце задать вопрос об общей сумме долга."
        )
    )

    text = answer_for(ClientProfile(), draft, kind="situation")

    for leak in ["спросить", "предложить", "задать", "в конце"]:
        assert leak not in text.lower(), leak
    assert "310 тысяч" in text


def test_answer_follows_consultant_formula() -> None:
    """Формула эталона: отклик → объяснение по материалам → мостик к вопросу."""
    from core.behavior import STAGE_INSTRUCTIONS, SYSTEM_PROMPT

    assert "короткий отклик" in SYSTEM_PROMPT
    assert "подведи клиента к вопросу" in SYSTEM_PROMPT
    assert "3–5 предложений" in SYSTEM_PROMPT
    assert "откликнись" in STAGE_INSTRUCTIONS["ask_debt"]
    assert "подведи к вопросу" in STAGE_INSTRUCTIONS["ask_debt"]


def test_repeated_refusal_becomes_advice() -> None:
    """Клиент переспросил «и что делать» — вместо того же абзаца бот объясняет шаги."""
    first = answer_for(ClientProfile(debt_amount=310_000), AnswerDraft(text=""), kind="situation")
    state = GraphState(question="и что делать", profile=ClientProfile(debt_amount=310_000), kind="situation")
    state.messages += [
        HumanMessage(content="310к всего"),
        AIMessage(content=first),
        HumanMessage(content="и что делать"),
    ]

    result = make_answer_node(lambda prompt: AnswerDraft())(state)

    assert "МФЦ" in str(result["answer"])
    assert first.split(".")[0] not in str(result["answer"])


def test_same_paragraph_is_not_sent_twice() -> None:
    """Тот же ответ второй раз не отправляем: просим модель сказать другое."""
    same = "Рассрочка на 310 тысяч входит в общую сумму долга вместе с остальными обязательствами."
    drafts = iter([AnswerDraft(text=same), AnswerDraft(text=same)])
    state = GraphState(question="310к всего", profile=ClientProfile(), kind="situation")
    state.messages += [AIMessage(content=same), HumanMessage(content="310к всего")]

    result = make_answer_node(lambda prompt: next(drafts))(state)

    assert same not in str(result["answer"])


def test_regalia_are_not_used_as_argument() -> None:
    """«Работаем в 63 субъектах, провели 2500 процедур» — регалии, клиенту они не аргумент."""
    draft = AnswerDraft(
        text=(
            "Регион нужен, чтобы проверить, работаем ли мы с ним. "
            "Мы работаем в 63 субъектах РФ и провели больше 2500 процедур. "
            "Подскажите, где вы прописаны?"
        )
    )

    text = answer_for(ClientProfile(), draft, kind="situation")

    assert "63" not in text
    assert "2500" not in text


def test_answer_starts_with_a_separate_response_paragraph() -> None:
    """Отклик и объяснение — разными абзацами, как в эталонном чате."""
    draft = AnswerDraft(
        text=(
            "Понял вас: остальные обязательства тянете, а рассрочка стала неподъёмной. "
            "Для процедуры нужна общая сумма долга. "
            "В неё входят кредиты, займы и налоги."
        )
    )

    text = answer_for(ClientProfile(), draft, kind="situation")

    assert "\n\n" in text
    assert text.split("\n\n")[0].startswith("Понял вас")


def test_info_names_the_real_reason_for_refusal() -> None:
    """Модель сказала «по сумме препятствий нет» и промолчала про регион — причину называет код."""
    draft = AnswerDraft(
        text=(
            "По сумме долга препятствий нет: сумма выше порога. "
            "Остаётся проверить регион, и от него зависит, сможем ли мы взяться за дело."
        )
    )
    profile = ClientProfile(debt_amount=500_000, region="Чечня")

    text = answer_for(profile, draft, kind="situation")

    assert "не проводит банкротство" in text or "не работает" in text


def test_info_answer_with_named_reason_is_kept() -> None:
    """Если причина названа, ответ модели не подменяем."""
    draft = AnswerDraft(
        text=(
            "В вашем регионе компания не проводит банкротство физлиц. "
            "Банкротство привязано к месту прописки, поэтому дело мы не возьмём."
        )
    )

    text = answer_for(ClientProfile(debt_amount=500_000, region="Чечня"), draft, kind="situation")

    assert "в вашем регионе" in text.lower()
    assert "если прописка или ситуация изменится" not in text.lower()


def test_prompt_forbids_asking_again_what_is_known() -> None:
    """Данные, которые клиент уже назвал, второй раз не спрашиваем."""
    assert "не переспрашивай" in SYSTEM_PROMPT.lower()


def test_practice_example_is_used_to_explain() -> None:
    """Пример из практики — короткой фразой, чтобы ответ не был сухим."""
    assert "пример" in SYSTEM_PROMPT.lower()


def test_instruction_about_the_system_never_reaches_the_client() -> None:
    """«Телефон и предложение записи не писать — это делает система» — служебная строка."""
    text = answer_text(
        "Телефон и предложение записи не писать — это делает система.",
        [],
        "",
        "invite",
        ask="Напишите, пожалуйста, ваш телефон и удобное время для звонка.",
    )

    assert "систем" not in text.lower()
    assert text.strip() == "Напишите, пожалуйста, ваш телефон и удобное время для звонка."


def test_invite_offers_consultation_before_asking_for_phone() -> None:
    """Фильтры пройдены — на первом ходу invite только предложение, без записи."""
    profile = ClientProfile(debt_amount=899_000, region="Ставрополь")
    draft = AnswerDraft(text="Ставрополь — работаем там, так что можно двигаться дальше.")

    first = answer_for(profile, draft, kind="situation")

    assert "Записать вас на бесплатную консультацию" in first
    assert "телефон" not in first.lower()


def test_invite_asks_phone_after_consent() -> None:
    """Клиент согласился — только теперь код спрашивает телефон и время."""
    profile = ClientProfile(debt_amount=899_000, region="Ставрополь")
    state = GraphState(question="да, давайте", profile=profile, kind="situation", previous_step="invite")

    text = cast(str, make_answer_node(lambda prompt: AnswerDraft(text="Хорошо, тогда запишу вас."))(state)["answer"])

    assert "телефон" in text.lower()


def test_stage_instructions_do_not_talk_about_the_system() -> None:
    """Модель копирует служебные оговорки дословно — в инструкциях их быть не должно."""
    for step, instruction in STAGE_INSTRUCTIONS.items():
        assert "систем" not in instruction.lower(), step


def test_time_with_a_word_is_normalized() -> None:
    """«10 утра» в записи выглядит как «10:00», а не как реплика клиента."""
    assert normalize_time("10 утра") == "10:00"
    assert normalize_time("10 вечера") == "22:00"
