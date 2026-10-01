#!/usr/bin/env bash
# Copies this agent to the Oracle VM and (re)starts it. The VM's .env is never
# touched by a deploy: create it once with `scp .env` or on the VM itself.
set -euo pipefail

HOST="${AGENT_HOST:-129.146.79.96}"
USER_AT="${AGENT_USER:-ubuntu}@${HOST}"
KEY="${AGENT_KEY:-$HOME/.ssh/koya_oracle}"
DIR="agno-livekit-agent"
SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "$USER_AT")
HERE="$(cd "$(dirname "$0")" && pwd)"

"${SSH[@]}" "mkdir -p ~/$DIR/data && touch ~/$DIR/data/memory.db"
rsync -az -e "ssh -i $KEY -o StrictHostKeyChecking=accept-new" \
  --exclude .git --exclude .venv --exclude '.env*' --exclude data --exclude __pycache__ --exclude memory.db \
  "$HERE/" "$USER_AT:$DIR/"

"${SSH[@]}" bash -s <<REMOTE
set -euo pipefail
cd ~/$DIR
test -f .env || { echo "~/$DIR/.env is missing - create it first (see README)." >&2; exit 1; }
sudo nice -n 19 docker compose build
sudo docker compose up -d
sleep 8
sudo docker compose ps
sudo docker compose logs --tail 25 agent
REMOTE
