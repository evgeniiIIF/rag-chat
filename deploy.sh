#!/usr/bin/env bash
# deploy.sh — push → ssh → disk-preflight → down → reset+clean → build --pull → up → health
set -euo pipefail

SSH_KEY="${SSH_KEY:-$HOME/.ssh/cloud_ru}"
SSH_USER="${SSH_USER:-user1}"
SSH_HOST="${SSH_HOST:-176.109.103.195}"
REMOTE_DIR="${REMOTE_DIR:-rag-chat}"
BRANCH="${BRANCH:-main}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
DISK_CLEAN_THRESHOLD="${DISK_CLEAN_THRESHOLD:-85}"

usage() {
  cat <<USAGE
usage: ./deploy.sh [--no-push] [--branch <b>] [--first]
  --no-push        skip git push
  --branch <b>     git branch (default: main)
  --first          on VPS: cp .env.example .env if .env missing
  --follow         после health-check: стрим docker compose logs -f
env:
  SSH_KEY SSH_USER SSH_HOST REMOTE_DIR BRANCH COMPOSE_FILE DISK_CLEAN_THRESHOLD
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
die() { printf "\033[1;31m✖\033[0m %s\n" "$*" >&2; exit 1; }

[ -f "$SSH_KEY" ] || die "ssh key not found: $SSH_KEY"

if [ "$NO_PUSH" -eq 0 ]; then
  log "git push origin $BRANCH"
  git push origin "$BRANCH"
  ok "pushed"
fi

log "ssh $SSH_USER@$SSH_HOST → remote deploy (trace + лог на VPS)"
ssh -i "$SSH_KEY" \
  -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=4 \
  "$SSH_USER@$SSH_HOST" bash -s -- \
  "$REMOTE_DIR" "$BRANCH" "$COMPOSE_FILE" "$FIRST" "$DISK_CLEAN_THRESHOLD" "$FOLLOW" <<'REMOTE'
set -euo pipefail

REMOTE_DIR="$1"; BRANCH="$2"; COMPOSE_FILE="$3"; FIRST="$4"; TH="$5"; FOLLOW="${6:-0}"

DEPLOY_LOG_DIR="${DEPLOY_LOG_DIR:-$HOME/.ragchat-deploy/logs}"
mkdir -p "$DEPLOY_LOG_DIR"
DEPLOY_LOG="$DEPLOY_LOG_DIR/deploy-$(date +%Y%m%d-%H%M%S).log"
exec > >(stdbuf -oL tee -a "$DEPLOY_LOG") 2>&1

log()  { printf "  \033[1;36m▸\033[0m %s\n" "$*"; }
ok()   { printf "  \033[1;32m✔\033[0m %s\n" "$*"; }
warn() { printf "  \033[1;33m!\033[0m %s\n" "$*"; }

dump_diag() {
  [ -n "${COMPOSE_FILE:-}" ] && [ -f "${COMPOSE_FILE:-}" ] || return 0
  echo "  ───── docker compose ps -a ─────"
  docker compose -f "$COMPOSE_FILE" ps -a 2>&1 | sed "s/^/    /" || true
  echo "  ───── docker compose logs --tail=80 ─────"
  docker compose -f "$COMPOSE_FILE" logs --tail=80 2>&1 | sed "s/^/    /" || true
}

die()  { printf "  \033[1;31m✖\033[0m %s\n" "$*" >&2; dump_diag; exit 1; }

PS4="+ [\t] L${BASH_SOURCE##*/}:${LINENO}> "
set -x
trap 'rc=$?; printf "  \033[1;31m✖\033[0m FAIL exit=%s строка=%s: %s\n" "$rc" "$LINENO" "$BASH_COMMAND" >&2; dump_diag; exit "$rc"' ERR

disk_pct()  { df --output=pcent / | tail -1 | tr -dc "0-9"; }
disk_info() { df -h / | tail -1 | awk "{print \$3\" / \"\$2\" (\"\$5\")\"}"; }

echo "──────────────────────────────────────────────"
echo " host: $(hostname) · dir: $REMOTE_DIR · branch: $BRANCH"
echo "──────────────────────────────────────────────"

[ -n "$REMOTE_DIR" ] || die "REMOTE_DIR empty"
cd "$REMOTE_DIR" || die "cd $REMOTE_DIR failed"

log "preflight: disk"
D0=$(disk_pct)
echo "    /: $(disk_info)"
if [ "$D0" -ge "$TH" ]; then
  warn "disk ≥ ${TH}% → prune images + build cache"
  docker image prune -af 2>&1 | tail -n 3 | sed "s/^/    /" || true
  docker builder prune -af 2>&1 | tail -n 3 | sed "s/^/    /" || true
  ok "after prune: $(disk_info)"
else
  ok "disk ok: ${D0}% < ${TH}%"
fi

log "down --remove-orphans"
docker compose -f "$COMPOSE_FILE" down --remove-orphans 2>&1 | sed "s/^/    /" || true
ok "containers stopped"

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

log "build --pull (stream)"
docker compose -f "$COMPOSE_FILE" build --pull --progress=plain 2>&1 | stdbuf -oL sed -u "s/^/    /"
ok "images built"

log "up -d --wait --remove-orphans"
docker compose -f "$COMPOSE_FILE" up -d --wait --remove-orphans 2>&1 | sed "s/^/    /"
ok "containers started (compose --wait: healthchecks зелёные)"

log "health check"
HITS=0
for i in $(seq 1 40); do
  if curl -fsS "http://localhost/api/health" >/dev/null 2>&1; then
    ok "/api/health ok (attempt $i)"
    HITS=1
    break
  fi
  warn "waiting ($i/40)…"
  sleep 3
done
[ "$HITS" -eq 1 ] || die "health check failed after 40 tries (~120s, start_period=60s)"

log "final state"
docker compose -f "$COMPOSE_FILE" ps 2>&1 | sed "s/^/    /"
echo "    /: $(disk_info)"
echo "    deploy log на VPS: $DEPLOY_LOG"
[ "$FOLLOW" = "1" ] || echo "    все логи: ssh -tt -i \$SSH_KEY \$SSH_USER@\$SSH_HOST \"cd $REMOTE_DIR && docker compose -f $COMPOSE_FILE logs -f\""
ok "deploy done"

if [ "$FOLLOW" = "1" ]; then
  log "docker compose logs -f (Ctrl-C — выйти, деплой уже завершён)"
  docker compose -f "$COMPOSE_FILE" logs -f --tail=100
fi
REMOTE

ok "deployed: http://$SSH_HOST/"
echo "   logs: ssh -i $SSH_KEY $SSH_USER@$SSH_HOST \"cd $REMOTE_DIR && docker compose -f $COMPOSE_FILE logs -f\""
