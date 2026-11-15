"""Composition root: lifespan собирает ChatService; /chat, /query, /health."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from langchain_openai import ChatOpenAI

from .api.chat_router import router as chat_router
from .core.config import get_settings
from .core.logging import configure_logging, get_logger
from .models.chunk import Chunk
from .repositories.docx_loader import DocxParagraphLoader, merge_adjacent
from .repositories.embeddings import OpenAIEmbeddingsAdapter
from .repositories.hybrid_retriever import HybridRetriever
from .repositories.vector_store import VectorStoreRepository
from .services.answer_generator import AnswerGenerator, LLMPort
from .services.chat_service import ChatService
from .services.query_condenser import QueryCondenser


class _LangChainLLMAdapter(LLMPort):
    """Адаптер ChatOpenAI -> LLMPort."""

    def __init__(self, llm: ChatOpenAI) -> None:
        self._llm = llm

    def complete(self, system: str, user: str) -> str:
        msg = self._llm.invoke(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
        )
        content = msg.content
        return content if isinstance(content, str) else str(content)


def _index_data() -> tuple[list[Chunk], bool]:
    """Грузим data/, склеиваем соседние абзацы; возвращаем (chunks, has_data)."""
    settings = get_settings()
    data_dir = Path(settings.data_dir)
    if not data_dir.is_dir():
        return [], False
    loader = DocxParagraphLoader()
    chunks: list[Chunk] = []
    for path in sorted(data_dir.glob("*.docx")):
        chunks.extend(merge_adjacent(loader.load(path)))
    return chunks, bool(chunks)


def _build_service() -> ChatService:
    settings = get_settings()
    log = get_logger()

    embeddings = OpenAIEmbeddingsAdapter(settings).get()
    store_repo = VectorStoreRepository(settings, embeddings=embeddings)
    chunks, has_data = _index_data()
    if has_data:
        # Инвалидация по хэшу: если документ не менялся — загружаем, иначе пересобираем
        from pathlib import Path as _Path
        data_dir = _Path(settings.data_dir)
        docx_files = sorted(data_dir.glob("*.docx"))
        if docx_files:
            source_file = docx_files[0]
            from .repositories.vector_store import content_hash
            h = content_hash(source_file)
            if store_repo.is_indexed(source_file):
                log.info("Индекс актуален (хэш совпал), загружаем без пересборки")
                store = store_repo.load()
            else:
                store = store_repo.rebuild(chunks, source_hash=h)
                log.info("Индекс пересобран: %d чанков (хэш изменился)", len(chunks))
        else:
            store = store_repo.rebuild(chunks, source_hash="auto")
            log.info("Индекс пересобран: %d чанков", len(chunks))
    else:
        store = store_repo.load()
        log.warning("Нет data/*.docx — грузим существующий индекс")

    retriever = HybridRetriever(store, chunks)
    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.api_key.get_secret_value(),
        base_url=settings.base_url,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
    )
    generator = AnswerGenerator(_LangChainLLMAdapter(llm), settings)
    condenser = QueryCondenser()
    return ChatService(retriever, generator, condenser, settings, corpus=chunks)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    get_logger().info("Backend стартует")
    app.state.chat_service = _build_service()
    yield
    get_logger().info("Backend остановлен")


app = FastAPI(title="RAG Chat API", version="0.2.0", lifespan=lifespan)
app.include_router(chat_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/readiness")
async def readiness() -> dict[str, str]:
    from fastapi import HTTPException
    if getattr(app.state, "chat_service", None) is None:
        raise HTTPException(status_code=503, detail="not ready")
    return {"status": "ready"}
