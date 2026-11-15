"""Преобразование доменного результата в схему ответа (граница)."""

from __future__ import annotations

from collections.abc import Sequence

from ..models.chunk import Chunk
from ..models.grounding import Grounding
from ..models.retrieved import RetrievedChunk
from ..schemas.chat import ChatResponse, SourceSchema


def present(
    answer: str,
    grounding: Grounding,
    hits: Sequence[RetrievedChunk],
    expanded: Sequence[Chunk] | None = None,
) -> ChatResponse:
    grounded = grounding is Grounding.GROUNDED
    chunks = expanded if expanded is not None else [h.chunk for h in hits]
    sources: list[SourceSchema] = []
    if grounded:
        sources = [
            SourceSchema(
                source=c.source,
                paragraph_start=c.span.start,
                paragraph_end=c.span.end,
                text=c.text,
            )
            for c in chunks
        ]
    top = max((hit.score for hit in hits), default=0.0)
    return ChatResponse(
        answer=answer,
        sources=sources,
        grounded=grounded,
        top_score=max(0.0, min(1.0, top)),
    )
