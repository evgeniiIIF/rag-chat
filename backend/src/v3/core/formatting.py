"""Приведение ответа к читаемому виду: пункты «- » с новой строки, пустая строка перед списком.

Модель любит писать список в одну строку («... как вы платите. - Сначала ... - Работаем ...»),
а интерфейс рисует список только когда каждый пункт начинается с новой строки. Правило живёт
здесь, а не в промпте: вёрстка не должна зависеть от настроения модели.
"""

from __future__ import annotations

import re

_SPACES = re.compile(r"[ \t]+")
_ITEM = re.compile(r"\s+(?=[-•*]\s)")
_MARK = re.compile(r"^[-•*]\s+")


def normalize_answer(text: str) -> str:
    """Разложить инлайн-пункты по строкам и отделить список пустой строкой."""
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
