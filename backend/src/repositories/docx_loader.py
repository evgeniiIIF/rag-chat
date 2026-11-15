"""Loader .docx: сохранение paragraph_span + дробление длинных строк.

Word часто хранит текст одним абзацем с \n внутри. Поэтому:
1) делим абзац по \n;
2) длинные строки (>MAX_LINE_CHARS) дробим по предложениям с перекрытием OVERLAP.
Все получившиеся чанки наследуют span родительского абзаца.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from docx import Document as DocxDocument

from ..models.chunk import Chunk, ParagraphSpan

MAX_LINE_CHARS: int = 300
OVERLAP: int = 50
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def split_long_line(line: str, max_chars: int = MAX_LINE_CHARS, overlap: int = OVERLAP) -> list[str]:
    """Делит длинную строку по предложениям, склеивая до max_chars с перекрытием."""
    if len(line) <= max_chars:
        return [line]
    sentences = [s.strip() for s in _SENT_SPLIT.split(line) if s.strip()]
    if len(sentences) <= 1:
        # нет точек — режем по словам
        return _split_by_words(line, max_chars, overlap)
    chunks: list[str] = []
    buf = ""
    for sent in sentences:
        candidate = (buf + " " + sent).strip() if buf else sent
        if len(candidate) <= max_chars:
            buf = candidate
            continue
        if buf:
            chunks.append(buf)
            tail = buf[-overlap:] if overlap > 0 else ""
            buf = (tail + " " + sent).strip() if tail else sent
        else:
            buf = sent
        while len(buf) > max_chars:
            chunks.append(buf[:max_chars])
            buf = buf[max_chars - overlap :]
    if buf:
        chunks.append(buf)
    return chunks


def _split_by_words(line: str, max_chars: int, overlap: int) -> list[str]:
    words = line.split()
    chunks: list[str] = []
    buf: list[str] = []
    for w in words:
        # одно слово длиннее max -> режем по max_chars, без overlap внутри слова
        if len(w) > max_chars:
            if buf:
                chunks.append(" ".join(buf))
                buf = []
            for i in range(0, len(w), max_chars):
                chunks.append(w[i : i + max_chars])
            continue
        candidate = (" ".join([*buf, w])) if buf else w
        if len(candidate) <= max_chars:
            buf.append(w)
            continue
        if buf:
            chunks.append(" ".join(buf))
            tail_chars = " ".join(buf)[-overlap:] if overlap > 0 else ""
            buf = [*tail_chars.split(), w] if tail_chars else [w]
        else:
            chunks.append(w)
            buf = []
    if buf:
        chunks.append(" ".join(buf))
    return chunks


class DocxParagraphLoader:
    """Загружает .docx, отдаёт чанки с paragraph_span (1-based)."""

    def load(self, path: Path) -> list[Chunk]:
        if path.suffix.lower() != ".docx":
            raise ValueError(f"Ожидался .docx, получен: {path.suffix}")
        if not path.is_file():
            raise FileNotFoundError(path)

        document = DocxDocument(str(path))
        chunks: list[Chunk] = []
        for index, paragraph in enumerate(document.paragraphs, start=1):
            raw = paragraph.text
            if not raw.strip():
                continue
            lines = [ln.strip() for ln in raw.splitlines()]
            for line in lines:
                if not line:
                    continue
                for piece in split_long_line(line):
                    piece = piece.strip()
                    if not piece:
                        continue
                    chunks.append(
                        Chunk(
                            source=path.name,
                            text=piece,
                            span=ParagraphSpan(start=index, end=index),
                        )
                    )
        return chunks


def merge_adjacent(chunks: Iterable[Chunk]) -> list[Chunk]:
    """Склеивает подряд идущие абзацы одного документа (если нужен крупный чанк)."""
    merged: list[Chunk] = []
    for chunk in chunks:
        if merged and _touches(merged[-1], chunk):
            last = merged[-1]
            merged[-1] = Chunk(
                source=last.source,
                text=f"{last.text}\n\n{chunk.text}",
                span=ParagraphSpan(start=last.span.start, end=chunk.span.end),
            )
        else:
            merged.append(chunk)
    return merged


def _touches(previous: Chunk, current: Chunk) -> bool:
    return previous.source == current.source and previous.span.end + 1 == current.span.start
