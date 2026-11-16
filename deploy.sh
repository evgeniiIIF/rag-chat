#!/usr/bin/env bash
# deploy.sh — push → ssh → down → hard-reset+clean → build --pull → up → health. Без prune.
set -euo pipefail

SSH_KEY="${SSH_KEY:-$HOME/.ssh/cloud_ru}"
SSH_USER="${SSH_USER:-user1}"
SSH_HOST="${SSH_HOST:-176.109.103.195}"
REMOTE_DIR="${REMOTE_DIR:-rag-chat}"
BRANCH="${BRANCH:-main}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

usage() {
  cat <<USAGE
usage: ./deploy.sh [--no-push] [--branch <b>] [--first]
  --no-push        skip git push (remote code already updated)
  --branch <b>     git branch (default: main)
  --first          on VPS: cp .env.example .env if .env missing
env:
  SSH_KEY SSH_USER SSH_HOST REMOTE_DIR COMPOSE_FILE
USAGE
}

NO_PUSH=0
FIRST=0
while [ $# -gt 0 ]; do
  case "$1" in
    --no-push) NO_PUSH=1; shift ;;
    --first)   FIRST=1; shift ;;
    --branch)  BRANCH="${2:?--branch needs value}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage; exit 1 ;;
  esac
done

log() { printf "▸ %s\n" "$*"; }
die() { printf "✖ %s\n" "$*" >&2; exit 1; }

[ -f "$SSH_KEY" ] || die "ssh key not found: $SSH_KEY"

if [ "$NO_PUSH" -eq 0 ]; then
  log "git push origin $BRANCH"
  git push origin "$BRANCH"
fi

log "ssh $SSH_USER@$SSH_HOST → deploy"
ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" bash -s -- \
  "$REMOTE_DIR" "$BRANCH" "$COMPOSE_FILE" "$FIRST" <<'REMOTE'
set -euo pipefail

REMOTE_DIR="$1"
BRANCH="$2"
COMPOSE_FILE="$3"
FIRST="$4"

log() { printf "  ▸ %s\n" "$*"; }
die() { printf "  ✖ %s\n" "$*" >&2; exit 1; }

[ -n "$REMOTE_DIR" ] || die "REMOTE_DIR empty"
cd "$REMOTE_DIR" || die "cd $REMOTE_DIR failed"

log "down --remove-orphans"
docker compose -f "$COMPOSE_FILE" down --remove-orphans

log "git fetch --prune · reset --hard · clean -fd (keep .env*)"
git fetch --all --prune
git reset --hard "origin/$BRANCH"
git clean -fd -e .env -e .env.prod

if [ ! -f .env ]; then
  if [ "$FIRST" = "1" ]; then
    log ".env missing → cp .env.example .env (заполни секреты!)"
    cp .env.example .env
  else
    die ".env missing (first deploy? run with --first)"
  fi
fi

log "build --pull"
docker compose -f "$COMPOSE_FILE" build --pull

log "up -d --remove-orphans"
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

log "verify"
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS "http://localhost/api/health" >/dev/null 2>&1; then
    echo "  ✔ /api/health ok"
    break
  fi
  [ "$i" = "10" ] && die "health check failed after 10 tries"
  sleep 3
done
docker compose -f "$COMPOSE_FILE" ps
REMOTE

echo
echo "✅ deployed: http://$SSH_HOST/"
echo "   logs: ssh -i $SSH_KEY $SSH_USER@$SSH_HOST \"cd $REMOTE_DIR && docker compose -f $COMPOSE_FILE logs -f\""
