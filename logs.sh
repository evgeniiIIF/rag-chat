#!/bin/bash

set -e

# Конфигурация
SSH_KEY="$HOME/.ssh/cloud_ru"
SSH_USER="user1"
SSH_HOST="176.109.103.195"
REMOTE_DIR="rag-chat"

echo "📋 Просмотр логов приложения на $SSH_HOST..."

# Проверяем наличие SSH ключа
if [ ! -f "$SSH_KEY" ]; then
    echo "❌ SSH ключ не найден: $SSH_KEY"
    exit 1
fi

# Спрашиваем какие логи показывать
echo ""
echo "Выберите логи для просмотра:"
echo "1) Все сервисы"
echo "2) Frontend"
echo "3) Backend"
echo "4) Nginx"
echo ""
read -p "Выберите вариант [1/2/3/4] (по умолчанию: 1): " LOG_CHOICE
LOG_CHOICE=${LOG_CHOICE:-1}

case $LOG_CHOICE in
    1)
        SERVICE=""
        echo "📊 Показываю логи всех сервисов..."
        ;;
    2)
        SERVICE="frontend"
        echo "🌐 Показываю логи фронтенда..."
        ;;
    3)
        SERVICE="backend"
        echo "⚙️  Показываю логи бэкенда..."
        ;;
    4)
        SERVICE="nginx"
        echo "🔧 Показываю логи nginx..."
        ;;
    *)
        SERVICE=""
        echo "📊 Показываю логи всех сервисов..."
        ;;
esac

# Показываем логи
if [ -z "$SERVICE" ]; then
    ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" "cd $REMOTE_DIR && docker compose -f docker-compose.prod.yml logs -f"
else
    ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" "cd $REMOTE_DIR && docker compose -f docker-compose.prod.yml logs -f $SERVICE"
fi