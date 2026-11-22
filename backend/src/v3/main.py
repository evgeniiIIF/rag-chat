"""Composition root v3: настройки → индекс корпуса → граф → FastAPI.

При старте строится (или переиспользуется) индекс; если корпус недоступен, сервис
поднимается в деградированном режиме: `/api/health` отдаёт 503 с причиной, `/api/chat` — 503.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api import chat as chat_api
from api import health as health_api
from core.config import Settings, get_settings
from core.logging import configure_logging
from infrastructure.llm import build_chat_model, build_condense, build_intake, build_structured_model
from services.chat_service import ChatService
from services.index_service import IndexService

API_PREFIX = "/api"

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, *, service: ChatService | None = None) -> FastAPI:
    """Приложение FastAPI; `service` позволяет подменить сценарий в тестах."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        config = settings if settings is not None else get_settings()
        configure_logging(config.log_level)
        app.state.chat_service = service
        app.state.index_error = None
        if service is None:
            try:
                index = IndexService(config)
                index.ensure_index()
            except Exception as exc:  # причина уходит в /api/health
                logger.error("индекс не построен: %s", exc)
                app.state.index_error = str(exc)
            else:
                app.state.chat_service = ChatService(
                    config,
                    model=build_chat_model(config),
                    search=index.search,
                    invoke=build_structured_model(config),
                    condense=build_condense(build_chat_model(config)),
                    intake=build_intake(build_chat_model(config, max_tokens=2000)),
                )
                logger.info("индекс готов: %d фрагментов", len(index.chunks))
        yield
        app.state.chat_service = None

    application = FastAPI(title="ragchat v3", version="3.0.0", lifespan=lifespan)
    application.include_router(chat_api.router, prefix=API_PREFIX)
    application.include_router(health_api.router, prefix=API_PREFIX)
    return application


app = create_app()
