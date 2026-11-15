"""Результат retrieval: чанк + нормализованный score в [0,1]."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .chunk import Chunk


class RetrievedChunk(BaseModel):
    chunk: Chunk
    score: float = Field(..., ge=0.0, le=1.0)
