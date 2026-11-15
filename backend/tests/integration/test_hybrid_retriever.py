from __future__ import annotations

from pathlib import Path

from src.core.config import Settings
from src.models.chunk import Chunk, ParagraphSpan
from src.repositories.hybrid_retriever import HybridRetriever, top_score
from src.repositories.vector_store import VectorStoreRepository


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        API_KEY="dummy",
        CHROMA_DIR=str(tmp_path / "chroma"),
        DATA_DIR=str(tmp_path / "data"),
    )


def _corpus() -> list[Chunk]:
    return [
        Chunk(
            source="КЦ.docx",
            text="Иван Висильевич — царь, который знал RAG.",
            span=ParagraphSpan(start=1, end=1),
        ),
        Chunk(
            source="КЦ.docx",
            text="Григорий Рыльский — логист в Пятёрочке.",
            span=ParagraphSpan(start=2, end=2),
        ),
        Chunk(
            source="КЦ.docx",
            text="Компания работает с 2017 года и провела 2500 процедур.",
            span=ParagraphSpan(start=3, end=3),
        ),
    ]


def test_search_returns_scored_chunks_with_spans(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    repo = VectorStoreRepository(settings)
    chunks = _corpus()
    store = repo.rebuild(chunks, source_hash="h1")
    retriever = HybridRetriever(store, chunks)

    hits = retriever.search("кто такой Иван Висильевич", k=2)
    assert 1 <= len(hits) <= 2
    for hit in hits:
        assert 0.0 <= hit.score <= 1.0
        assert hit.chunk.source == "КЦ.docx"
        assert hit.chunk.span.start >= 1


def test_top_score_zero_on_empty() -> None:
    assert top_score([]) == 0.0


def test_bm25_finds_keyword_even_if_vector_misses(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    repo = VectorStoreRepository(settings)
    chunks = _corpus()
    store = repo.rebuild(chunks, source_hash="h1")
    retriever = HybridRetriever(store, chunks)

    hits = retriever.search("2500 процедур", k=3)
    assert any("2500" in hit.chunk.text for hit in hits)
