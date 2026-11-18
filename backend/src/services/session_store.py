"""Хранилище сессий диалога (цепочка chat_v2, узлы 07/17). In-memory + TTL + LRU (решение D6).

Redis/Postgres в стеке нет (один backend-контейнер в docker-compose), поэтому состояние
живёт в процессе. Промах сессии (рестарт, новая вкладка) не ломает диалог: история
приходит с клиента, и TurnAnalyzer достраивает состояние из неё отдельным вызовом не
требует — см. узел 09 (facts/asked уже извлекаются из истории).
"""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from ..models.dialog_state import DialogState
from ..models.turn import Turn

DEFAULT_TTL_SECONDS: int = 24 * 60 * 60
DEFAULT_MAX_SESSIONS: int = 1000
DEFAULT_MAX_TURNS: int = 30


@dataclass(frozen=True)
class Session:
    """Снимок состояния одной сессии: профиль-факты + реплики."""

    state: DialogState
    turns: tuple[Turn, ...]

    @classmethod
    def empty(cls) -> Session:
        return cls(state=DialogState.empty(), turns=())


def dedupe_turns(*sources: Iterable[Turn]) -> tuple[Turn, ...]:
    """Слить несколько списков реплик в одну хронологическую ленту без повторов.

    Ключ — (role, content): pydantic-модель Turn не хешируется.
    """
    seen: set[tuple[str, str]] = set()
    out: list[Turn] = []
    for source in sources:
        for turn in source:
            key = (turn.role, turn.content)
            if key in seen:
                continue
            seen.add(key)
            out.append(turn)
    return tuple(out)


class SessionStore:
    """LRU-карта session_id → Session с истечением по TTL."""

    def __init__(
        self,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_sessions: int = DEFAULT_MAX_SESSIONS,
        max_turns: int = DEFAULT_MAX_TURNS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0 or max_sessions <= 0 or max_turns <= 0:
            raise ValueError("ttl_seconds, max_sessions, max_turns должны быть положительными")
        self._ttl = ttl_seconds
        self._max_sessions = max_sessions
        self._max_turns = max_turns
        self._clock = clock
        self._data: OrderedDict[str, tuple[Session, float]] = OrderedDict()

    def load(self, session_id: str | None) -> Session:
        """Сессия или пустая (просроченная удаляется)."""
        if not session_id:
            return Session.empty()
        entry = self._data.get(session_id)
        if entry is None:
            return Session.empty()
        session, stamp = entry
        if self._clock() - stamp > self._ttl:
            self._data.pop(session_id, None)
            return Session.empty()
        self._data.move_to_end(session_id)
        return session

    def save(self, session_id: str, state: DialogState, turns: Sequence[Turn]) -> Session:
        """Сохранить состояние, обрезая ленту реплик хвостом max_turns и вытесняя LRU."""
        tail = tuple(turns)[-self._max_turns :]
        session = Session(state=state, turns=tail)
        self._data[session_id] = (session, self._clock())
        self._data.move_to_end(session_id)
        self._evict()
        return session

    def size(self) -> int:
        return len(self._data)

    def _evict(self) -> None:
        now = self._clock()
        for session_id, (_, stamp) in list(self._data.items()):
            if now - stamp > self._ttl:
                self._data.pop(session_id, None)
        while len(self._data) > self._max_sessions:
            self._data.popitem(last=False)
