"""Детектор намерений: приветствие, спасибо, прощание, вопрос (соц-ветка, решение D1).

Ветка соц-реплик остаётся правилом, а не моделью, поэтому словарь должен быть широким.
Сравнение — ТОЛЬКО полное совпадение всей нормализованной реплики: подстроки и «короткие
реплики с мусором вокруг» больше не ловятся (из-за них «пока не знаю» уходило в прощание,
а «здравствуйте, хочу списать долги» — в приветствие вместо делового разбора).

Нормализация: нижний регистр, ё→е, пунктуация → пробел, схлопывание пробелов и снятие
ведущих филлеров («ну привет» = «привет», «и снова здравствуйте» = «здравствуйте»).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from enum import Enum, auto

from ..models.turn import Turn


class Intent(Enum):
    GREETING = auto()
    THANKS = auto()
    BYE = auto()
    QUESTION = auto()


# Приветствие одним словом (сокращения и опечатки — как их реально пишут в чате).
GREETING_TOKENS: frozenset[str] = frozenset(
    {
        "привет",
        "приветик",
        "приветище",
        "прет",
        "прив",
        "пр",
        "приветствую",
        "приветствуем",
        "здравствуй",
        "здравствуйте",
        "здраствуй",
        "здраствуйте",
        "здрасьте",
        "здрасте",
        "здрасти",
        "здрасьти",
        "здрям",
        "здр",
        "зд",
        "з",
        "здоров",
        "здорово",
        "здорова",
        "здарова",
        "здоровеньки",
        "хай",
        "хайчик",
        "хаюшки",
        "хеллоу",
        "хелло",
        "hi",
        "hello",
        "hey",
        "ку",
        "йо",
        "алло",
        "ало",
        "алё",
        "ау",
    }
)

# Приветствие фразой: тоже только полным совпадением.
GREETING_PHRASES: frozenset[str] = frozenset(
    {
        "добрый день",
        "день добрый",
        "доброго дня",
        "доброе утро",
        "утро доброе",
        "с добрым утром",
        "добрый вечер",
        "вечер добрый",
        "доброго вечера",
        "доброго времени суток",
        "доброе время суток",
        "мое почтение",
        "моё почтение",
        "здравия желаю",
        "привет всем",
        "всем привет",
        "приветствую всех",
        "всех приветствую",
        "приветствую вас",
        "здравствуйте всем",
        "здравствуйте вам",
    }
)

THANKS_TOKENS: frozenset[str] = frozenset(
    {
        "спасибо",
        "спасибочки",
        "спасибки",
        "спс",
        "сб",
        "пасиб",
        "пасибо",
        "пасиба",
        "благодарю",
        "благодарствую",
        "мерси",
        "thanks",
        "thx",
        "сенкс",
        "сэнкс",
    }
)

THANKS_PHRASES: frozenset[str] = frozenset(
    {
        "спасибо большое",
        "большое спасибо",
        "спасибо огромное",
        "огромное спасибо",
        "спасибо вам",
        "спасибо тебе",
        "благодарю вас",
        "благодарю тебя",
        "спасибо за помощь",
        "спасибо за консультацию",
        "спасибо за ответ",
    }
)

# «доброй ночи» — прощание, а не приветствие (в чате так закрывают разговор).
BYE_TOKENS: frozenset[str] = frozenset(
    {
        "пока",
        "покеда",
        "поки",
        "бай",
        "бай бай",
        "бб",
        "bb",
        "bye",
        "cu",
        "до свидания",
        "до встречи",
        "до связи",
        "увидимся",
        "прощай",
        "прощайте",
        "всего доброго",
        "всего хорошего",
        "хорошего дня",
        "хорошего вечера",
        "спокойной ночи",
        "доброй ночи",
    }
)

_GREETING_WORDS: frozenset[str] = frozenset({"привет", "здравствуйте", "здравствуй", "здрасьте", "приветствую"})

# Ведущие филлеры соц-реплики смысла не меняют: «ну привет», «а привет», «и снова здравствуйте».
LEADING_FILLERS: frozenset[str] = frozenset({"ну", "и", "а", "э", "ой", "снова", "опять", "еще"})

_PUNCT = re.compile(r"[^\w\s]")


def normalize(question: str) -> str:
    """Реплика → сравнимое значение: регистр/пунктуация/ё сняты, ведущие филлеры убраны."""
    flat = _PUNCT.sub(" ", question.lower().replace("ё", "е"))
    tokens = [token for token in flat.split() if token]
    while tokens and tokens[0] in LEADING_FILLERS:
        tokens.pop(0)
    return " ".join(tokens)


class IntentDetector:
    @staticmethod
    def detect(question: str) -> Intent:
        """Соц-намерение строго по полному совпадению нормализованной реплики (D1)."""
        phrase = normalize(question)
        if not phrase:
            return Intent.QUESTION
        if phrase in BYE_TOKENS:
            return Intent.BYE
        if phrase in THANKS_TOKENS or phrase in THANKS_PHRASES:
            return Intent.THANKS
        if phrase in GREETING_TOKENS or phrase in GREETING_PHRASES:
            return Intent.GREETING
        return Intent.QUESTION

    @staticmethod
    def already_greeted(history: Sequence[Turn]) -> bool:
        """Было ли приветствие в ответах ассистента (сравнение по словам, без пунктуации)."""
        for turn in history:
            if turn.role != "assistant":
                continue
            words = set(_PUNCT.sub(" ", turn.content.lower().replace("ё", "е")).split())
            if words & _GREETING_WORDS:
                return True
        return False
