"""Индекс корпуса: манифест sha256 решает, переиспользовать индекс или строить заново.

SC-005 спеки: при неизменных документах повторный старт не перестраивает индекс.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path

from core.config import Settings
from core.formatting import knowledge_text
from domain.models import Chunk, RetrievedChunk
from infrastructure.artifacts import read_json, read_jsonl, write_chunks_markdown, write_json, write_jsonl
from infrastructure.index import HybridRetriever, build_index
from infrastructure.loader import LoadedDocument, load_documents
from infrastructure.splitter import SPLITTER_VERSION, split_documents

logger = logging.getLogger(__name__)

INDEX_STAGE = "index"
MANIFEST_NAME = "manifest.json"
CHUNKS_NAME = "chunks.jsonl"

Loader = Callable[[Path], list[LoadedDocument]]
SplitterFn = Callable[..., list[Chunk]]
IndexFactory = Callable[..., HybridRetriever]


def build_manifest(documents: Sequence[LoadedDocument], settings: Settings) -> dict[str, object]:
    """Отпечаток корпуса: sha256 документов + параметры чанкинга и эмбеддингов."""
    return {
        "documents": [{"source": document.source, "sha256": document.sha256} for document in documents],
        "splitter_version": SPLITTER_VERSION,
        "chunking": "paragraph",
        "embedding_model": settings.embedding_model,
    }


class IndexService:
    """Владелец поиска по корпусу: строит индекс один раз и отдаёт `search`."""

    def __init__(
        self,
        settings: Settings,
        *,
        loader: Loader = load_documents,
        split: SplitterFn = split_documents,
        index_factory: IndexFactory = build_index,
    ) -> None:
        self._settings = settings
        self._loader = loader
        self._split = split
        self._index_factory = index_factory
        self._chunks: list[Chunk] = []
        self._retriever: HybridRetriever | None = None

    @property
    def chunks(self) -> list[Chunk]:
        """Фрагменты корпуса (после `ensure_index`)."""
        return list(self._chunks)

    def ensure_index(self) -> None:
        """Прочитать корпус и подготовить поиск (перестройка — только при изменении манифеста)."""
        documents = self._loader(self._settings.data_dir)
        manifest = build_manifest(documents, self._settings)
        index_dir = self._settings.artifacts_dir / INDEX_STAGE
        manifest_path = index_dir / MANIFEST_NAME
        chunks_path = index_dir / CHUNKS_NAME

        stored = self._stored_chunks(manifest_path, chunks_path, manifest)
        if stored is not None:
            self._chunks = stored
            self._retriever = self._index_factory(stored, self._settings, rebuild=False)
            self._write_snapshot()
            return

        # служебные абзацы (инструкции операторам) не должны занимать места в поиске
        split_chunks = self._split(documents)
        chunks = [chunk for chunk in split_chunks if knowledge_text(chunk.text)]
        write_jsonl(chunks_path, [chunk.model_dump(mode="json") for chunk in chunks])
        write_json(manifest_path, manifest)
        self._chunks = chunks
        self._retriever = self._index_factory(chunks, self._settings, rebuild=True)
        self._write_snapshot()

    def search(self, question: str, k: int) -> list[RetrievedChunk]:
        """Гибридный поиск по готовому индексу."""
        if self._retriever is None:
            raise RuntimeError("индекс не построен: сначала ensure_index()")
        return self._retriever.search(question, k)

    def _write_snapshot(self) -> None:
        """Обновить читаемый снимок нарезки (`settings.chunks_doc`); сбой записи не ломает старт."""
        try:
            write_chunks_markdown(self._chunks, self._settings.chunks_doc)
        except OSError as error:  # read-only каталог в проде — снимок просто не обновится
            logger.warning("снимок нарезки не обновлён: %s", error)

    @staticmethod
    def _stored_chunks(manifest_path: Path, chunks_path: Path, manifest: dict[str, object]) -> list[Chunk] | None:
        if read_json(manifest_path) != manifest:
            return None
        rows = read_jsonl(chunks_path)
        if not rows:
            return None
        return [Chunk(**row) for row in rows]
