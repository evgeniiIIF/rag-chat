"""Гибридный поиск: векторы (Chroma) + слова (BM25), слияние Reciprocal Rank Fusion.

Своё здесь только слияние и границы типов: Chroma, BM25 и эмбеддинги — из библиотек
(`specs/001-v3-langgraph-rag/research.md`, R3).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from langchain_chroma import Chroma
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from core.config import Settings
from domain.models import Chunk, RetrievedChunk

COLLECTION_NAME = "chunks"
RANK_CONST = 60
DocSearch = Callable[[str, int], Sequence[Document]]


def to_documents(chunks: Sequence[Chunk]) -> list[Document]:
    """Фрагменты домена → документы LangChain (метаданные несут адрес источника)."""
    return [
        Document(
            page_content=chunk.text,
            metadata={
                "id": chunk.id,
                "source": chunk.source,
                "order": chunk.order,
                "paragraph_start": chunk.paragraph_start,
                "paragraph_end": chunk.paragraph_end,
            },
        )
        for chunk in chunks
    ]


def to_chunk(document: Document) -> Chunk:
    """Документ LangChain → фрагмент домена (обратное преобразование)."""
    meta = document.metadata
    return Chunk(
        id=str(meta["id"]),
        source=str(meta["source"]),
        order=int(meta["order"]),
        paragraph_start=int(meta["paragraph_start"]),
        paragraph_end=int(meta["paragraph_end"]),
        text=document.page_content,
    )


def rrf_fuse(rankings: Sequence[Sequence[str]], *, limit: int) -> list[tuple[str, float]]:
    """Слить ранжирования по RRF и нормализовать скор в 0..1.

    Лучший документ, найденный обоими способами, получает 1.0, найденный только одним — 0.5.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for position, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (RANK_CONST + position)

    ceiling = len(rankings) / (RANK_CONST + 1)
    if ceiling <= 0.0:
        return []
    fused = [(doc_id, min(1.0, score / ceiling)) for doc_id, score in scores.items()]
    fused.sort(key=lambda item: (-item[1], item[0]))
    return fused[:limit]


class HybridRetriever:
    """Поиск по двум каналам с слиянием RRF; оба канала — внешние функции."""

    def __init__(self, *, vector_search: DocSearch, keyword_search: DocSearch) -> None:
        self._vector_search = vector_search
        self._keyword_search = keyword_search

    def search(self, question: str, k: int) -> list[RetrievedChunk]:
        """Топ-k фрагментов с нормализованным скором и рангом."""
        vector_docs = list(self._vector_search(question, k))
        keyword_docs = list(self._keyword_search(question, k))
        by_id: dict[str, Document] = {}
        for document in [*vector_docs, *keyword_docs]:
            by_id.setdefault(str(document.metadata["id"]), document)

        rankings = [
            [str(document.metadata["id"]) for document in vector_docs],
            [str(document.metadata["id"]) for document in keyword_docs],
        ]
        return [
            RetrievedChunk(chunk=to_chunk(by_id[doc_id]), score=score, rank=rank)
            for rank, (doc_id, score) in enumerate(rrf_fuse(rankings, limit=k), start=1)
        ]


def build_embeddings(settings: Settings) -> Embeddings:
    """Эмбеддинги провайдера (OpenAI-совместимый endpoint).

    Провайдеры вроде polza.ai не принимают `input` в виде массивов токенов, поэтому
    отключаем клиентскую токенизацию: `check_embedding_ctx_length=False` + `tiktoken_enabled=False`
    (иначе langchain-openai шлёт id токенов и получает 400 BAD_REQUEST).
    """
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        base_url=settings.base_url,
        api_key=settings.api_key,
        check_embedding_ctx_length=False,
        tiktoken_enabled=False,
        allowed_special=set(),
        disallowed_special=set(),
    )


def build_index(chunks: Sequence[Chunk], settings: Settings, *, rebuild: bool = True) -> HybridRetriever:
    """Собрать гибридный поиск; `rebuild=False` — использовать уже сохранённый Chroma."""
    documents = to_documents(chunks)
    store = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=build_embeddings(settings),
        persist_directory=str(settings.chroma_dir),
    )
    if rebuild:
        store.reset_collection()
        store.add_documents(documents)

    bm25 = BM25Retriever.from_documents(documents)

    def keyword_search(question: str, limit: int) -> Sequence[Document]:
        bm25.k = limit
        return bm25.invoke(question)

    return HybridRetriever(
        vector_search=lambda question, limit: store.similarity_search(question, k=limit),
        keyword_search=keyword_search,
    )
