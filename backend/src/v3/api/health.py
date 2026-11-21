"""Роутер здоровья: готов ли сервис отвечать (индекс построен)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])

READY = "ok"
DEGRADED = "degraded"


@router.get("/health")
def health(request: Request) -> JSONResponse:
    """200 — индекс готов; 503 — сервис поднялся без индекса."""
    state = request.app.state
    if getattr(state, "chat_service", None) is None:
        return JSONResponse(
            status_code=503,
            content={"status": DEGRADED, "reason": str(getattr(state, "index_error", "неизвестно"))},
        )
    return JSONResponse(content={"status": READY})
