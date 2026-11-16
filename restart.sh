#!/bin/bash

set -e

# Конфигурация
SSH_KEY="$HOME/.ssh/cloud_ru"
SSH_USER="user1"
SSH_HOST="176.109.103.195"
REMOTE_DIR="rag-chat"

echo "🔄 Перезапуск приложения на $SSH_HOST..."

# Проверяем наличие SSH ключа
if [ ! -f "$SSH_KEY" ]; then
    echo "❌ SSH ключ не найден: $SSH_KEY"
    exit 1
fi

# Перезапускаем контейнеры
echo "🐳 Перезапускаем Docker контейнеры..."
ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" "cd $REMOTE_DIR && docker compose -f docker-compose.prod.yml restart"

# Проверяем состояние сервисов
echo "🔍 Проверяем состояние сервисов..."
ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" "cd $REMOTE_DIR && docker compose -f docker-compose.prod.yml ps"

echo ""
echo "✅ Перезапуск завершен!"
echo "🌐 Приложение доступно по адресу: http://$SSH_HOST/"