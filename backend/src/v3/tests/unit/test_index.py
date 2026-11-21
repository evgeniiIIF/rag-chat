"""Тесты поиска: документы ↔ фрагменты, слияние RRF, сборка гибрида над библиотеками."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

import pytest
from langchain_core.documents import Document
from pydantic import SecretStr

from core.config import Settings
from domain.models import Chunk
from infrastructure import index as index_module
from infrastructure.index import (
    HybridRetriever,
    build_embeddings,
    build_index,
    rrf_fuse,
    to_chunk,
    to_documents,
)


def make_chunk(order: int, text: str = "Текст фрагмента.", source: str = "doc.docx") -> Chunk:
    return Chunk(
        id=f"{source}-{order:04d}",
        source=source,
        order=order,
        paragraph_start=order + 1,
        paragraph_end=order + 1,
        text=text,
    )


def make_settings(tmp_path: Any) -> Settings:
    return Settings(api_key=SecretStr("test"), chroma_dir=tmp_path / "chroma", artifacts_dir=tmp_path / "artifacts")


def test_documents_roundtrip_keeps_address() -> None:
    chunk = make_chunk(3)

    document = to_documents([chunk])[0]
    restored = to_chunk(document)

    assert document.metadata["paragraph_start"] == 4
    assert restored == chunk


def test_rrf_fuse_prefers_document_found_by_both_channels() -> None:
    fused = rrf_fuse([["a", "b"], ["b"]], limit=2)

    assert [doc_id for doc_id, _ in fused] == ["b", "a"]
    assert fused[0][1] == pytest.approx(0.992, abs=1e-3)
    assert fused[1][1] == pytest.approx(0.5)


def test_rrf_fuse_empty_rankings() -> None:
    assert rrf_fuse([[], []], limit=3) == []


def test_hybrid_retriever_merges_channels_and_limits() -> None:
    documents = {chunk.id: to_documents([chunk])[0] for chunk in map(make_chunk, range(3))}

    def vector_search(question: str, limit: int) -> Sequence[Document]:
        assert question == "сумма"
        return [documents["doc.docx-0000"], documents["doc.docx-0001"]][:limit]

    def keyword_search(question: str, limit: int) -> Sequence[Document]:
        return [documents["doc.docx-0001"], documents["doc.docx-0002"]][:limit]

    retriever = HybridRetriever(vector_search=vector_search, keyword_search=keyword_search)

    hits = retriever.search("сумма", 2)

    assert [hit.chunk.id for hit in hits] == ["doc.docx-0001", "doc.docx-0000"]
    assert [hit.rank for hit in hits] == [1, 2]
    assert all(0.0 <= hit.score <= 1.0 for hit in hits)


def test_hybrid_retriever_without_hits() -> None:
    retriever = HybridRetriever(vector_search=lambda question, limit: [], keyword_search=lambda question, limit: [])

    assert retriever.search("ничего", 3) == []


class FakeEmbeddings:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


class FakeChroma:
    instances: ClassVar[list[FakeChroma]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.documents: list[Document] = []
        self.reset_calls = 0
        FakeChroma.instances.append(self)

    def reset_collection(self) -> None:
        self.reset_calls += 1
        self.documents = []

    def add_documents(self, documents: Sequence[Document]) -> None:
        self.documents.extend(documents)

    def similarity_search(self, question: str, k: int) -> list[Document]:
        return self.documents[:k]


class FakeBM25:
    def __init__(self, documents: Sequence[Document]) -> None:
        self.documents = list(documents)
        self.k = 4

    @classmethod
    def from_documents(cls, documents: Sequence[Document]) -> FakeBM25:
        return cls(documents)

    def invoke(self, question: str) -> list[Document]:
        return self.documents[: self.k]


def test_build_index_wires_libraries(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.setattr(index_module, "Chroma", FakeChroma)
    monkeypatch.setattr(index_module, "BM25Retriever", FakeBM25)
    monkeypatch.setattr(index_module, "OpenAIEmbeddings", FakeEmbeddings)
    FakeChroma.instances.clear()
    settings = make_settings(tmp_path)
    chunks = [make_chunk(0), make_chunk(1)]

    retriever = build_index(chunks, settings, rebuild=True)

    store = FakeChroma.instances[-1]
    assert store.reset_calls == 1
    assert len(store.documents) == 2
    assert store.kwargs["persist_directory"] == str(settings.chroma_dir)
    assert len(retriever.search("сумма", 1)) == 1


def test_build_index_reuses_persisted_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.setattr(index_module, "Chroma", FakeChroma)
    monkeypatch.setattr(index_module, "BM25Retriever", FakeBM25)
    monkeypatch.setattr(index_module, "OpenAIEmbeddings", FakeEmbeddings)
    FakeChroma.instances.clear()
    settings = make_settings(tmp_path)
    chunks = [make_chunk(0)]

    retriever = build_index(chunks, settings, rebuild=False)

    assert FakeChroma.instances[-1].reset_calls == 0
    assert isinstance(retriever, HybridRetriever)


def test_build_embeddings_uses_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.setattr(index_module, "OpenAIEmbeddings", FakeEmbeddings)
    settings = make_settings(tmp_path)

    embeddings = build_embeddings(settings)

    assert isinstance(embeddings, FakeEmbeddings)
    assert embeddings.kwargs["api_key"].get_secret_value() == "test"
    assert embeddings.kwargs["model"] == settings.embedding_model
    # провайдер не принимает токены: клиентская токенизация должна быть выключена
    assert embeddings.kwargs["check_embedding_ctx_length"] is False
    assert embeddings.kwargs["tiktoken_enabled"] is False
