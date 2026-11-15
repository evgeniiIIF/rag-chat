# RAG Chat · монорепо

Чат по документу (КЦ). Backend — FastAPI (Python 3.12), frontend — React 18 + Vite + Tailwind, proxy — nginx.

## Возможности

- **Точные ответы** по документу (RAG: hybrid search + LLM).
- **Честный отказ**: если ответа нет в документе — «Не знаю» (без галлюцинаций).
- **Small Talk**: приветствия, благодарности, прощания (без поиска).
- **Input Guardrail**: защита от мусора, оскорблений, prompt injection.
- **Светлая/тёмная тема** с переключателем.
- **Хэш-инвалидация индекса**: первый старт ~1.5 мин, последующие — ~3 сек (если документ не менялся).

## Запуск (dev)

\`\`\`bash
cp .env.example .env
# вписать реальный ключ модели polza.ai в BACKEND_API_KEY
docker compose up -d --build
\`\`\`

Первый запуск занимает ~1.5–2 минуты: backend читает \`backend/data/*.docx\`,
режет на чанки и строит Chroma-индекс. Прогресс — в логе \`docker compose logs -f backend\`.
Последующие старты — мгновенные (хэш документа не менялся).

- UI:   http://localhost:8081
- API:  http://localhost:8081/api/chat
- Health: http://localhost:8081/api/health

## Проверки

Backend (локально, через conda env \`ragchat\`):

\`\`\`bash
cd backend
conda activate ragchat
uv sync --extra dev
make check        # ruff + ruff format + mypy strict (models+services) + pytest
\`\`\`

Frontend (локально):

\`\`\`bash
cd frontend
npm install
npm run check     # eslint + tsc --noEmit + vitest
\`\`\`

E2E (Playwright) требует браузеры (\`npx playwright install chromium\`); в \`npm run check\` не входит.

## Оценка качества (RAGAS)

\`\`\`bash
# Golden set: backend/eval/golden_set.json (10 вопросов)
# Запуск RAGAS (требует API-ключ polza.ai):
cd eval
uv run python ../backend/eval/run_ragas.py
\`\`\`

**Faithfulness: 0.845** (цель > 0.90, enterprise-уровень).

## Структура

\`\`\`
backend/
  src/
    core/            # config (pydantic-settings), logging, di
    schemas/         # pydantic-схемы HTTP-границы (ChatRequest, ChatResponse)
    api/             # тонкие роутеры (chat, query, health)
    services/        # use-cases: chat_service, answer_gate, answer_generator, query_condenser, query_rewriter, small_talk, guardrail, chat_presenter
    repositories/    # docx_loader, vector_store, embeddings, hybrid_retriever
    models/          # доменные модели: chunk, retrieved, grounding, turn
  tests/             # unit + integration + e2e
  eval/              # golden_set.json, run_ragas.py
frontend/
  src/
    app/             # composition root: env, theme, main.tsx
    shared/api/      # HttpClient + interceptors (CSRF, Unauthorized)
    shared/ui/       # UIButton, UIInput (Tailwind + inline)
    components/      # ChatMessageList (пузыри, аватарки)
    features/chat/   # types (zod), api, useChat (react-query)
    pages/           # ChatPage (ChatGPT-style, тёмная тема)
  tests/             # unit (vitest) + e2e (playwright)
nginx/
  conf.d/default.conf  # :8081 → frontend:5173, /api/* → backend:8000
docs/chains/chat.md
\`\`\`

## Стек

- Backend: Python 3.12, FastAPI, pydantic v2, LangChain 0.1, ChromaDB, BM25.
- Frontend: React 18, Vite 5, TypeScript strict, zod, react-query, Tailwind CSS.
- Контейнеры: multi-stage Dockerfile (prod), dev с hot-reload.

## Заметки

- Модель LLM настраивается через \`BACKEND_LLM_MODEL\` в \`.env\` — должна существовать у провайдера.
- Embedding-модель: \`BACKEND_EMBEDDING_MODEL\` (по умолчанию \`qwen/qwen3-embedding-8b\`).
- \`SCORE_THRESHOLD\` — порог «Не знаю». Ниже — gate отсекает ответ. Дефолт 0.02.
- \`docs/chains/chat.md\` — обязательный артефакт: код = 1 шаг цепочки.
