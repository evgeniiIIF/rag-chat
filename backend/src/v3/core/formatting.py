"""Приведение ответа к читаемому виду: пункты «- » с новой строки, пустая строка перед списком.

Модель любит писать список в одну строку («... как вы платите. - Сначала ... - Работаем ...»),
а интерфейс рисует список только когда каждый пункт начинается с новой строки. Правило живёт
здесь, а не в промпте: вёрстка не должна зависеть от настроения модели.
"""

from __future__ import annotations

import re

_SPACES = re.compile(r"[ \t]+")
# следы источника, которые модель иногда проговаривает вслух
_SOURCE_REF = re.compile(
    r"(?i)\b(?:согласно|по|из|во|со|в)\s+(?:предоставленн\w+\s+)?"
    r"(?:документ\w*|фрагмент\w*|источник\w*|материал\w*|баз\w+\s+знаний|контекст\w*)\b[ ,:—-]*"
)
_BRACKET_ID = re.compile(r"\[[^\]]*?-\d{4}\]\s*")
_ITEM = re.compile(r"\s+(?=[-•*]\s)")
_MARK = re.compile(r"^[-•*]\s+")


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


def normalize_answer(text: str) -> str:
    """Убрать следы источника, разложить инлайн-пункты по строкам и отделить список пустой строкой."""
    text = strip_source_refs(text)
    blocks: list[str] = []
    for block in text.strip().split("\n\n"):
        flat = _SPACES.sub(" ", block.replace("\n", " ")).strip()
        if not flat:
            continue
        parts = _ITEM.split(flat)
        head = parts[0].strip()
        items = [_MARK.sub("", part).strip() for part in parts[1:]]
        if _MARK.match(head):  # блок начался сразу с пункта списка
            items.insert(0, _MARK.sub("", head).strip())
            head = ""
        items = [item for item in items if item]
        if not items:
            blocks.append(flat)
            continue
        listing = "\n".join(f"- {item}" for item in items)
        blocks.append(f"{head}\n\n{listing}" if head else listing)
    return "\n\n".join(blocks)
