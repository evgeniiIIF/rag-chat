<!--
Sync Impact Report
- Version change: (none) → 1.0.0 (initial ratification)
- Modified principles: n/a (initial)
- Added sections: Core Principles (I–VI), Технологические ограничения, Процесс разработки, Governance
- Removed sections: none
- Templates checked: spec-template ✔, plan-template ✔, tasks-template ✔ (no constitution-dependent tokens changed)
- Deferred items: none; функциональные требования v3 выносятся в /speckit.specify
-->

# Rag Chat v3 Constitution

Правила проекта `rag_chat` (переписывание бэкенда на LangGraph в каталоге `v3/`). Источник
общих правил — `~/.pi/agent/rules/` (`workflow.md`, `chains.md`, `architecture.md`, `python.md`,
`types.md`, `testing.md`, `infra.md`). Конституция уточняет их для этого проекта и имеет приоритет
при конфликте.

## Core Principles

### I. Коробочное прежде своего (NON-NEGOTIABLE)

Поведение агента реализуется средствами пакета LangGraph/LangChain: `create_react_agent`,
`ToolNode`, `tools_condition`, `checkpointer`, `interrupt`, `Command`, `stream`, `Send`, prebuilt
retrievers (`BM25Retriever`, `EnsembleRetriever`, `MultiQueryRetriever`), loaders/splitters,
`Chroma`, `with_structured_output`. Свой код пишется только тогда, когда в пакете нет решения;
каждый такой случай фиксируется в `spec.md` и `plan.md` строкой «почему не коробка» и
согласуется с пользователем до реализации. Самописные FSM диалога, ручные regex-правила
поведения и собственные циклы вызова модели запрещены.

**Rationale**: коробочные узлы отлажены, задокументированы и обновляются вместе с пакетом;
свой код в поведении агента — источник неявных багов и регрессий качества.

### II. Наблюдаемость каждого шага (NON-NEGOTIABLE)

Каждый узел графа логирует вход и выход в структурированном виде (JSON) и складывает
артефакты в `v3/artifacts/`: полученные чанки (`chunks/*.jsonl`), результаты поиска, итоговый
промпт, ответ модели. Пользователь обязан видеть, что именно узел получил и что вернул.
Шаг, результат которого нельзя посмотреть глазами, не принимается.

**Rationale**: цель работы — не только рабочий сервис, но и понимание каждого этапа пайплайна.

### III. Работа только по цепочке пульта

Единица работы — шаг в `docs/chains/v3.md` (нотация `~/.pi/agent/rules/chains.md`, цикл
skill `chain-control`): шаг ⬜→🚧 + список файлов → «да» → одна правка → `make check` →
сверка с `git diff` → ✅ + журнал. Нет шага в пульте — нет правки кода; изменённый код без
обновлённого пульта в том же ответе недействителен.

**Rationale**: пошаговый контроль исключает «большой взрыв» и позволяет объяснять каждый узел.

### IV. Строгие границы типов

Python 3.12. Все внешние границы (env, HTTP, файлы, JSON) описываются pydantic v2 моделями;
`mypy --strict` обязателен для `src`; `Any`, непараметризованные `dict`/`list` на границе и
`# type: ignore` без ссылки на issue запрещены. Зависимости — только `uv` + `uv.lock`.

**Rationale**: parse-don't-validate; ошибки ловятся на границе, а не в середине пайплайна.

### V. Изолированная замена, контракт фронтенда неизменен

v3 живёт в `v3/` как самостоятельный сервис со своим `pyproject.toml`; каталоги `backend/`,
`frontend/`, `eval/`, `docker-compose*.yml` не изменяются без отдельного согласования.
HTTP-контракт (`POST /api/chat`, стриминг и формат ответа) совместим с текущим фронтендом —
фронтенд не трогаем.

**Rationale**: старый сервис остаётся рабочей точкой отката; фронтенд не должен стать
заложником переписывания.

### VI. Единая проверка и оценка качества

Definition of Done шага: `make check` (ruff check + ruff format --check + mypy --strict +
pytest с покрытием нового кода ≥80 %), плюс `docker compose` не запускается агентом —
пользователь запускает строку сам. Качество ответов проверяется `ragas` на golden set;
снижение faithfulness относительно зафиксированного baseline — регрессия.

**Rationale**: без автоматической проверки «шаг готов» превращается в мнение агента.

## Технологические ограничения

- Стек: Python 3.12, LangGraph (граф, state, checkpointer, prebuilt agent), LangChain
  (loaders, splitters, embeddings, vectorstore, retrievers), Chroma, FastAPI, pydantic v2,
  `pydantic-settings` (единственное место чтения env), `uv` (lock в репозитории).
- Слои по `~/.pi/agent/rules/architecture.md`: `api/` → `services/` (узлы графа и use-case)
  → `domain/` → `infrastructure/`; сборка графа — в `bootstrap`/composition root, без
  бизнес-логики.
- Секреты только из env через `core/config`; логи без ключей и содержимого документов.
- Внешние вызовы (LLM, эмбеддинги) — через адаптеры LangChain, не через самописный HTTP.

## Процесс разработки

1. `/speckit.constitution` — этот файл; изменения только через амендмент (см. Governance).
2. `/speckit.specify` — `specs/<NNN>-v3/spec.md`: что и зачем, без технологий; каждый
   функциональный пункт проверяем.
3. `/speckit.clarify` — снятие неоднозначностей до плана.
4. `/speckit.plan` — макро-цепочка и дерево файлов → пульт `docs/chains/v3.md`
   (шаги = узлы пайплайна: ingest → split → embed/index → retrieve → generate → gate).
5. `/speckit.tasks` — отдельный `tasks.md` не ведём: задачи = шаги пульта.
6. `/speckit.implement` — цикл `chain-control`, одна правка за шаг, отчёт с хвостом `make check`.
7. `/speckit.analyze` / `/speckit.converge` — сверка спеки, пульта и кода; отчёт о расхождениях.

## Governance

Конституция выше остальных практик; конфликт с проектным `AGENTS.md` решает пульт
`docs/chains/<feature>.md`, конфликт с `~/.pi/agent/rules/` — этот файл.

- Поправка: предложение → rationale → версия → согласование с пользователем → запись в файл
  одним изменением вместе с отчётом Sync Impact.
- Версионирование (semver): MAJOR — удаление/переопределение принципа; MINOR — новый принцип
  или существенное расширение; PATCH — уточнение формулировок.
- Обязательная проверка соответствия на каждом шаге: принцип I (коробка или обоснование),
  принцип II (артефакты узла), принцип III (пульт обновлён), принцип VI (`make check`).

**Version**: 1.0.0 | **Ratified**: 2026-11-21 | **Last Amended**: 2026-11-21
