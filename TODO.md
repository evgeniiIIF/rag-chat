# TODO: Улучшения RAG Chat

## ✅ ЗАВЕРШЕНО: Передача профиля в AnswerGenerator

**Что сделано:**
1. Добавлен параметр `profile: Profile | None = None` в `AnswerGenerator.generate()`
2. Профиль форматируется в промпт: `"Профиль клиента: сумма долга: 500,000 ₽, город: Москва..."`
3. Обновлена цепочка `docs/chains/chat.md` — шаг 19 выполнен
4. Удалён TODO в `chat_service.py`

**Следующий шаг:** Тестирование и сборка (`make check`)

---

## 🚨 КРИТИЧНО: Сохранение истории диалогов

**Текущая проблема**
История диалогов хранится только в памяти фронтенда (React state). При перезагрузке страницы, открытии в новой вкладке или на другом устройстве история теряется.

**Почему это неправильно:**
1. **Потеря контекста**: Пользователь не может продолжить разговор после перезагрузки
2. **Многоустройственность**: Невозможно начать на телефоне, продолжить на ноутбуке
3. **Бизнес-логика**: Для контекстного чата по банкротству история критична
4. **UX**: Ожидание сохранения истории — стандарт для чатов

**Решение:**

### Backend (FastAPI)
1. **Session management**:
   ```python
   # session_store.py
   from typing import MutableMapping
   from datetime import datetime, timedelta
   import uuid
   from ..models.turn import Turn
   
   class SessionStore:
       def __init__(self, ttl_hours: int = 24, max_history: int = 50):
           self._sessions: MutableMapping[str, Session] = {}
           self._ttl = timedelta(hours=ttl_hours)
           self._max_history = max_history
       
       def get_or_create(self, session_id: str | None = None) -> tuple[str, list[Turn]]:
           # Возвращает (session_id, история)
           pass
       
       def append(self, session_id: str, turn: Turn) -> None:
           # Добавляет сообщение, обрезает историю, чистит старые сессии
           pass
   ```

2. **Изменение ChatService**:
   - Принимать `session_id` вместо `history` в запросе
   - Загружать историю из SessionStore
   - Сохранять новые сообщения после обработки

3. **Новый эндпоинт для очистки сессии**:
   ```
   DELETE /api/session/{session_id}
   ```

### Frontend (React)
1. **Генерация/сотхранение session_id**:
   ```typescript
   // localStorage или cookie
   const getSessionId = () => {
     let id = localStorage.getItem('session_id')
     if (!id) {
       id = crypto.randomUUID()
       localStorage.setItem('session_id', id)
     }
     return id
   }
   ```

2. **Изменение API запроса**:
   ```typescript
   // Было: { question, history }
   // Стало: { question, session_id }
   ```

3. **Кнопка "Новый чат"**:
   - Генерирует новый session_id
   - Очищает локальное состояние
   - (Опционально) вызывает DELETE на старую сессию

### Middleware (Nginx/Backend)
1. **CORS**: Разрешить заголовок `X-Session-ID`
2. **Rate limiting**: По session_id для предотвращения злоупотреблений

### Альтернативы
1. **Browser-only**: Сохранять всю историю в localStorage (простейшее, но не решает синхронизацию)
2. **Server + DB**: PostgreSQL/Redis для персистентного хранения
3. **JWT tokens**: Закодировать историю в токене (ограничено размером)

### Приоритет
**ВЫСОКИЙ**: Без этого система не production-ready для реальных пользователей.

---

## 📋 Прочие улучшения

### 1. Улучшение поиска
- [ ] Тюнинг эмбеддингов: Qwen3 → OpenAI/text-embedding-3
- [ ] Весовой гибридный поиск (BM25 + векторы)
- [ ] Reranking (Cohere/переранжировщики)

### 2. Мониторинг и логирование
- [ ] Prometheus метрики: запросы/ответы, latency, ошибки
- [ ] Структурированные логи с trace_id
- [ ] Дашборд Grafana

### 3. Безопасность
- [ ] Rate limiting (per IP/session)
- [ ] Input sanitization
- [ ] Защита от prompt injection

### 4. UX/UI
- [ ] Индикатор загрузки источников
- [ ] Предпросмотр документов (клик по source → preview)
- [ ] Темы (системная/светлая/тёмная)
- [ ] Экспорт диалога (PDF/текст)

### 5. Админка
- [ ] Просмотр активных сессий
- [ ] Статистика запросов
- [ ] Управление документами (upload/delete)

---

## 🏗️ Архитектурные долги

1. **Тестирование E2E**: Playwright тесты для полного пайплайна
2. **Миграции данных**: Версионирование индекса Chroma
3. **Health checks**: Проверка LLM API доступности
4. **Конфигурация**: Feature flags, A/B тестирование

---

## 📅 Примерная оценка

| Задача | Сложность | Время |
|--------|-----------|-------|
| Сохранение истории (MVP) | Низкая | 2-3 дня |
| Мониторинг | Средняя | 3-4 дня |
| Улучшение поиска | Высокая | 1-2 недели |
| Полная админка | Очень высокая | 2-3 недели |

---

*Обновлено: $(date)*  
*Приоритет: Сохранение истории → Безопасность → UX → Мониторинг*