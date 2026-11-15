"""Hybrid retrieval: vector (Chroma) + BM25.

Chroma с hnsw:space=cosine возвращает squared L2 по нормализованным векторам
(= 2*(1 - cos)). Значит, similarity = 1 - distance/2, dist ∈ [0,2].

BM25 сырые скоры не нормируем на максимум (иначе топ-хит всегда 1.0 даже для
нерелевантного запроса). Ограничиваем сверху константой BM25_CAP и смешиваем
с vector: score = 0.7*sim + 0.3*bm25_norm.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from langchain_community.vectorstores import Chroma
from rank_bm25 import BM25Okapi

from ..models.chunk import Chunk, ParagraphSpan
from ..models.retrieved import RetrievedChunk

SOURCE_KEY = "source"
SPAN_START_KEY = "paragraph_start"
SPAN_END_KEY = "paragraph_end"

VECTOR_WEIGHT: float = 0.7
BM25_WEIGHT: float = 0.3
BM25_CAP: float = 20.0


def _tokenize(text: str) -> list[str]:
    return [t for t in text.lower().split() if t]


def _chunk_from_metadata(text: str, metadata: dict[str, object]) -> Chunk:
    source = str(metadata.get(SOURCE_KEY, "unknown"))
    start = int(str(metadata.get(SPAN_START_KEY, 1)))
    end = int(str(metadata.get(SPAN_END_KEY, start)))
    return Chunk(source=source, text=text, span=ParagraphSpan(start=start, end=end))


def _distance_to_similarity(distance: float) -> float:
    """cosine dist ∈ [0,2] -> similarity ∈ [0,1]."""
    sim = 1.0 - distance / 2.0
    return max(0.0, min(1.0, sim))


class HybridRetriever:
    def __init__(self, store: Chroma, corpus: Sequence[Chunk]) -> None:
        self._store = store
        self._corpus: list[Chunk] = list(corpus)
        tokenized = [_tokenize(c.text) for c in self._corpus]
        self._bm25: BM25Okapi | None = BM25Okapi(tokenized) if tokenized else None

    def search(self, question: str, k: int) -> list[RetrievedChunk]:
        vector_hits = {self._key(h): h for h in self._vector_search(question, k)}
        bm25_hits = {self._key(h): h for h in self._bm25_search(question, k)}

        merged: dict[tuple[str, int, int], RetrievedChunk] = {}
        for key in set(vector_hits) | set(bm25_hits):
            v = vector_hits.get(key)
            b = bm25_hits.get(key)
            v_score = v.score if v is not None else 0.0
            b_score = b.score if b is not None else 0.0
            combined = VECTOR_WEIGHT * v_score + BM25_WEIGHT * b_score
            chunk = v or b
            assert chunk is not None
            merged[key] = RetrievedChunk(chunk=chunk.chunk, score=max(0.0, min(1.0, combined)))

        ordered = sorted(merged.values(), key=lambda r: r.score, reverse=True)
        return ordered[:k]

    @staticmethod
    def _key(hit: RetrievedChunk) -> tuple[str, int, int]:
        return (hit.chunk.source, hit.chunk.span.start, hit.chunk.span.end)

    def _vector_search(self, question: str, k: int) -> list[RetrievedChunk]:
        results = self._store.similarity_search_with_score(question, k=k)
        out: list[RetrievedChunk] = []
        for doc, distance in results:
            out.append(
                RetrievedChunk(
                    chunk=_chunk_from_metadata(doc.page_content, doc.metadata),
                    score=_distance_to_similarity(float(distance)),
                )
            )
        return out

    def _bm25_search(self, question: str, k: int) -> list[RetrievedChunk]:
        if self._bm25 is None:
            return []
        tokens = _tokenize(question)
        if not tokens:
            return []
        raw = np.asarray(self._bm25.get_scores(tokens), dtype=float)
        if raw.size == 0 or float(raw.max()) <= 0.0:
            return []
        top_idx = np.argsort(raw)[::-1][: k * 2]
        out: list[RetrievedChunk] = []
        for i in top_idx:
            score = float(raw[int(i)])
            if score <= 0.0:
                continue
            normalized = min(1.0, score / BM25_CAP)
            out.append(RetrievedChunk(chunk=self._corpus[int(i)], score=normalized))
        return out


def top_score(hits: Sequence[RetrievedChunk]) -> float:
    if not hits:
        return 0.0
    return max(hit.score for hit in hits)
