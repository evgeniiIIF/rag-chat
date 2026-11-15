"""Тонкий роутер /chat и deprecated /query. Никакой бизнес-логики."""

from __future__ import annotations

import warnings
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from ..schemas.chat import ChatRequest, ChatResponse
from ..services.chat_service import ChatService

router = APIRouter(tags=["chat"])

REQUEST_SERVICE_KEY = "chat_service"


def get_chat_service(request: Request) -> ChatService:
    service = getattr(request.app.state, REQUEST_SERVICE_KEY, None)
    if service is None:
        raise RuntimeError("ChatService не инициализирован (lifespan)")
    return service  # type: ignore[no-any-return]


ServiceDep = Annotated[ChatService, Depends(get_chat_service)]


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, service: ServiceDep) -> ChatResponse:
    return service.ask(payload)


@router.post("/query", response_model=ChatResponse, deprecated=True)
async def query(payload: ChatRequest, service: ServiceDep) -> ChatResponse:
    warnings.warn(
        "POST /query устарел, используйте POST /chat",
        DeprecationWarning,
        stacklevel=2,
    )
    return service.ask(payload)
