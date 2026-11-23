"""Роутер чата: только HTTP-граница, вся логика в ChatService."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from schemas.chat import ChatRequest, ChatResponse, HistoryResponse
from services.chat_service import ChatService

router = APIRouter(tags=["chat"])

SERVICE_ATTR = "chat_service"


def get_chat_service(request: Request) -> ChatService:
    """Достать сервис из состояния приложения (ставится в lifespan)."""
    service = getattr(request.app.state, SERVICE_ATTR, None)
    if not isinstance(service, ChatService):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="индекс недоступен: сервис не инициализирован",
        )
    return service


ServiceDep = Annotated[ChatService, Depends(get_chat_service)]


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, service: ServiceDep) -> ChatResponse:
    """Ответ по документу или честный отказ."""
    return service.ask(payload)


@router.get("/session/history", response_model=HistoryResponse)
def history(session_id: str, service: ServiceDep) -> HistoryResponse:
    """История диалога для новой вкладки: то, что уже лежит в чекпойнтере."""
    return service.history(session_id)


@router.post("/session/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset_session(session_id: str, service: ServiceDep) -> None:
    """Удалить чекпойнт сессии (кнопка «Очистить чат»)."""
    service.reset_session(session_id)
