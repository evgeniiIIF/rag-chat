#!/usr/bin/env bash
# deploy_v3.sh — push → ssh → disk-preflight → build backend (v3) → up backend → health
# деплоит ТОЛЬКО сервис backend (v3) из docker-compose.prod.yml: frontend и nginx не трогает
set -euo pipefail

SSH_KEY="${SSH_KEY:-$HOME/.ssh/cloud_ru}"
SSH_USER="${SSH_USER:-user1}"
SSH_HOST="${SSH_HOST:-176.109.103.195}"
REMOTE_DIR="${REMOTE_DIR:-rag-chat}"
BRANCH="${BRANCH:-main}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
DISK_CLEAN_THRESHOLD="${DISK_CLEAN_THRESHOLD:-85}"

usage() {
  cat <<USAGE
usage: ./deploy_v3.sh         # обычный запуск: только backend (v3)
  (флаги ниже — только для исключений)
  --no-push        не трогать git (локальные коммиты уже на origin)
  --branch <b>     git branch (default: main)
  --first          on VPS: cp .env.example .env if .env missing
  --follow         после health-check: стрим docker compose logs -f backend
env:
  SSH_KEY SSH_USER SSH_HOST REMOTE_DIR BRANCH COMPOSE_FILE BACKEND_PORT DISK_CLEAN_THRESHOLD
USAGE
}

NO_PUSH=0
FIRST=0
FOLLOW=0
while [ $# -gt 0 ]; do
  case "$1" in
    --no-push) NO_PUSH=1; shift ;;
    --first)   FIRST=1; shift ;;
    --follow)  FOLLOW=1; shift ;;
    --branch)  BRANCH="${2:?--branch needs value}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage; exit 1 ;;
  esac
done

log() { printf "\033[1;36m▸\033[0m %s\n" "$*"; }
ok()  { printf "\033[1;32m✔\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m!\033[0m %s\n" "$*"; }
die() { printf "\033[1;31m✖\033[0m %s\n" "$*" >&2; exit 1; }

[ -f "$SSH_KEY" ] || die "ssh key not found: $SSH_KEY"

if [ "$NO_PUSH" -eq 0 ]; then
  log "git: автокоммит + push (флаги не нужны)"
  CUR="$(git rev-parse --abbrev-ref HEAD)"
  [ "$CUR" = "$BRANCH" ] || die "ты на ветке '$CUR', деплоим '$BRANCH' → git checkout $BRANCH"
  if [ -n "$(git status --porcelain)" ]; then
    warn "незакоммиченные изменения → коммичу сам: $(git status --porcelain | head -3 | tr '\n' ' ')"
    git add -A
    git commit -m "deploy v3: $(date +'%Y-%m-%d %H:%M')" | sed "s/^/    /"
    ok "committed"
  else
    ok "рабочее дерево чистое"
  fi
  git fetch origin "$BRANCH" 2>&1 | sed "s/^/    /" || true
  AHEAD="$(git rev-list --count "origin/$BRANCH..HEAD" 2>/dev/null || echo 1)"
  if [ "$AHEAD" = "0" ]; then
    ok "нечего пушить — origin уже актуален"
  else
    git push origin "$BRANCH" 2>&1 | sed "s/^/    /" || die "git push не прошёл (конфликт с origin/$BRANCH? сделай git pull --rebase)"
    ok "pushed ($AHEAD коммитов)"
  fi
fi

log "ssh $SSH_USER@$SSH_HOST → remote deploy v3 (trace + лог на VPS)"
ssh -i "$SSH_KEY" \
  -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=4 \
  "$SSH_USER@$SSH_HOST" bash -s -- \
  "$REMOTE_DIR" "$BRANCH" "$COMPOSE_FILE" "$FIRST" "$DISK_CLEAN_THRESHOLD" "$FOLLOW" "$BACKEND_PORT" <<'REMOTE'
set -euo pipefail

REMOTE_DIR="$1"; BRANCH="$2"; COMPOSE_FILE="$3"; FIRST="$4"; TH="$5"; FOLLOW="${6:-0}"
BACKEND_PORT="${7:-8000}"
SERVICE="backend"
# порт наружу только для backend: compose-файл не правим, кладём рядом override
OVERRIDE=".compose.v3.override.yml"

DEPLOY_LOG_DIR="${DEPLOY_LOG_DIR:-$HOME/.ragchat-deploy/logs}"
mkdir -p "$DEPLOY_LOG_DIR"
DEPLOY_LOG="$DEPLOY_LOG_DIR/deploy-v3-$(date +%Y%m%d-%H%M%S).log"
exec > >(stdbuf -oL tee -a "$DEPLOY_LOG") 2>&1

log()  { printf "  \033[1;36m▸\033[0m %s\n" "$*"; }
ok()   { printf "  \033[1;32m✔\033[0m %s\n" "$*"; }
warn() { printf "  \033[1;33m!\033[0m %s\n" "$*"; }

compose() { docker compose -f "$COMPOSE_FILE" -f "$OVERRIDE" "$@"; }

dump_diag() {
  [ -n "${COMPOSE_FILE:-}" ] && [ -f "${COMPOSE_FILE:-}" ] || return 0
  echo "  ───── docker compose ps -a ($SERVICE) ─────"
  compose ps -a "$SERVICE" 2>&1 | sed "s/^/    /" || true
  echo "  ───── docker compose logs --tail=80 ($SERVICE) ─────"
  compose logs --tail=80 "$SERVICE" 2>&1 | sed "s/^/    /" || true
}

die()  { printf "  \033[1;31m✖\033[0m %s\n" "$*" >&2; dump_diag; exit 1; }

PS4="+ [\t] L${BASH_SOURCE:-stdin}:${LINENO}> "
set -x
trap 'rc=$?; printf "  \033[1;31m✖\033[0m FAIL exit=%s строка=%s: %s\n" "$rc" "$LINENO" "$BASH_COMMAND" >&2; dump_diag; exit "$rc"' ERR

disk_mounts() {  # все реально используемые разделы: /, /home, $HOME
  { echo /; echo /home; echo "$HOME"; } | sort -u | while read -r m; do
    df --output=target,pcent "$m" 2>/dev/null | tail -1
  done
}
disk_max_pct() { disk_mounts | awk '{gsub("%","",$2); if ($2+0>m) m=$2+0} END {print m}'; }
disk_report()  { disk_mounts | sed "s/^/      /"; }

cleanup_disk() {  # volumes НЕ трогаем — иначе снесётся chroma_db
  if [ "${1:-0}" = "1" ]; then
    warn "агрессивная чистка: builder-кэш + неиспользуемые образы + журнал + apt"
    docker builder prune -af >/dev/null 2>&1 || true
    docker system prune -af >/dev/null 2>&1 || true
    sudo -n journalctl --vacuum-size=100M >/dev/null 2>&1 || true
    sudo -n apt-get clean >/dev/null 2>&1 || true
  else
    docker builder prune -f >/dev/null 2>&1 || true
    docker image prune -f >/dev/null 2>&1 || true
  fi
}

try_build() {
  compose build --pull --progress=plain "$SERVICE" 2>&1 | stdbuf -oL sed -u "s/^/    /"
}
build_with_retry() {
  try_build && return 0
  warn "build упал (частая причина = no space left on device) → чистка места и 1 повтор"
  cleanup_disk 1
  disk_report
  try_build
}
disk_info() { df -h / | tail -1 | awk "{print \$3\" / \"\$2\" (\"$5\")\"}"; }

echo "──────────────────────────────────────────────"
echo " host: $(hostname) · dir: $REMOTE_DIR · branch: $BRANCH"
echo " deploy: только $SERVICE (v3) · порт $BACKEND_PORT"
echo "──────────────────────────────────────────────"

[ -n "$REMOTE_DIR" ] || die "REMOTE_DIR empty"
cd "$REMOTE_DIR" || die "cd $REMOTE_DIR failed"

log "preflight: диск (все разделы)"
disk_report
P=$(disk_max_pct)
echo "    максимум: ${P}% (порог ${TH}%)"
cleanup_disk 0
if [ "${P:-0}" -ge "$TH" ]; then
  warn "есть раздел ≥ ${TH}% → агрессивная чистка ДО сборки"
  cleanup_disk 1
  disk_report
  [ "$(disk_max_pct)" -lt "$TH" ] || die "диск всё ещё ≥ ${TH}% — освободи место руками (список разделов выше)"
fi
ok "диск ок: $(disk_info)"

log "git fetch --prune · reset --hard · clean -fd (keep .env*)"
git fetch --all --prune 2>&1 | sed "s/^/    /" || true
git reset --hard "origin/$BRANCH" 2>&1 | sed "s/^/    /"
git clean -fd -e .env -e .env.prod 2>&1 | sed "s/^/    /" || true
ok "code at $(git rev-parse --short HEAD) · $(git log -1 --pretty=%s)"

if [ ! -f .env ]; then
  if [ "$FIRST" = "1" ]; then
    warn ".env missing → cp .env.example .env (заполни секреты!)"
    cp .env.example .env
  else
    die ".env missing (first deploy? run with --first)"
  fi
fi
ok ".env present"

log "override: только $SERVICE, порт $BACKEND_PORT → 8000"
cat > "$OVERRIDE" <<YAML
services:
  $SERVICE:
    ports:
      - "$BACKEND_PORT:8000"
YAML
ok "override written: $OVERRIDE"

log "build --pull $SERVICE (stream, авто-чистка + 1 повтор)"
build_with_retry
ok "image built"

log "up -d --wait $SERVICE (nginx и frontend не трогаем)"
compose up -d --wait --remove-orphans "$SERVICE" 2>&1 | sed "s/^/    /"
ok "container started (compose --wait: healthcheck зелёный)"

log "health check"
HITS=0
for i in $(seq 1 40); do
  if curl -fsS "http://localhost:$BACKEND_PORT/api/health" >/dev/null 2>&1; then
    ok "/api/health ok (attempt $i)"
    HITS=1
    break
  fi
  warn "waiting ($i/40)…"
  sleep 3
done
[ "$HITS" -eq 1 ] || die "health check failed after 40 tries (~120s, start_period=60s)"

log "final state"
compose ps "$SERVICE" 2>&1 | sed "s/^/    /"
echo "    /: $(disk_info)"
echo "    deploy log на VPS: $DEPLOY_LOG"
[ "$FOLLOW" = "1" ] || echo "    логи v3: ssh -tt -i \$SSH_KEY \$SSH_USER@\$SSH_HOST \"cd $REMOTE_DIR && docker compose -f $COMPOSE_FILE -f $OVERRIDE logs -f $SERVICE\""
ok "deploy v3 done"

if [ "$FOLLOW" = "1" ]; then
  log "docker compose logs -f $SERVICE (Ctrl-C — выйти, деплой уже завершён)"
  compose logs -f --tail=100 "$SERVICE"
fi
REMOTE

ok "deployed v3: http://$SSH_HOST:$BACKEND_PORT/api/health"
echo "   logs: ssh -i $SSH_KEY $SSH_USER@$SSH_HOST \"cd $REMOTE_DIR && docker compose -f $COMPOSE_FILE -f .compose.v3.override.yml logs -f backend\""
