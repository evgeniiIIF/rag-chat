"""Разбиение документа на фрагменты: один абзац — один фрагмент.

Документ размечен абзацами вручную, поэтому резать его по длине нельзя: фрагмент обрывается
на середине мысли, и модель получает огрызок вместо знания. Инварианты фрагмента задаёт
`domain.models.Chunk`: id = `{source}-{order:04d}`, номер абзаца настоящий, текст — абзац целиком.
Список идёт вместе со своим заголовком: пункты без заголовка бессмысленны.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from domain.models import Chunk
from infrastructure.loader import LoadedDocument

PARAGRAPH_SEP = re.compile(r"\n\s*\n")
# версия алгоритма нарезки: попадает в манифест, поэтому смена логики сама инвалидирует индекс
SPLITTER_VERSION = 3


def chunk_id(source: str, order: int) -> str:
    """Идентификатор фрагмента: имя документа + порядковый номер."""
    return f"{source}-{order:04d}"


def _is_list_item(text: str) -> bool:
    """Пункт списка — короткая строка без заглавной буквы в начале.

    «какие долги есть и перед кем;» и «есть ли аресты, приставы, суды, коллекторы.» — пункты,
    а обычный абзац начинается с заглавной и заканчивается точкой: он остаётся отдельным фрагментом.
    """
    if len(text) > 120:
        return False
    return text[:1].islower() or not text.endswith((".", "!", "?", "…"))


class Splitter:
    """Абзац — фрагмент; заголовок с двоеточием забирает свои пункты."""

    def split(self, document: LoadedDocument) -> list[Chunk]:
        """Фрагменты одного документа по порядку: только целые абзацы."""
        paragraphs = self._paragraphs(document.text)
        if not paragraphs:
            raise ValueError(f"документ не содержит текста: {document.source}")
        chunks: list[Chunk] = []
        for start, end, text in self._group_lists(paragraphs):
            order = len(chunks)
            chunks.append(
                Chunk(
                    id=chunk_id(document.source, order),
                    source=document.source,
                    order=order,
                    paragraph_start=start,
                    paragraph_end=end,
                    text=text,
                )
            )
        return chunks

    @staticmethod
    def _group_lists(paragraphs: list[tuple[int, str]]) -> list[tuple[int, int, str]]:
        """Абзац-заголовок с двоеточием забирает свои пункты: список без заголовка бессмыслен."""
        grouped: list[tuple[int, int, str]] = []
        index = 0
        while index < len(paragraphs):
            start, text = paragraphs[index]
            index += 1
            items = [text]
            if text.endswith(":"):
                while index < len(paragraphs) and _is_list_item(paragraphs[index][1]):
                    items.append(paragraphs[index][1])
                    index += 1
            grouped.append((start, paragraphs[index - 1][0], "\n".join(items)))
        return grouped

    @staticmethod
    def _paragraphs(text: str) -> list[tuple[int, str]]:
        numbered = [(number, part.strip()) for number, part in enumerate(PARAGRAPH_SEP.split(text), start=1)]
        return [(number, part) for number, part in numbered if part]


def split_documents(documents: Sequence[LoadedDocument]) -> list[Chunk]:
    """Фрагменты по всем документам корпуса."""
    splitter = Splitter()
    return [chunk for document in documents for chunk in splitter.split(document)]
