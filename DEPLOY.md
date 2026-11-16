# Деплой на VPS

Прод: docker-compose.prod.yml. nginx (80) -> frontend (статика) + /api -> backend (:8000).
ChromaDB в volume chroma_db; документы ./backend/data:ro.
Node на VPS НЕ нужен — фронт собирается в frontend/Dockerfile (multi-stage).

## 1. Быстрый старт (локально)

    cp .env.example .env
    chmod 600 .env
    ./deploy.sh

Флаги:

| Флаг | Что делает |
|------|------------|
| --first    | на VPS создать .env из .env.example, если его нет (первый деплой) |
| --no-push  | не пушить локально (код на remote уже обновлён) |
| --branch b | ветка (default main) |

Переменные: SSH_KEY SSH_USER SSH_HOST REMOTE_DIR BRANCH COMPOSE_FILE.

## 2. Первый деплой нового VPS

1. На VPS: Docker + compose (curl -fsSL https://get.docker.com | sh), usermod -aG docker $USER, перелогин.
2. Клонировать репо на VPS:

       git clone <repo-url> ~/rag-chat

3. Локально:

       ./deploy.sh --first

4. На VPS заполнить ~/rag-chat/.env (BACKEND_API_KEY, BACKEND_LLM_MODEL, NGINX_HTTP_PORT=80), chmod 600 .env.
5. ./deploy.sh --no-push — пересборка с реальными ключами и health-check.

Firewall:

    sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw enable

## 3. Обновление прода

    ./deploy.sh

Шаги:

1. git push origin main — локально.
2. ssh $SSH_USER@$SSH_HOST — переход на VPS.
3. docker compose -f docker-compose.prod.yml down --remove-orphans — стоп и удаление контейнеров.
4. git fetch --all --prune + git reset --hard origin/main + git clean -fdx -e .env — все локальные изменения на VPS сносятся, код = origin; .env сохраняется.
5. [ -f .env ] || cp .env.example .env — гарантия наличия env (при --first).
6. docker compose -f docker-compose.prod.yml build --pull — свежие образы.
7. docker compose -f docker-compose.prod.yml up -d --remove-orphans — запуск.
8. curl -fsS http://localhost/api/health (10 попыток x 3s) + compose ps.

prune не используется: обновление достигается down --remove-orphans + build --pull + up -d --remove-orphans; volume chroma_db сохраняется.

## 4. Ручные шаги (то же, без скрипта)

    # локально
    git push origin main

    # на VPS
    ssh -i ~/.ssh/cloud_ru user1@176.109.103.195
    cd ~/rag-chat
    docker compose -f docker-compose.prod.yml down --remove-orphans
    git fetch --all --prune
    git reset --hard origin/main
    git clean -fdx -e .env
    [ -f .env ] || cp .env.example .env
    docker compose -f docker-compose.prod.yml build --pull
    docker compose -f docker-compose.prod.yml up -d --remove-orphans
    curl -fsS http://localhost/api/health && docker compose -f docker-compose.prod.yml ps

## 5. Проверка

    curl -sS http://<IP>/api/health
    curl -sS -X POST http://<IP>/api/chat \
      -H "Content-Type: application/json" \
      -d {"question":"Что при банкротстве?"} | python3 -m json.tool --no-ensure-ascii

UI: http://<IP>/.

## 6. Диагностика

    ssh -i ~/.ssh/cloud_ru user1@176.109.103.195 "cd ~/rag-chat && docker compose -f docker-compose.prod.yml ps"
    ssh -i ~/.ssh/cloud_ru user1@176.109.103.195 "cd ~/rag-chat && docker compose -f docker-compose.prod.yml logs -f --tail=100 backend"
    ssh -i ~/.ssh/cloud_ru user1@176.109.103.195 "df -h && free -m"

## 7. HTTPS (Let us Encrypt)

    sudo apt install -y certbot
    sudo certbot certonly --webroot -w /var/lib/docker/volumes/rag_chat_certbot_www/_data -d <домен> --email <email> --agree-tos -n
    sudo systemctl enable --now certbot.timer

Добавить в nginx/conf.d/prod.conf server-блок на 443, в docker-compose.prod.yml ports: 80:80, 443:443 + bind /etc/letsencrypt. Затем ./deploy.sh --no-push.

## 8. Безопасность

- .env в .gitignore, chmod 600, не логируется.
- backend наружу не публикуется (expose, не ports).
- SSH только по ключу (PasswordAuthentication no).
- .env.prod с реальным ключом не держать в репозитории — только на VPS.
