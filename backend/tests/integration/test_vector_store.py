from __future__ import annotations

from pathlib import Path

from src.core.config import Settings
from src.models.chunk import Chunk, ParagraphSpan
from src.repositories.vector_store import (
    COLLECTION_NAME,
    HASH_KEY,
    SOURCE_KEY,
    SPAN_END_KEY,
    SPAN_START_KEY,
    VectorStoreRepository,
    content_hash,
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        API_KEY="dummy",
        CHROMA_DIR=str(tmp_path / "chroma"),
        DATA_DIR=str(tmp_path / "data"),
    )


def _chunks(source: str = "КЦ.docx") -> list[Chunk]:
    return [
        Chunk(source=source, text="Первый", span=ParagraphSpan(start=1, end=1)),
        Chunk(source=source, text="Второй", span=ParagraphSpan(start=2, end=2)),
    ]


def test_rebuild_is_idempotent_and_keeps_metadata(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    repo = VectorStoreRepository(settings)
    payload = _chunks()
    h = "abc123"
    store = repo.rebuild(payload, h)
    got = store._collection.get(include=["metadatas", "documents"])  # type: ignore[attr-defined]
    assert got["documents"] and len(got["documents"]) == 2
    metas = got["metadatas"] or []
    assert all(m[SOURCE_KEY] == "КЦ.docx" for m in metas)
    assert all(m[HASH_KEY] == h for m in metas)
    assert {m[SPAN_START_KEY] for m in metas} == {1, 2}
    assert {m[SPAN_END_KEY] for m in metas} == {1, 2}
    # второй rebuild не падает на существующей коллекции
    repo.rebuild(payload, h)


def test_content_hash_detects_change(tmp_path: Path) -> None:
    p = tmp_path / "doc.bin"
    p.write_bytes(b"one")
    first = content_hash(p)
    p.write_bytes(b"two")
    assert content_hash(p) != first


def test_is_indexed_false_when_file_missing(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    repo = VectorStoreRepository(settings)
    assert repo.is_indexed(tmp_path / "missing.docx") is False


def test_collection_name_is_kc_doc() -> None:
    assert COLLECTION_NAME == "kc_doc"
