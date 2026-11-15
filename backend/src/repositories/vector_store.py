"""Chroma store: коллекция kc_doc, идемпотентная реиндексация по хэшу."""

from __future__ import annotations

import contextlib
import hashlib
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_community.embeddings import FakeEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from ..core.config import Settings
from ..models.chunk import Chunk

COLLECTION_NAME = "kc_doc"
SOURCE_KEY = "source"
SPAN_START_KEY = "paragraph_start"
SPAN_END_KEY = "paragraph_end"
HASH_KEY = "content_hash"


def content_hash(path: Path) -> str:
    """Стабильный хэш содержимого файла — база для инвалидации."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


class VectorStoreRepository:
    """Держит один persistent Chroma-клиент на процесс."""

    def __init__(self, settings: Settings, embeddings: Embeddings | None = None) -> None:
        self._settings = settings
        self._embeddings: Embeddings = embeddings or FakeEmbeddings(size=8)
        self._client: Any = chromadb.PersistentClient(
            path=settings.chroma_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._store: Chroma | None = None

    def is_indexed(self, path: Path) -> bool:
        if not path.is_file():
            return False
        wanted = content_hash(path)
        try:
            collection = self._client.get_collection(COLLECTION_NAME)
        except Exception:
            return False
        try:
            sample = collection.get(limit=1, include=["metadatas"])
        except Exception:
            return False
        metadatas = sample.get("metadatas") or []
        if not metadatas:
            return False
        stored = metadatas[0].get(HASH_KEY)
        return bool(stored == wanted)

    def rebuild(self, chunks: list[Chunk], source_hash: str) -> Chroma:
        with contextlib.suppress(Exception):
            self._client.delete_collection(COLLECTION_NAME)
        documents = [_to_document(chunk, source_hash) for chunk in chunks]
        self._store = Chroma.from_documents(
            documents=documents,
            embedding=self._embeddings,
            persist_directory=self._settings.chroma_dir,
            client=self._client,
            collection_name=COLLECTION_NAME,
            collection_metadata={"hnsw:space": "cosine"},
        )
        return self._store

    def load(self) -> Chroma:
        self._store = Chroma(
            persist_directory=self._settings.chroma_dir,
            embedding_function=self._embeddings,
            client=self._client,
            collection_name=COLLECTION_NAME,
        )
        return self._store

    def get(self) -> Chroma:
        if self._store is None:
            return self.load()
        return self._store


def _to_document(chunk: Chunk, source_hash: str) -> Document:
    return Document(
        page_content=chunk.text,
        metadata={
            SOURCE_KEY: chunk.source,
            SPAN_START_KEY: chunk.span.start,
            SPAN_END_KEY: chunk.span.end,
            HASH_KEY: source_hash,
        },
    )
