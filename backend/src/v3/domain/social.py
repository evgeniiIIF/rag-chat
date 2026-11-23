"""Соц-реплики: распознаются правилом, отвечаются готовым текстом из `core/behavior.py`."""

from __future__ import annotations

import re

_WORDS: frozenset[str] = frozenset(
    {
        "привет",
        "приветик",
        "прет",
        "прив",
        "приветствую",
        "здравствуй",
        "здравствуйте",
        "здрасьте",
        "здрасте",
        "здорово",
        "здоров",
        "хай",
        "ку",
        "йо",
        "алло",
        "hi",
        "hello",
        "hey",
    }
)
_PHRASES: frozenset[str] = frozenset(
    {
        "добрый день",
        "доброе утро",
        "добрый вечер",
        "доброго времени суток",
        "доброго дня",
        "доброго вечера",
        "всем привет",
        "привет всем",
    }
)
_THANKS: frozenset[str] = frozenset({"спасибо", "спс", "благодарю", "пасибо", "thanks", "thank you"})
_BYE: frozenset[str] = frozenset(
    {"пока", "бай", "прощай", "досвидания", "до свидания", "всего доброго", "до встречи", "bye"}
)
_CLEAN = re.compile(r"[^a-zа-яё\s]+")


def _flat(text: str) -> str:
    return " ".join(_CLEAN.sub(" ", text.casefold()).split())


def is_greeting(text: str) -> bool:
    """Реплика — только приветствие, без вопроса и данных."""
    flat = _flat(text)
    if not flat:
        return False
    if flat in _PHRASES:
        return True
    words = flat.split()
    if not any(word in _WORDS for word in words):
        return False
    # «привет, у меня долг 500к» — не приветствие, а начало разговора по делу
    return len(words) <= 3


def social_kind(text: str) -> str | None:
    """Тип соц-реплики: greeting | thanks | bye, иначе None — разговор деловой."""
    flat = _flat(text)
    if not flat or len(flat.split()) > 4:
        return None
    if flat in _THANKS or flat in {"спасибо большое", "большое спасибо", "спасибо за ответ"}:
        return "thanks"
    if flat in _BYE or flat in {"ну пока", "ладно пока", "всем пока"}:
        return "bye"
    return "greeting" if is_greeting(text) else None
