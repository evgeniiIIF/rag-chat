"""Преобразование доменного результата в схему ответа (граница)."""

from __future__ import annotations

from collections.abc import Sequence

from ..models.grounding import Grounding
from ..models.retrieved import RetrievedChunk
from ..schemas.chat import ChatResponse, SourceSchema

SNIPPET_LIMIT: int = 200


def _snippet(text: str) -> str:
    clean = text.strip().replace("\n", " ")
    if len(clean) <= SNIPPET_LIMIT:
        return clean
    return clean[: SNIPPET_LIMIT - 1] + "…"


def present(
    answer: str,
    grounding: Grounding,
    hits: Sequence[RetrievedChunk],
) -> ChatResponse:
    grounded = grounding is Grounding.GROUNDED
    sources: list[SourceSchema] = []
    if grounded:
        sources = [
            SourceSchema(
                source=hit.chunk.source,
                paragraph_start=hit.chunk.span.start,
                paragraph_end=hit.chunk.span.end,
                snippet=_snippet(hit.chunk.text),
            )
            for hit in hits
        ]
    top = max((hit.score for hit in hits), default=0.0)
    return ChatResponse(
        answer=answer,
        sources=sources,
        grounded=grounded,
        top_score=max(0.0, min(1.0, top)),
    )
