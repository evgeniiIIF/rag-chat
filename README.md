# RAG Chat · монорепо

Чат по документу (КЦ). Backend — FastAPI (Python 3.12), frontend — React 18 + Vite, proxy — nginx.

## Запуск (dev)

```bash
cp .env.example .env
# вписать реальный ключ в BACKEND_API_KEY
docker compose up -d --build
```

Первый запуск занимает ~1.5–2 минуты: backend читает `backend/data/*.docx`,
режет на чанки и строит Chroma-индекс. Прогресс — в логе `docker compose logs -f backend`.

- UI:   http://localhost:8081
- API:  http://localhost:8081/api/chat
- Health: http://localhost:8081/api/health (nginx → backend)

## Проверки

Backend (локально, через conda env `ragchat`):

```bash
cd backend
conda activate ragchat
uv sync --extra dev
make check        # ruff + ruff format + mypy strict (models+services) + pytest
```

Frontend (локально):

```bash
cd frontend
npm install
npm run check     # eslint + tsc --noEmit + vitest
```

E2E (Playwright) требует браузеры (`npx playwright install chromium`); в `npm run check` не входит — отдельной командой `npm run e2e`.

## Структура

```
backend/
  src/
    core/            # config (pydantic-settings), logging, di
    schemas/         # pydantic-схемы HTTP-границы (ChatRequest, ChatResponse)
    api/             # тонкие роутеры (chat, query, health)
    services/        # use-cases: chat_service, answer_gate, answer_generator, query_condenser, chat_presenter
    repositories/    # docx_loader, vector_store, embeddings, hybrid_retriever
    models/          # доменные модели: chunk, retrieved, grounding, turn
  tests/             # unit + integration + e2e
  docs/chains/chat.md  # макро-цепочка фичи (rules/chains.md)
frontend/
  src/
    app/             # composition root: env, main.tsx
    shared/api/      # HttpClient + interceptors (CSRF, Unauthorized)
    shared/ui/       # UIButton, UIInput
    components/      # ChatMessageList
    features/chat/   # types (zod), api, useChat (react-query)
    pages/           # ChatPage
  tests/             # unit (vitest) + e2e (playwright)
nginx/
  conf.d/default.conf  # :8081 → frontend:5173, /api/* → backend:8000
docs/chains/chat.md
```

## Стек

- Backend: Python 3.12, FastAPI, pydantic v2, LangChain 0.1, ChromaDB, BM25.
- Frontend: React 18, Vite 5, TypeScript strict, zod, react-query, react-hook-form.
- Контейнеры: multi-stage Dockerfile (prod), dev с hot-reload.

## Заметки

- Модель LLM настраивается через `BACKEND_LLM_MODEL` в `.env` — должна существовать у провайдера.
- Embedding-модель: `BACKEND_EMBEDDING_MODEL` (по умолчанию `qwen/qwen3-embedding-8b`).
- `SCORE_THRESHOLD` — порог «Не знаю». Ниже — gate отсекает ответ. Дефолт 0.02.
- `docs/chains/chat.md` — обязательный артефакт: код = 1 шаг цепочки.
