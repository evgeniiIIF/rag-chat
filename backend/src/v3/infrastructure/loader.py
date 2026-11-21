"""Загрузка документов из каталога данных: текст страниц + sha256 файла.

Обёртка над `Docx2txtLoader` (rules/architecture.md: библиотека-корень, свой код — только склейка).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from langchain_community.document_loaders import Docx2txtLoader

DOC_GLOB = "*.docx"


@dataclass(frozen=True)
class LoadedDocument:
    """Документ корпуса: имя файла, склеенный текст, хеш содержимого."""

    source: str
    text: str
    sha256: str


def load_documents(data_dir: Path) -> list[LoadedDocument]:
    """Прочитать все `.docx` каталога; пустой каталог или его отсутствие — ошибка конфигурации."""
    if not data_dir.is_dir():
        raise FileNotFoundError(f"каталог документов не найден: {data_dir}")
    paths = sorted(data_dir.glob(DOC_GLOB))
    if not paths:
        raise FileNotFoundError(f"в каталоге нет файлов {DOC_GLOB}: {data_dir}")

    documents: list[LoadedDocument] = []
    for path in paths:
        pages = Docx2txtLoader(str(path)).load()
        text = "\n\n".join(page.page_content for page in pages).strip()
        if not text:
            raise ValueError(f"документ пуст: {path.name}")
        documents.append(
            LoadedDocument(
                source=path.name,
                text=text,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
    return documents
