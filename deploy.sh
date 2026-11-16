#!/bin/bash

set -e

# Конфигурация
SSH_KEY="$HOME/.ssh/cloud_ru"
SSH_USER="user1"
SSH_HOST="176.109.103.195"
REMOTE_DIR="rag-chat"
LOCAL_DIR="."

echo "🚀 Начинаем деплой проекта на $SSH_HOST..."

# Проверяем наличие SSH ключа
if [ ! -f "$SSH_KEY" ]; then
    echo "❌ SSH ключ не найден: $SSH_KEY"
    exit 1
fi

# Спрашиваем пользователя о методе деплоя
echo ""
echo "Выберите метод деплоя:"
echo "1) Git (push/pull) - если настроен удалённый репозиторий"
echo "2) Rsync (копирование файлов) - по умолчанию"
echo ""
read -p "Выберите вариант [1/2] (по умолчанию: 2): " DEPLOY_METHOD
DEPLOY_METHOD=${DEPLOY_METHOD:-2}

case $DEPLOY_METHOD in
    1)
        # Метод 1: Git деплой
        echo "📤 Используем Git деплой..."
        
        # Проверяем, есть ли удалённый репозиторий
        if ! git remote -v | grep -q "origin"; then
            echo "❌ Удалённый репозиторий не настроен. Настройте сначала:"
            echo "   git remote add origin <ваш-repo-url>"
            exit 1
        fi
        
        echo "Пушим изменения в origin/main..."
        git push origin main
        
        echo "Пулим на сервере..."
        ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" "cd $REMOTE_DIR && git pull origin main"
        ;;
    2)
        # Метод 2: Rsync деплой
        echo "📁 Используем Rsync деплой..."
        
        # Копируем файлы на сервер
        rsync -avz -e "ssh -i $SSH_KEY" \
          --exclude='.git' \
          --exclude='.vscode' \
          --exclude='node_modules' \
          --exclude='__pycache__' \
          --exclude='.pytest_cache' \
          --exclude='.ruff_cache' \
          --exclude='chroma_db' \
          --exclude='.env' \
          --exclude='*.log' \
          --exclude='frontend/dist' \
          "$LOCAL_DIR/" "$SSH_USER@$SSH_HOST:~/$REMOTE_DIR/"
        
        # Копируем .env.prod как .env на сервере (если существует)
        if [ -f ".env.prod" ]; then
            echo "🔧 Копируем конфигурацию .env.prod..."
            scp -i "$SSH_KEY" .env.prod "$SSH_USER@$SSH_HOST:~/$REMOTE_DIR/.env"
        else
            echo "⚠️  Файл .env.prod не найден, пропускаем..."
        fi
        ;;
    *)
        echo "❌ Неверный выбор"
        exit 1
        ;;
esac

# Собираем фронтенд на сервере (всегда)
echo "🏗️  Собираем фронтенд на сервере..."
ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" "cd $REMOTE_DIR/frontend && npm ci --only=production && npm run build"

# Запускаем Docker Compose на сервере
echo "🐳 Перезапускаем Docker контейнеры..."
ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" "cd $REMOTE_DIR && docker compose -f docker-compose.prod.yml down || true"
ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" "cd $REMOTE_DIR && docker compose -f docker-compose.prod.yml up -d --build"

# Проверяем состояние сервисов
echo "🔍 Проверяем состояние сервисов..."
ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" "cd $REMOTE_DIR && docker compose -f docker-compose.prod.yml ps"

# Проверяем доступность приложения
echo "🏥 Проверяем доступность приложения..."
sleep 5
if ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" "curl -s -o /dev/null -w '%{http_code}' http://localhost" | grep -q "200"; then
    echo "✅ Приложение успешно запущено!"
else
    echo "⚠️  Приложение запущено, но проверка статуса не удалась"
fi

echo ""
echo "✅ Деплой завершен!"
echo "🌐 Приложение доступно по адресу: http://$SSH_HOST/"
echo ""
echo "📋 Для просмотра логов:"
echo "ssh -i $SSH_KEY $SSH_USER@$SSH_HOST \"cd $REMOTE_DIR && docker compose -f docker-compose.prod.yml logs -f\""