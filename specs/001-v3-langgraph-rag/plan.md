# Implementation Plan: RAG-ответы по документу КЦ (v3, LangGraph)

**Branch**: `001-v3-langgraph-rag` | **Date**: 2026-11-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-v3-langgraph-rag/spec.md`

## Summary

Самостоятельный сервис `backend/src/v3/` (FastAPI + LangGraph): при старте читает `backend/data/*.docx`,
режет на фрагменты, строит гибридный индекс (векторы Chroma + BM25) с сохранением артефактов;
на запрос запускает граф `retrieve → grade → generate` и возвращает ответ с источниками или
честный отказ. HTTP-контракт `POST /api/chat` и `/api/health` совместим с текущим фронтендом.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: `langgraph`, `langchain-core`, `langchain-openai`, `langchain-chroma`,
`langchain-community` (Docx2txtLoader, BM25Retriever), `langchain-text-splitters`, `chromadb`,
`rank-bm25`, `fastapi`, `uvicorn`, `pydantic` v2, `pydantic-settings`; dev: `ruff`, `mypy`,
`pytest`, `pytest-cov`, `ragas`

**Storage**: Chroma persistent dir `backend/src/v3/.chroma`; артефакты `backend/src/v3/artifacts/` (JSONL/JSON)

**Testing**: pytest (unit — узлы графа и адаптеры, integration — переходы графа, e2e — HTTP)

**Target Platform**: Linux, Docker (через существующий nginx, замена upstream позже)

**Project Type**: web-service (backend only, фронтенд не меняется)

**Performance Goals**: старт с готовым индексом < 10 с; ответ на вопрос p95 < 15 с

**Constraints**: ответы только по содержимому `backend/data`; без памяти диалога, без small talk
и guardrail (вне области v3); ключи только из env

**Scale/Scope**: 1 документ (~1.7 МБ), десятки запросов в час, один процесс

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Принцип | Как соблюдается | Статус |
|---|---|---|
| I. Коробочное прежде своего | узлы = LangGraph `StateGraph`, узлы-адаптеры над `Docx2txtLoader`, `RecursiveCharacterTextSplitter`, `Chroma`, `EnsembleRetriever`/`BM25Retriever`, `ChatOpenAI.with_structured_output`; свой код — только склейка (см. research.md) | PASS |
| II. Наблюдаемость | каждый узел пишет `backend/src/v3/artifacts/<request_id>/{chunks,retrieved,prompt,answer}.json` + структурный лог входа/выхода | PASS |
| III. Шаг пульта | `docs/chains/v3.md`, цикл `chain-control`, одна правка за шаг | PASS |
| IV. Строгие типы | pydantic v2 на границах, mypy `--strict`, uv + lock | PASS |
| V. Изоляция и контракт фронта | изменяется только `backend/src/v3/` + `docs/chains/v3.md` + `specs/`; контракт `/api/chat` сохранён | PASS |
| VI. Единая проверка | `backend/src/v3/Makefile check` = ruff + format + mypy + pytest(cov≥80); ragas против golden set v2 | PASS |

Нарушений нет, Complexity Tracking не заполняется.

## Project Structure

### Documentation (this feature)

```text
specs/001-v3-langgraph-rag/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/openapi.yaml
└── checklists/requirements.md
```

### Source Code (repository root)

```text
backend/src/v3/                          # корень нового проекта (uv) = корень версии, старые файлы не трогаем
├── pyproject.toml
├── .python-version
├── Makefile
├── core/config.py               # пакет core: pydantic-settings, единственное чтение env
├── core/logging.py              # JSON-лог на stdlib
├── domain/models.py             # Chunk, RetrievedChunk, Answer, SourceRef
├── domain/graph_state.py        # TypedDict состояния графа
├── infrastructure/loader.py     # DirectoryLoader + Docx2txtLoader, sha256
├── infrastructure/splitter.py   # RecursiveCharacterTextSplitter
├── infrastructure/index.py      # Chroma + embeddings + EnsembleRetriever
├── infrastructure/llm.py        # ChatOpenAI + with_structured_output
├── infrastructure/artifacts.py  # запись артефактов этапов
├── graph/nodes/retrieve.py
├── graph/nodes/grade.py
├── graph/nodes/generate.py
├── graph/build.py               # StateGraph + compile
├── services/index_service.py    # старт: ingest → split → index (артефакты)
├── services/chat_service.py     # запуск графа, сбор ответа
├── schemas/chat.py              # HTTP-граница (совместима с фронтендом)
├── api/chat.py
├── api/health.py
├── main.py                      # composition root: uvicorn main:app
├── tests/{unit,integration,e2e}/
├── eval/run_ragas.py
├── artifacts/                   # gitignore
└── .chroma/                     # gitignore
```

**Structure Decision**: web-service, самостоятельный uv-проект в `backend/src/v3/` (корень версии, слои
без обёртки-пакета: `core`, `domain`, `infrastructure`, `graph`, `services`, `schemas`, `api`; импорты
`from core.config import …`, у v2 аналогично `from src.core.config import …`), слои по
`~/.pi/agent/rules/architecture.md`; существующие `backend/`, `frontend/`, `eval/`, compose-файлы
не изменяются. Пульт `docs/chains/v3.md` ведётся в формате расширения chain-guard: `ЦЕПОЧКА`
правится руками, `ФАЙЛЫ` — живая проекция `src/` и `tests/`.

## Complexity Tracking

Не заполняется — нарушений конституции нет.
