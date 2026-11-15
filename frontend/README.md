# Frontend · RAG Chat

React 18 + Vite + TS strict + zod + react-query.

## Команды

- `npm install` — зависимости
- `npm run dev` — dev-сервер
- `npm run check` — lint + types + unit + e2e

## Слои (rules/react.md)

- `app/` — composition root, env
- `shared/api/` — HttpClient + interceptors
- `shared/ui/` — UI-атомы
- `components/`, `layouts/`, `features/<name>/`, `pages/`
