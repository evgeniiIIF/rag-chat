# Data Model: v3

**Фича**: [spec.md](./spec.md) · **План**: [plan.md](./plan.md)

## Сущности (pydantic v2, `backend/src/v3/domain/models.py`)

### Chunk

| Поле | Тип | Правило |
|---|---|---|
| `id` | `str` | `"{source}-{order:04d}"`, уникален |
| `source` | `str` | имя файла документа |
| `order` | `int` ≥0 | порядок чанка в документе |
| `paragraph_start` / `paragraph_end` | `int` ≥1 | границы в исходном документе, `start ≤ end` |
| `text` | `str` | непустой, длина ≤ `chunk_size` |

### RetrievedChunk

| Поле | Тип | Правило |
|---|---|---|
| `chunk` | `Chunk` | источник |
| `score` | `float` 0..1 | нормализованный скор (RRF) |
| `rank` | `int` ≥1 | позиция в выдаче |

### SourceRef (то, что уходит в HTTP-ответ)

| Поле | Тип | Правило |
|---|---|---|
| `source` | `str` | имя документа |
| `paragraph_start` / `paragraph_end` | `int` ≥1 | как в `Chunk` |
| `text` | `str` | полный текст фрагмента |

### Answer

| Поле | Тип | Правило |
|---|---|---|
| `answer` | `str` | непустой; при отказе — стандартная формулировка |
| `grounded` | `bool` | `false` ⇒ отказ |
| `used_chunk_ids` | `list[str]` | только из переданных фрагментов; при отказе пуст |
| `sources` | `list[SourceRef]` | фрагменты, попавшие в ответ; при отказе пуст |

## Состояние графа (`backend/src/v3/domain/graph_state.py`, `TypedDict`)

| Ключ | Тип | Кто пишет |
|---|---|---|
| `request_id` | `str` | entrypoint |
| `question` | `str` | entrypoint |
| `k` | `int` | entrypoint (по умолчанию `retriever_k`) |
| `retrieved` | `list[RetrievedChunk]` | узел `retrieve` |
| `top_score` | `float` | узел `grade` |
| `refused` | `bool` | узел `grade` |
| `answer` | `Answer \| None` | узел `generate` |

Запись в state делает возвращаемое значение узла (фреймворк-корень), узел не мутирует state.

## Артефакты (`backend/src/v3/artifacts/`)

| Путь | Содержимое | Когда |
|---|---|---|
| `index/manifest.json` | sha256 документов, версия конфига чанкинга | старт |
| `index/chunks.jsonl` | все `Chunk` | построение индекса |
| `<request_id>/retrieved.json` | `list[RetrievedChunk]` | запрос |
| `<request_id>/prompt.json` | system + user + фрагменты | запрос |
| `<request_id>/answer.json` | сырой и распарсенный ответ, `refused`, `top_score` | запрос |
