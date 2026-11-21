# Research: v3 на LangGraph — что берём из пакетов

**Дата**: 2026-11-21 · **Спека**: [spec.md](./spec.md) · **План**: [plan.md](./plan.md)

## R1. Загрузка документа

- Решение: `langchain_community.directory.DirectoryLoader` с `Docx2txtLoader`, glob `*.docx`.
- Почему не свой код: поддержка glob/метаданных/ошибок уже есть; свой парсер `.docx` — дублирование.
- Наш код: обёртка `infrastructure/loader.py` (путь из конфига, метаданные `source`, `mtime`, sha256).

## R2. Разбиение на фрагменты

- Решение: `RecursiveCharacterTextSplitter` (500/100 из `.env.example`), метаданные
  `paragraph_start/paragraph_end` вычисляются по позиции чанка в исходном тексте.
- Почему не свой код: иерархия разделителей и overlap уже реализованы.
- Артефакт: `artifacts/index/chunks.jsonl` — по чанку на строку (id, source, порядок, границы, текст).

## R3. Индекс и поиск

- Решение: `langchain_chroma.Chroma` + `OpenAIEmbeddings` (`langchain_openai`) для векторов;
  `BM25Retriever` (`langchain_community`) по тем же документам; `EnsembleRetriever` (RRF) для гибрида.
- Почему коробка: персистентность, фильтры и ранжирование реализованы; свой скор — источник регрессий.
- Конфиг: `retriever_k=3`, `score_threshold=0.35`, веса 0.5/0.5.
- Инкрементальность: sha256 документов в `artifacts/index/manifest.json`; совпал — индекс не перестраиваем.

## R4. Отказ от ответа (честный «не знаю»)

- Решение: два уровня — (а) числовой гейт в узле `grade`: нет кандидатов или лучший скор ниже
  `score_threshold` → `refused=True`, генерация не вызывается; (б) структурный вывод модели
  `Answer {answer, grounded: bool, used_chunk_ids}` через `ChatOpenAI.with_structured_output`
  (pydantic-схема); `grounded=False` → отдаём стандартный отказ.
- Почему не свой regex/FSM: поведение задаётся схемой ответа и порогом, а не правилами на строках.

## R5. Генерация ответа

- Решение: `ChatOpenAI` (`temperature=0`, `max_tokens=800`) + `ChatPromptTemplate`
  (`system` = «отвечай только по фрагментам, иначе grounded=false», `user` = вопрос + нумерованные фрагменты).
- Почему коробка: ретраи, таймауты, токенайзинг — в клиенте; свой HTTP-клиент запрещён конституцией.
- Артефакт: `artifacts/<request_id>/prompt.json` и `answer.json` (сырой ответ + распарсенный).

## R6. Граф запроса

- Решение: `langgraph.graph.StateGraph` с `TypedDict`-состоянием: `retrieve → grade → (generate | END)`,
  `compile()` один раз при старте, `ainvoke` на запрос.
- Почему не `create_react_agent`: по спеке один детерминированный проход без выбора инструментов;
  агентский цикл добавил бы недетерминизм и лишние вызовы модели без пользы для качества.
  Решение зафиксировано как осознанное отклонение от «агентского» варианта, коробочный API графа соблюдён.
- Checkpointer не подключаем: память диалога вне области v3 (spec, Assumptions).

## R7. Оценка качества

- Решение: `ragas` (faithfulness, answer_relevancy, context_precision) на golden set v2
  (`backend/eval/golden_set.json`), запуск — отдельной командой, не в `make check`.
- Baseline: faithfulness 0.845 → цель ≥0.90 (SC-001).
