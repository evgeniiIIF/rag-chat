# Quickstart: v3

## Установка

```bash
cd /home/jon/Projects/test-tasks/rag_chat/backend/src/v3 && uv sync
```

## Конфиг

```bash
cp ../../../.env.example .env   # v3 читает те же BACKEND_* переменные
# BACKEND_API_KEY, BACKEND_BASE_URL, BACKEND_LLM_MODEL, BACKEND_EMBEDDING_MODEL
```

## Проверка

```bash
cd /home/jon/Projects/test-tasks/rag_chat/backend/src/v3 && make check
```

## Запуск (вручную, агент не запускает)

```bash
cd /home/jon/Projects/test-tasks/rag_chat/backend/src/v3 && uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

При старте: чтение `../../backend/data/*.docx` → чанки → индекс → артефакты
`backend/src/v3/artifacts/index/chunks.jsonl`. Если sha256 документов не менялся — индекс не перестраивается.

## Запрос

```bash
curl -s http://localhost:8000/api/chat -H 'Content-Type: application/json' \
  -d '{"question":"<вопрос по документу>"}' | python3 -m json.tool
```

## Что смотреть

| Что | Где |
|---|---|
| Чанки документа | `backend/src/v3/artifacts/index/chunks.jsonl` |
| Найденные фрагменты | `backend/src/v3/artifacts/<request_id>/retrieved.json` |
| Промпт к модели | `backend/src/v3/artifacts/<request_id>/prompt.json` |
| Ответ модели + отказ | `backend/src/v3/artifacts/<request_id>/answer.json` |

## Оценка качества (вручную)

```bash
cd /home/jon/Projects/test-tasks/rag_chat/backend/src/v3 && uv run python eval/run_ragas.py
```
