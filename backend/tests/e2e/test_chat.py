from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from src.main import app
from src.models.chunk import Chunk, ParagraphSpan
from src.models.grounding import Grounding
from src.models.retrieved import RetrievedChunk
from src.services.chat_presenter import present
from src.services.chat_service import ChatService


class _StubService(ChatService):
    def __init__(self) -> None:  # type: ignore[super-init-not-called]
        pass

    def ask(self, request):  # type: ignore[override]
        hits = [
            RetrievedChunk(
                chunk=Chunk(
                    source="КЦ.docx",
                    text="Компания работает с 2017 года.",
                    span=ParagraphSpan(start=3, end=3),
                ),
                score=0.9,
            )
        ]
        return present("С 2017 года.", Grounding.GROUNDED, hits)


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app.state.chat_service = _StubService()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as cli:
        yield cli


async def test_health(client: httpx.AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_chat_returns_grounded_with_span(client: httpx.AsyncClient) -> None:
    r = await client.post("/chat", json={"question": "С какого года?"})
    assert r.status_code == 200
    body = r.json()
    assert body["grounded"] is True
    assert body["sources"][0]["paragraph_start"] == 3
    assert body["answer"] == "С 2017 года."


async def test_chat_validates_empty_question(client: httpx.AsyncClient) -> None:
    r = await client.post("/chat", json={"question": ""})
    assert r.status_code == 422


async def test_query_alias_returns_same_shape(client: httpx.AsyncClient) -> None:
    r = await client.post("/query", json={"question": "q"})
    assert r.status_code == 200
    assert set(r.json().keys()) == {"answer", "sources", "grounded", "top_score"}


async def test_session_id_and_long_history_accepted(client: httpx.AsyncClient) -> None:
    """S04: session_id опционален, история допускается до 30 реплик (обратная совместимость)."""
    history = [{"role": "user" if i % 2 else "assistant", "content": f"реплика {i}"} for i in range(30)]
    r = await client.post("/chat", json={"question": "С какого года?", "session_id": "s-1", "history": history})
    assert r.status_code == 200


async def test_history_over_limit_and_bad_session_id_rejected(client: httpx.AsyncClient) -> None:
    too_long = [{"role": "user", "content": "q"} for _ in range(31)]
    r = await client.post("/chat", json={"question": "С какого года?", "history": too_long})
    assert r.status_code == 422
    r = await client.post("/chat", json={"question": "С какого года?", "session_id": ""})
    assert r.status_code == 422
