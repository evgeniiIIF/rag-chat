"""Разбиение документа на фрагменты: упаковка абзацев + RecursiveCharacterTextSplitter.

Инварианты фрагмента задаёт `domain.models.Chunk`: id = `{source}-{order:04d}`,
границы абзацев реальные (из исходного текста), текст непустой и не длиннее `chunk_size`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from langchain_text_splitters import RecursiveCharacterTextSplitter

from domain.models import Chunk
from infrastructure.loader import LoadedDocument

PARAGRAPH_SEP = re.compile(r"\n\s*\n")
# версия алгоритма нарезки: попадает в манифест, поэтому смена логики сама инвалидирует индекс
SPLITTER_VERSION = 2


def chunk_id(source: str, order: int) -> str:
    """Идентификатор фрагмента: имя документа + порядковый номер."""
    return f"{source}-{order:04d}"


class Splitter:
    """Делит документ на фрагменты, сохраняя номера абзацев.

    Короткие абзацы пакуются вместе, пока влезают в `chunk_size`; абзац длиннее
    `chunk_size` режется коробочным сплиттером (с перекрытием `chunk_overlap`).
    """

    def __init__(self, *, chunk_size: int, chunk_overlap: int) -> None:
        self._chunk_size = chunk_size
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def split(self, document: LoadedDocument) -> list[Chunk]:
        """Фрагменты одного документа по порядку."""
        paragraphs = self._paragraphs(document.text)
        if not paragraphs:
            raise ValueError(f"документ не содержит текста: {document.source}")

        chunks: list[Chunk] = []
        buffer: list[str] = []
        start = 0
        end = 0

        for number, text in paragraphs:
            if len(text) > self._chunk_size:
                if buffer:
                    chunks.append(self._chunk(document, len(chunks), start, end, "\n\n".join(buffer)))
                    buffer = []
                for piece in self._splitter.split_text(text):
                    chunks.append(self._chunk(document, len(chunks), number, number, piece))
                start = end = 0  # следующий буфер начинается заново, а не с абзаца прошлого фрагмента
                continue

            candidate = "\n\n".join([*buffer, text])
            if buffer and len(candidate) > self._chunk_size:
                chunks.append(self._chunk(document, len(chunks), start, end, "\n\n".join(buffer)))
                buffer = [text]
                start = end = number
            else:
                if not buffer:
                    start = number
                buffer.append(text)
                end = number

        if buffer:
            chunks.append(self._chunk(document, len(chunks), start, end, "\n\n".join(buffer)))
        return chunks

    def _chunk(self, document: LoadedDocument, order: int, start: int, end: int, text: str) -> Chunk:
        return Chunk(
            id=chunk_id(document.source, order),
            source=document.source,
            order=order,
            paragraph_start=start,
            paragraph_end=end,
            text=text,
        )

    @staticmethod
    def _paragraphs(text: str) -> list[tuple[int, str]]:
        numbered = [(number, part.strip()) for number, part in enumerate(PARAGRAPH_SEP.split(text), start=1)]
        return [(number, part) for number, part in numbered if part]


def split_documents(documents: Sequence[LoadedDocument], *, chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    """Фрагменты по всем документам корпуса."""
    splitter = Splitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return [chunk for document in documents for chunk in splitter.split(document)]
