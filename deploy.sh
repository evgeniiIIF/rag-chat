#!/bin/bash

set -e

# Конфигурация
SSH_KEY="$HOME/.ssh/cloud_ru"
SSH_USER="user1"
SSH_HOST="176.109.103.195"
REMOTE_DIR="rag-chat"  # Используем существующую директорию
LOCAL_DIR="."

echo "🚀 Начинаем деплой проекта на $SSH_HOST..."

# 1. Копируем файлы на сервер
echo "📁 Копируем файлы проекта на сервер..."
rsync -avz -e "ssh -i $SSH_KEY" \
  --exclude='.git' \
  --exclude='.vscode' \
  --exclude='node_modules' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='.ruff_cache' \
  --exclude='chroma_db' \
  --exclude='.env' \
  "$LOCAL_DIR/" "$SSH_USER@$SSH_HOST:~/$REMOTE_DIR/"

# 2. Копируем .env.prod как .env на сервере
echo "🔧 Копируем конфигурацию .env..."
scp -i "$SSH_KEY" .env.prod "$SSH_USER@$SSH_HOST:~/$REMOTE_DIR/.env"

# 3. Запускаем Docker Compose на сервере
echo "🐳 Запускаем Docker Compose в режиме production..."
ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" "cd $REMOTE_DIR && chmod 600 .env && docker compose -f docker-compose.prod.yml down || true"
ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" "cd $REMOTE_DIR && docker compose -f docker-compose.prod.yml up -d --build"

# 4. Проверяем состояние сервисов
echo "🔍 Проверяем состояние сервисов..."
ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" "cd $REMOTE_DIR && docker compose -f docker-compose.prod.yml ps"

# 5. Проверяем health check
echo "🏥 Проверяем health check..."
sleep 10
ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" "curl -sS http://localhost/api/health || echo 'Health check еще не готов, подождите...'"

echo ""
echo "✅ Деплой завершен!"
echo "🌐 Приложение доступно по адресу: http://$SSH_HOST/"
echo ""
echo "📋 Логи можно посмотреть командой:"
echo "ssh -i $SSH_KEY $SSH_USER@$SSH_HOST \"cd $REMOTE_DIR && docker compose -f docker-compose.prod.yml logs -f backend\""
echo ""
echo "🔄 Для обновления кода выполните этот скрипт повторно"