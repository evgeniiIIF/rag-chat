# Frontend · RAG Chat

React 18 + Vite + TypeScript strict + zod + react-query + Tailwind CSS.

## Команды

- \`npm install\` — зависимости
- \`npm run dev\` — dev-сервер (Vite, hot-reload)
- \`npm run build\` — production-сборка
- \`npm run check\` — eslint + tsc --noEmit + vitest
- \`npm run e2e\` — Playwright (требует \`npx playwright install chromium\`)

## Слои (rules/react.md)

- \`app/\` — composition root, env, theme (light/dark)
- \`shared/api/\` — HttpClient + interceptors (CSRF, Unauthorized)
- \`shared/ui/\` — UI-атомы (UIButton, UIInput)
- \`components/\` — ChatMessageList
- \`features/chat/\` — типы (zod), api, useChat (react-query)
- \`pages/\` — ChatPage

## UI

- **Тёмная/светлая тема** с переключателем (☀️/🌙 в шапке).
- **ChatGPT-style**: пузыри сообщений, аватарки, индикатор «печатает…».
- **Tailwind CSS** + inline-стили для инпута (гарантия контраста).

## Env

См. \`.env.example\`. Vite пробрасывает только переменные с префиксом \`VITE_\`.
