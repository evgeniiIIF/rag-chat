"""Границы HTTP /chat: pydantic v2, parse-don’t-validate."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..models.turn import Turn

HISTORY_MAX_TURNS: int = 30


class SourceSchema(BaseModel):
    source: str
    paragraph_start: int = Field(..., ge=1)
    paragraph_end: int = Field(..., ge=1)
    text: str  # полный текст чанка


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    history: list[Turn] = Field(default_factory=list, max_length=HISTORY_MAX_TURNS)
    session_id: str | None = Field(None, min_length=1, max_length=64)
    k: int | None = Field(None, ge=1, le=10)


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceSchema]
    grounded: bool
    top_score: float = Field(..., ge=0.0, le=1.0)
