# Деплой на VPS

Прод-запуск: `docker-compose.prod.yml` + `nginx/conf.d/prod.conf`.
Стек: nginx (80) → frontend (статика на :80) и /api → backend (:8000).
Индекс ChromaDB персистентный (volume `chroma_db`), документы монтируются `./backend/data:ro`.

## 0. Требования к VPS

- Ubuntu 22.04+ (или Debian 12+), 1 vCPU / 2 GB RAM минимум (LangChain+Chroma тянут ~1 GB).
- Открытые порты: 22 (SSH), 80 (HTTP), 443 (HTTPS).
- Домен (A-запись на IP сервера) — для HTTPS.

## 1. Установка Docker

\`\`\`bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"
# перелогиниться (выйти и зайти по SSH), чтобы применилась группа
docker --version
docker compose version
\`\`\`

## 2. Код и .env

\`\`\`bash
git clone <repo-url> rag_chat
cd rag_chat
cp .env.example .env
nano .env    # вписать BACKEND_API_KEY (ключ провайдера), при необходимости LLM/embedding модель
chmod 600 .env
\`\`\`

Ключи, которые **обязательно** заполнить в \`.env\`:
- \`BACKEND_API_KEY\` — ключ polza.ai (или другого OpenAI-совместимого провайдера).
- \`BACKEND_LLM_MODEL\` — существующая у провайдера модель (по умолчанию \`deepseek/deepseek-v3.2\`).
- \`NGINX_HTTP_PORT=80\` — для прода.

## 3. Первый запуск

\`\`\`bash
docker compose -f docker-compose.prod.yml up -d --build
# первый старт backend ~1.5 мин (индексация), следить:
docker compose -f docker-compose.prod.yml logs -f backend
\`\`\`

Готовность:
\`\`\`bash
curl -sS http://<IP-сервера>/api/health
curl -sS -X POST http://<IP-сервера>/api/chat \\
  -H "Content-Type: application/json" \\
  -d \x27{"question":"Что с детьми при банкротстве?"}\x27 | python3 -m json.tool --no-ensure-ascii
\`\`\`

UI: http://<IP-сервера>/ (порт 80).

## 4. Firewall (ufw)

\`\`\`bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
\`\`\`

## 5. HTTPS (Let\x27s Encrypt) — после того как HTTP работает

Вариант А: certbot вручную.

\`\`\`bash
sudo apt install -y certbot
# вебрут: сертификат без остановки nginx
sudo certbot certonly --webroot -w /var/lib/docker/volumes/rag_chat_certbot_www/_data -d <домен> --email <email> --agree-tos -n
\`\`\`

После получения сертификата — добавить в \`nginx/conf.d/prod.conf\` server-блок на 443 (файлы \`/etc/letsencrypt/live/<домен>/fullchain.pem\` и \`privkey.pem\`), смонтировать в nginx-volume:

\`\`\`yaml
# docker-compose.prod.yml → nginx.volumes
- /etc/letsencrypt:/etc/letsencrypt:ro
- certbot_www:/var/www/certbot:ro
\`\`\`

И порт:
\`\`\`yaml
ports:
  - "80:80"
  - "443:443"
\`\`\`

Потом:
\`\`\`bash
docker compose -f docker-compose.prod.yml up -d nginx
\`\`\`

Автообновление сертификата:
\`\`\`bash
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
\`\`\`

## 6. Обновление кода

\`\`\`bash
git pull
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
\`\`\`

Индекс сохраняется в volume \`chroma_db\`; переиндексация при изменении \`backend/data/*.docx\` — автоматически при старте (хэш-сравнение).

## 7. Логи и отладка

\`\`\`bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f --tail=100 backend
docker compose -f docker-compose.prod.yml logs -f --tail=50 nginx
\`\`\`

## 8. Безопасность (минимум)

- \`.env\` в \`.gitignore\` и \`chmod 600\` — не коммитить ключи.
- Не публиковать backend наружу (\`expose\` вместо \`ports\` — уже так).
- SSH: только по ключу (\`PasswordAuthentication no\` в \`/etc/ssh/sshd_config\`).
- Регулярно: \`docker compose ... pull && build && up -d\`.
