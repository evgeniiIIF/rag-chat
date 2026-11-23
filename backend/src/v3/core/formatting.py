"""Приведение текста к виду, который понимает интерфейс: абзац, список «- », **жирный**.

Вёрстка живёт здесь, а не в промпте: модель отдаёт поля схемы, код собирает из них блоки.
Здесь же чистка знаний: клиенту нельзя показывать инструкции операторам и кейсы других клиентов.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from core.behavior import (
    ASK_STEPS,
    CLIENT_TALK_RE,
    MAX_POINTS,
    OPERATOR_LEAD_RE,
    OPERATOR_RE,
    OPERATOR_SENTENCE_RE,
    POINT_MAX,
    SELF_TALK_RE,
    SHORT_STEPS,
    SUMMARY_MAX,
    booked_text,
)
from domain.profile import ClientProfile

_SPACES = re.compile(r"[ \t]+")
_SENTENCE = re.compile(r"(?<=[.!?…])\s+(?=[А-ЯЁA-Z«\"(])")
# служебные ярлыки модели в начале фразы: клиенту они не нужны
_LABEL = re.compile(r"(?i)^(?:кратко|коротко|важно|по сути)\s*:\s*")
# клиент не проходит фильтры: консультацию и запись ему не предлагаем
_CONSULT = re.compile(r"(?i)консультац\w*")
# фильтры не пройдены: объяснять можно, обещать и склонять к процедуре нельзя
_SELLING = re.compile(
    r"(?i)списыва\w*\s+(?:долг|всё|все)|спиш\w*|полностью\s+списа\w*|единственн\w+\s+(?:законн\w+\s+)?способ"
    r"|подходит\s+под\s+критери|гарантиру\w*|избавит\w*\s+от\s+долг|освободит\w*\s+от\s+долг"
    r"|вам\s+(?:точно\s+)?подходит|рекомендую\s+(?:вам\s+)?(?:пройти|запустить|начать)"
)
# на шагах сбора данных о цене не говорим, пока клиент сам не спросил
_PRICE = re.compile(r"(?i)\b(?:цен[аыуеой]?|стоимост\w*|дороже|дешевле|прайс)\b")
# задание оператору: инфинитив первым словом или сразу после слова-маркера плана
_PLAN_CUE = re.compile(
    r"(?i)^(?:не|коротко|кратко|мягко|важно|лучше|стоит|нужно|можно|без|сразу|теперь|сначала|далее|затем)$"
)
# инфинитив, но не существительное на «-сть»: «Стоимость зависит…» — это ответ клиенту
_INFINITIVE_WORD = re.compile(r"(?i)^\w+(?:(?<!с)(?<!е)ть|ться|ти)$")
# глаголы-задания: если такой инфинитив стоит в начале фразы, это заметка себе, а не речь клиенту
_TASK_VERB = re.compile(
    r"(?i)^(?:задать|задавать|спросить|спрашивать|уточнить|уточнять|упомянуть|напомнить|добавить|"
    r"объяснить|ответить|подтвердить|предложить|попросить|сформулировать|назвать|перечислить|"
    r"указать|сообщить|сказать|подчеркнуть|отметить|сохранить|записать|выяснить|узнать|посоветовать|"
    r"откликнуться|подвести|подводить|перейти|начать|продолжить|держать|избегать|поблагодарить|"
    r"поздороваться|представиться|смягчить|усилить|сделать|дать|вести|показать|пояснить)"
    r"(?:\w+)?$"
)
# план вместо ответа: «Ответ клиенту …: подтверждение, разбор и реструктуризация»
# инструктивный зачин модели, который нельзя показывать клиенту
_INSTR_HEAD = re.compile(
    r"(?i)^\s*(?:нужн[аоы]|нужно|ответь|ответить|спроси|спросить|уточни|уточнить|попроси|попросить|"
    r"подтверди|подтвердить|разбери|разобрать|объясни|объяснить|клиент\s+(?:спрашивает|указал|говорит|хочет))\b"
)
_PLAN_HEAD = re.compile(
    r"(?i)^\s*(?:ответ|реплика|резюме|итог|вывод|план|задача|цель|шаг|стратегия|логика|"
    r"подтверждение|разбор|что\s+не\s+списывается)\b[^.!?]{0,90}:"
)
# заметка модели о клиенте вместо ответа: «Ситуация: …», «Цель — …»
_NOTE_HEAD = re.compile(
    r"(?i)^\s*(?:ситуация|клиент|клиентка|данные|факты?|цель|задача|вводные|контекст|профиль|"
    r"запрос\s+клиента|что\s+известно)\b[^.!?]{0,120}[:—]"
)
# служебные пометки из промпта: клиент читает ответ, а не состояние графа
# остатки плана модели: «Упомянуто внесудебное банкротство», «Завершение — можно написать снова»
_PLAN_RESIDUE = re.compile(
    r"(?i)^\s*(?:упомянут\w*|отмечен\w*|указан\w*|завершени\w*|итог\w*\s*—"
    r"|без\s+(?:вопрос|списк|предложени|пересказ|извинени|гаранти)\w*"
    r"|ответ\w*\s+(?:с|—|–|-|:)|ответ\w*\s+(?:клиенту|про|по|для)|текст\s+ответа"
    r"|клиенту\s+(?:сказать|ответить|объяснить|предложить)"
    r"|предложени\w*\s+(?:из|на)\s+\d)"
)
_INTERNAL_NOTE = re.compile(
    r"(?i)^\s*(?:клиент|клиентка)\b"
    r"|фильтр\w*\s+(?:пройден\w*|не\s+пройден\w*)"
    r"|состояние\s+фильтров|что\s+известно\s+о\s+клиенте"
    r"|(?:регион|сумма|долг)\w*(?:\s+долга)?\s+(?:пока\s+)?неизвест\w*"
    r"|пока\s+не\s+(?:указан|известн)\w*|регион\s+не\s+указан\w*"
    r"|отказ\s+по\s+(?:сумме|региону)|ниже\s+порога|порога\s+\d"
    r"|предложить\s+(?:самостоятельн|альтернатив)\w*|оставить\s+возможность\s+вернуться"
    r"|(?:в|под)\s+конце\s+(?:задать|спросить|уточнить|упомянуть|добавить|напомнить)"
    r"|(?:задать|задаётся|задай|задавайте|задать)\s+вопрос|вопрос\w*\s+(?:об|о|про)\s+"
    r"|напомнить\s+о\s+вопросе"
    # заметка о уже сделанном: «Извинился за лишние детали, объяснил, что…» — это не речь клиенту
    r"|^\s*(?:я\s+)?(?:извинил\w*|объяснил\w*|подвёл\w*|подвел\w*|уточнил\w*|назвал\w*|"
    r"отметил\w*|добавил\w*|сказал\w*|ответил\w*|предложил\w*|спросил\w*|написал\w*)\b"
    # обещание действия, которого не будет: «уточню и вернусь с ответом»
    r"|\b(?:уточню|проверю|уточним|проверим)\b|вернусь\s+с\s+ответом|передам\s+"
    # описание работы системы вместо речи клиенту: «это делает система», «сам не пиши»
    r"|это\s+дела\w*\s+система|зада[её]т\s+система|система\s+(?:сама|зада|собира)\w*"
    r"|\bне\s+пиши\b|сам\s+(?:его|их|её|ее)?\s*не\s+пиши"
)
# регалии компании: «работаем в 63 субъектах», «2500 процедур» — не аргумент в ответе клиенту
_REGALIA = re.compile(
    r"(?i)\d+\s*(?:субъект|регион)\w*|\d+\s*(?:процедур|дел|клиент)\w*|\d[\d\s.,]*\s*млрд"
    r"|не\s+проиграли\s+ни\s+одного"
)
# модель говорит о клиенте в третьем лице: клиент читает обращение к себе
_THIRD_PERSON = re.compile(r"(?i)\b(?:он|его|ему|у\s+него|в\s+его|о\s+нём)\b")
# благодарность за то, чего клиент не говорил («спасибо, что подробно всё рассказали»)
_GRATITUDE = re.compile(r"(?i)^\s*(?:спасибо|благодарю)\b")
# заметка модели вместо ответа: «Ответ клиенту…», «Клиент заметил…», «Один вопрос в конце:»
_META = re.compile(
    r"(?i)\bответ\s+клиент\w*|\bклиент\w*\s+(?:заметил\w*|спрашива\w*|указал\w*|говорит|хочет|не\s+проходит)\b"
    r"|\bодин\s+вопрос\s*(?:в\s+конце)?\s*[:—-]"
)
# следы источника, которые модель иногда проговаривает вслух
_SOURCE_REF = re.compile(
    r"(?i)\b(?:согласно|по|из|во|со|в)\s+(?:предоставленн\w+\s+)?"
    r"(?:документ\w*|фрагмент\w*|источник\w*|материал\w*|баз\w+\s+знаний|контекст\w*)\b[ ,:—-]*"
)
_BRACKET_ID = re.compile(r"\[[^\]]*?-\d{4}\]\s*")
# то, что клиент должен увидеть сразу: суммы, телефон и время звонка
_DETAIL = re.compile(
    r"(?<!\*)(?:"
    r"\b\d[\d\s\u00a0]*(?:₽|руб\w*|тыс\w*|млн\w*|миллион\w*|миллиард\w*)"
    r"|\+?\d[\d\s()\-]{8,}\d"
    r"|\b\d{1,2}[:.]\d{2}\b"
    r")"
)


def _capitalize_first(text: str) -> str:
    for index, char in enumerate(text):
        if char.isalpha():
            return text[:index] + char.upper() + text[index + 1 :]
    return text


def strip_source_refs(text: str) -> str:
    """Убрать упоминания документа, фрагмента, источника: клиент видит живого консультанта."""
    # сначала ссылки на абзацы, потом слова-источники: иначе запятая от ссылки останется в начале
    cleaned = _SOURCE_REF.sub("", _BRACKET_ID.sub("", text))
    cleaned = _SPACES.sub(" ", cleaned).strip(" ,;:")
    if cleaned == text:  # ссылок не было — текст не трогаем
        return text
    return _capitalize_first(cleaned) if cleaned else text


def highlight_details(text: str) -> str:
    """Выделить сумму, номер и время жирным: фронтенд рисует **…** акцентом."""
    if "**" in text:  # модель уже что-то выделила — не ломаем её разметку
        return text
    return _DETAIL.sub(lambda match: f"**{match.group(0).strip()}**", text)


def _instruction(sentence: str) -> bool:
    """Фраза написана как задание («Спросить…», «Не давить…»), а не как ответ клиенту."""
    words = sentence.split()
    if not words:
        return True
    if words[0][:1].islower():  # обрывок мысли после вырезанного начала
        return True
    if _INFINITIVE_WORD.match(words[0].strip(":;,.-—–")):
        return True
    # «Не давить…», «Сразу обозначить…», «Коротко объяснить…», «Нужно коротко объяснить…» —
    # инфинитив среди первых трёх слов после маркера плана
    if bool(_PLAN_CUE.match(words[0])) and any(_INFINITIVE_WORD.match(w) for w in words[1:5]):
        return True
    # «В конце задать вопрос…», «Далее спросить про сумму», «Затем предложить консультацию»:
    # глагол-задание в начале фразы — это инструкция себе, а не ответ клиенту
    if any(_TASK_VERB.match(w.strip(":;,.-—–")) for w in words[:4]):
        return True
    # «Нужно коротко откликнуться, затем объяснить и подвести к вопросу» — два задания в одной фразе
    return sum(1 for w in words if _INFINITIVE_WORD.match(w.strip(":;,.-—–"))) >= 2


# короткий тёплый отклик: «Понял вас.», «Понимаю.», «Это нормально.» — клиенту нужен, в отличие от мусора
_WARM_ACK = re.compile(
    r"(?i)^\s*(?:понял|понимаю|слышу|вижу|согласен|конечно|хорошо|разумеется|"
    r"это\s+нормально|сомнения|не\s+страшно|спасибо)\b"
)


# на сборе фильтров о цене не говорим, пока клиент сам не спросил; на invite цена — часть предложения
_PRICE_GUARD_STEPS = ASK_STEPS - {"invite"}


def _client_voice(text: str, step: str = "") -> str:
    """Убрать рассуждения модели о клиенте и о себе: клиент читает только обращённый к нему ответ."""
    sentences = _SENTENCE.split(" ".join(text.split()))
    # обрывки после сокращения («800 тыс. — подходит») и рассуждения модели клиенту не нужны
    return " ".join(
        _LABEL.sub("", sentence)
        for sentence in sentences
        if (len(sentence.strip()) >= 12 or _WARM_ACK.match(sentence))
        and sentence.strip()[0] not in "—–-"
        and not SELF_TALK_RE.search(sentence)
        and not _instruction(sentence)
        and not _PLAN_HEAD.search(sentence)
        and not _INSTR_HEAD.search(sentence)
        and not _NOTE_HEAD.search(sentence)
        and not _INTERNAL_NOTE.search(sentence)
        and not _PLAN_RESIDUE.search(sentence)
        and not (step == "info" and "?" in sentence)
        and not _META.search(sentence)
        and not _THIRD_PERSON.search(sentence)
        and not _GRATITUDE.search(sentence)
        and not _REGALIA.search(sentence)
        and not (step == "info" and (_CONSULT.search(sentence) or _SELLING.search(sentence)))
        and not (step in _PRICE_GUARD_STEPS and _PRICE.search(sentence))
    ).strip()


_ENUM_ITEMS = 3  # перечень в ответе: больше трёх наименований клиент не удерживает


def _second_paragraph(head: str, step: str) -> str:
    """Отклик отдельным абзацем, объяснение — следующим: так ответ читается, как речь консультанта."""
    if step not in {"ask_debt", "ask_region", "invite", "rag"}:
        return head
    sentences = [sentence.strip() for sentence in _SENTENCE.split(head) if sentence.strip()]
    if len(sentences) < 3:
        return head
    return f"{sentences[0]}\n\n{' '.join(sentences[1:])}"


def _trim_enumeration(text: str) -> str:
    """Длинный каталог из знаний («кредиты, карты, микрозаймы, рассрочки, автокредиты, ЖКХ, налоги…»)
    сжимаем до трёх наименований: ответ должен быть по теме, а не выпиской из документа."""
    out: list[str] = []
    for sentence in _SENTENCE.split(text):
        parts = sentence.split(", ")
        if len(parts) > 7 and len(sentence) > 140:  # явный каталог, а не перечисление в речи
            sentence = ", ".join(parts[:_ENUM_ITEMS]) + " и другие обязательства."
        out.append(sentence)
    return " ".join(out)


def _shorten(text: str, limit: int = POINT_MAX) -> str:
    """Пункт — одна короткая мысль: длинный абзац из знаний обрезаем по границе фразы."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for separator in (". ", "; ", ", "):
        position = cut.rfind(separator)
        if position > limit // 3:
            return cut[:position].rstrip(" ,;—-") + "."
    return cut[: cut.rfind(" ")].rstrip(" ,;—-") + "."


def _words(text: str) -> str:
    """Текст без пунктуации и регистра: чтобы поймать один и тот же смысл в разных полях."""
    return _SPACES.sub(" ", re.sub(r"[^\w\s]", " ", text.casefold())).strip()


def _stems(text: str) -> set[str]:
    """Грубые основы слов: «рассрочка/рассрочкой» — одно и то же."""
    return {word[:5] for word in re.findall(r"\w+", text.casefold()) if len(word) > 3}


def _similar(one: str, other: str) -> bool:
    """Одна и та же мысль другими словами: больше половины основ совпало."""
    left, right = _stems(one), _stems(other)
    return bool(left and right) and len(left & right) / len(left | right) >= 0.5


def _repeat(one: str, other: str) -> bool:
    """Считаем повтором, когда фраза совпадает целиком или один текст вложен в другой."""
    left, right = _words(one), _words(other)
    if not left or not right:
        return False
    return left == right or left in right or right in left


def _drop_tail_question(head: str, tail: str) -> str:
    """Убираем из сути вопрос, который код задаёт сам, но объяснение клиенту оставляем."""
    sentences = [part.strip() for part in _SENTENCE.split(head) if part.strip()]
    while len(sentences) > 1 and sentences[-1].rstrip().endswith("?"):
        if not _repeat(sentences[-1], tail):
            break
        sentences.pop()
    return " ".join(sentences)


def answer_text(
    summary: str,
    points: Iterable[str],
    question: str,
    step: str = "",
    profile: ClientProfile | None = None,
    ask: str = "",
    said: Iterable[str] = (),
) -> str:
    """Текст ответа из полей схемы: суть абзацем, пояснения списком, вопрос отдельным блоком.

    Одна мысль — один раз: поле, которое повторяет суть или вопрос, отбрасывается. На шагах сбора
    данных остаётся только вопрос, иначе модель дублирует его в сути и в пунктах.
    """
    head = _shorten(_trim_enumeration(dedupe_sentences(_client_voice(strip_source_refs(summary), step))), SUMMARY_MAX)
    if step in SHORT_STEPS:  # здесь нужна одна живая фраза, а не абзац
        head = _SENTENCE.split(head)[0].strip()
        if head.endswith("?"):  # вопрос задаёт код: второй вопрос в одном ответе — дубль
            head = ""
    if step == "booked" and profile is not None:  # запись подтверждаем ровно тем, что сохранили
        return highlight_details(booked_text(profile, head))
    # вопрос шага задаёт код: его формулировка не зависит от модели и всегда доходит до клиента
    own = only_question(strip_source_refs(question))
    tail = ask or own
    if step == "info":  # клиент не проходит фильтр: объясняем и закрываем разговор, вопросов больше нет
        tail = ""
    if head and tail:  # вопрос модели совпал с вопросом шага — выкидываем только сам вопрос
        head = _drop_tail_question(head, tail)
        if head and _repeat(head, tail):
            tail = ""  # вопрос уже прозвучал внутри сути, второй раз не задаём
    # шаги сбора данных: клиенту ничего не объясняем, остаётся реплика и вопрос
    if step in SHORT_STEPS:
        points = []
    items = [_shorten(_client_voice(strip_source_refs(point), step)) for point in points if point.strip()]
    items = [item for item in items if item]
    items = [item for item in items if not _repeat(item, head) and not _repeat(item, tail)]
    # клиент это уже слышал в прошлых ответах — второй раз не повторяем
    items = [item for item in items if not any(_similar(item, old) for old in said)]
    unique: list[str] = []
    for item in items:
        if not any(_repeat(item, kept) for kept in unique):
            unique.append(item)
    items = unique[:MAX_POINTS]
    head = _second_paragraph(head, step)  # отклик отдельным абзацем — уже после чистки сути
    blocks: list[str] = []
    if head:
        blocks.append(highlight_details(head))
    if items:
        blocks.append("\n".join(f"- {highlight_details(item)}" for item in items))
    if tail:
        blocks.append(highlight_details(tail))
    return "\n\n".join(blocks)


def only_question(text: str) -> str:
    """Только сам вопрос: обоснования и пояснения после него клиенту не нужны."""
    sentences = _SENTENCE.split(" ".join(text.split()))
    kept: list[str] = []
    for sentence in sentences:
        kept.append(sentence.strip("-•* "))
        if sentence.rstrip().endswith("?"):
            return " ".join(kept).strip()
    return ""


def parse_reply(text: str) -> tuple[str, list[str], str]:
    """Текст модели → поля схемы: строки с «- » пункты, последний абзац с «?» вопрос."""
    head: list[str] = []
    points: list[str] = []
    tail: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("-", "•", "*")):
            points.append(line.lstrip("-•* ").strip())
        elif points:
            tail.append(line)
        else:
            head.append(line)
    question = ""
    if tail:
        merged = " ".join(tail)
        if "?" in merged:
            question = merged
        else:
            head.extend(tail)
    return " ".join(head).strip(), points, question


def split_question(text: str) -> tuple[str, str]:
    """Текст ответа → консультация и вопрос: последний абзац с «?» — это вопрос клиенту.

    Вопрос уходит отдельным полем контракта, чтобы интерфейс показал его плашкой,
    а не последним предложением в куче текста.
    """
    blocks = [block.strip() for block in text.strip().split("\n\n") if block.strip()]
    if len(blocks) > 1 and "?" in blocks[-1] and not blocks[-1].startswith("- "):
        return "\n\n".join(blocks[:-1]), blocks[-1]
    return text.strip(), ""


_OPERATOR_HEADING_RE = re.compile(
    r"(?i)^(.*?)\s+(?:можно|стоит|лучше|нужно)\s+(?:объяснять|говорить|рассказывать|использовать)"
    r"[^:]{0,24}:\s*$"
)


def _neutral_heading(sentence: str) -> str:
    """Служебный зачин «Этапы процедуры можно объяснять коротко:» → «Этапы процедуры:»."""
    match = _OPERATOR_HEADING_RE.match(sentence.strip())
    if not match:
        return sentence
    return f"{match.group(1).strip(' :—-')}:"


def knowledge_text(text: str, topic: str = "") -> str:
    """Знания для клиента: без инструкций операторам, только то, о чём спросили.

    Режем по предложениям, а не абзацем целиком: в одном абзаце рядом нужный факт и соседняя ветка
    (спросили про долг — приезжает имущество супруга и дарение). Если тема реплики известна,
    оставляем предложения с общими словами, иначе — первое предложение абзаца.
    """
    lines = text.splitlines()
    if lines:  # служебный зачин-инструкция меняем на нейтральный заголовок, список сохраняем
        lines[0] = _neutral_heading(lines[0])
    flat = " ".join("\n".join(lines).split())
    if not flat:
        return ""
    if not flat[0].isupper():  # обрывок с середины фразы: начало кейса потеряно при нарезке
        return ""
    sentences = _SENTENCE.split(flat)
    if OPERATOR_RE.search(sentences[0]):  # абзац целиком написан для операторов, клиенту не показываем
        return ""
    sentences[0] = OPERATOR_LEAD_RE.sub("", sentences[0])  # «правильно объяснять так:» — зачин для оператора
    kept: list[str] = []
    for sentence in sentences:
        if OPERATOR_RE.search(sentence) or OPERATOR_SENTENCE_RE.search(sentence):
            continue
        if CLIENT_TALK_RE.search(sentence):
            continue
        kept.append(sentence)
    if topic.strip() and len(kept) > 1:  # отбираем по теме реплики, чтобы не тянуть соседние ветки
        stems = _stems(topic)
        relevant = [sentence for sentence in kept if _stems(sentence) & stems]
        kept = relevant or kept[:1]
    result = " ".join(kept).strip()
    return result if len(result) >= 40 else ""


def normalize_answer(text: str) -> str:
    """Привести ответ модели к вёрстке интерфейса: абзацы и список «- »."""
    cleaned = strip_source_refs(text)
    cleaned = re.sub(r"\s+-\s+", "\n- ", cleaned)
    lines = [line.strip() for line in cleaned.splitlines()]
    blocks: list[str] = []
    bullets: list[str] = []
    for line in lines:
        if not line:
            if bullets:
                blocks.append("\n".join(bullets))
                bullets = []
            continue
        if line.startswith(("-", "•", "*")):
            bullets.append("- " + line.lstrip("-•* ").strip())
        else:
            if bullets:
                blocks.append("\n".join(bullets))
                bullets = []
            blocks.append(line)
    if bullets:
        blocks.append("\n".join(bullets))
    return "\n\n".join(block for block in blocks if block).strip()


def enforce_style(text: str, step: str = "") -> str:
    """Финальная чистка: без заметок модели, инструкций и третьего лица."""
    return _client_voice(strip_source_refs(text), step)


def dedupe_sentences(text: str) -> str:
    """Одна мысль один раз: фразу, повторяющую уже сказанное, выбрасываем."""
    kept: list[str] = []
    for sentence in _SENTENCE.split(" ".join(text.split())):
        clean = sentence.strip()
        if clean and not any(_repeat(clean, old) or _similar(clean, old) for old in kept):
            kept.append(clean)
    return " ".join(kept)


def clean_note(text: str, step: str = "") -> str:
    """Оговорка клиенту: без ссылок на источник и служебных заметок модели."""
    cleaned = _client_voice(strip_source_refs(text), step)
    return cleaned


def build_blocks(
    body: str,
    note: str = "",
    question: str = "",
) -> list[dict[str, Any]]:
    """Ответ блоками для интерфейса: суть, пояснения списком, оговорка, вопрос.

    Плашки «фактов» здесь нет: любая подпись вида «из контекста» выдаёт клиенту источник.
    """
    paragraphs = [part.strip() for part in body.split("\n\n") if part.strip()]
    last = paragraphs[-1] if paragraphs else ""
    if not question and last and not last.startswith("- ") and last.rstrip("* ").endswith("?"):
        question = paragraphs.pop()  # на шагах сбора данных ответ состоит из одного вопроса
    blocks: list[dict[str, Any]] = []
    lead_done = False
    for part in paragraphs:
        if part.startswith("- "):
            items = [line[2:].strip() for line in part.splitlines() if line.startswith("- ")]
            blocks.append({"type": "list", "items": items})
            continue
        blocks.append({"type": "text" if lead_done else "lead", "text": part})
        lead_done = True
    if note:
        blocks.append({"type": "note", "text": highlight_details(note)})
    if question:
        blocks.append({"type": "question", "text": question})
    return blocks


def booked_blocks() -> list[dict[str, Any]]:
    """Подтверждение записи блоками: суть и список того, что подготовить к консультации."""
    return [
        {"type": "lead", "text": "Записал вас на консультацию: юрист сам позвонит в назначенное время."},
        {
            "type": "list",
            "title": "Что подготовить",
            "items": ["Паспорт", "Список кредиторов с суммами", "Справки о доходах"],
        },
    ]
