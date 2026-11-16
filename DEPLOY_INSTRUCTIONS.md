# Инструкции по деплою

## Быстрый деплой

Просто выполните команду:

```bash
./deploy.sh
```

Скрипт предложит выбрать метод деплоя:
1. **Git** - если настроен удалённый репозиторий
2. **Rsync** - копирование файлов напрямую (по умолчанию)

## Процесс деплоя

Скрипт выполняет следующие шаги:

### При выборе Git:
1. Пушит изменения в удалённый репозиторий (`git push origin main`)
2. Пулит изменения на сервере (`git pull origin main`)

### При выборе Rsync:
1. Копирует все файлы проекта на сервер (исключая ненужные директории)
2. Копирует файл `.env.prod` как `.env` на сервере

### Общие шаги (для обоих методов):
3. Собирает фронтенд на сервере (`npm ci --only=production && npm run build`)
4. Останавливает старые контейнеры (`docker compose down`)
5. Запускает новые контейнеры (`docker compose up -d --build`)
6. Проверяет состояние сервисов
7. Проверяет доступность приложения

## Требования

### Локально:
- Установленный Git
- Настроенный SSH ключ для доступа к серверу
- Файл SSH ключа: `~/.ssh/cloud_ru`
- Node.js для локальной разработки (опционально)

### На сервере:
- Установленный Docker и Docker Compose
- Node.js (для сборки фронтенда)
- Git (если используется Git метод)

## Настройка Git деплоя

Если хотите использовать Git деплой:

1. Создайте удалённый репозиторий (GitHub, GitLab, etc.)
2. Добавьте remote:
   ```bash
   git remote add origin <ваш-repo-url>
   ```
3. Запушите код:
   ```bash
   git push -u origin main
   ```
4. На сервере убедитесь, что репозиторий клонирован в `~/rag-chat`

## Ручной деплой (если скрипт не работает)

### 1. Копирование файлов:
```bash
rsync -avz -e "ssh -i ~/.ssh/cloud_ru" \
  --exclude='.git' --exclude='node_modules' --exclude='__pycache__' \
  --exclude='chroma_db' --exclude='.env' \
  ./ user1@176.109.103.195:~/rag-chat/
```

### 2. Сборка фронтенда на сервере:
```bash
ssh -i ~/.ssh/cloud_ru user1@176.109.103.195 "cd rag-chat/frontend && npm ci --only=production && npm run build"
```

### 3. Запуск контейнеров:
```bash
ssh -i ~/.ssh/cloud_ru user1@176.109.103.195 "cd rag-chat && docker compose -f docker-compose.prod.yml down"
ssh -i ~/.ssh/cloud_ru user1@176.109.103.195 "cd rag-chat && docker compose -f docker-compose.prod.yml up -d --build"
```

## Устранение проблем

### Проблема с правами SSH ключа
```bash
chmod 600 ~/.ssh/cloud_ru
```

### Проблема с Docker на сервере
Проверьте, что Docker установлен и запущен:
```bash
ssh -i ~/.ssh/cloud_ru user1@176.109.103.195 "docker --version && docker compose version"
```

### Проблема со сборкой фронтенда
Если Tailwind стили не работают, убедитесь что в Dockerfile фронтенда копируются конфигурационные файлы:
```dockerfile
COPY tsconfig.json vite.config.ts tailwind.config.js postcss.config.cjs index.html ./
```

## Быстрые команды

### Просмотр логов:
```bash
ssh -i ~/.ssh/cloud_ru user1@176.109.103.195 "cd rag-chat && docker compose -f docker-compose.prod.yml logs -f"
```

### Перезапуск одного сервиса:
```bash
ssh -i ~/.ssh/cloud_ru user1@176.109.103.195 "cd rag-chat && docker compose -f docker-compose.prod.yml restart frontend"
```

### Проверка статуса:
```bash
ssh -i ~/.ssh/cloud_ru user1@176.109.103.195 "cd rag-chat && docker compose -f docker-compose.prod.yml ps"
```
## Полезные скрипты

- `./deploy.sh` - полный деплой приложения
- `./restart.sh` - быстрый перезапуск контейнеров
- `./logs.sh` - просмотр логов с выбором сервиса
- `./query.sh` - отправка запросов к API (из корневой директории проекта)
