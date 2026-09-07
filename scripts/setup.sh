#!/usr/bin/env bash
# First-run setup: generate secrets, start the stack, pull models, create a key.
set -euo pipefail

cd "$(dirname "$0")/.."

green() { printf '\033[0;32m%s\033[0m\n' "$*"; }
warn()  { printf '\033[0;33m%s\033[0m\n' "$*"; }
die()   { printf '\033[0;31m%s\033[0m\n' "$*" >&2; exit 1; }

command -v docker >/dev/null || die "docker is not installed"
docker compose version >/dev/null 2>&1 || die "docker compose v2 is required"

# ---------------------------------------------------------------- .env
if [[ -f .env ]]; then
    warn ".env already exists — leaving it alone."
else
    green "Creating .env from .env.example with generated secrets…"
    cp .env.example .env
    secret() { openssl rand -hex 32; }
    # Portable in-place edit (GNU sed and BSD sed disagree about -i).
    for key in AUTH_SECRET N8N_ENCRYPTION_KEY WEBUI_SECRET_KEY; do
        value=$(secret)
        tmp=$(mktemp)
        sed "s|^${key}=.*|${key}=${value}|" .env > "$tmp" && mv "$tmp" .env
    done
    db_password=$(openssl rand -hex 24)
    tmp=$(mktemp)
    sed -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${db_password}|" \
        -e "s|^DATABASE_URL=.*|DATABASE_URL=postgresql+psycopg://aihelper:${db_password}@postgres:5432/aihelper|" \
        .env > "$tmp" && mv "$tmp" .env
    chmod 600 .env
    green "  .env written (mode 600). It is git-ignored — keep it that way."
fi

# ------------------------------------------------------- admin password
if ! grep -qE '^ADMIN_PASSWORD_HASH=.+' .env; then
    warn "No dashboard password is set. The API works without it; /admin will not."
    echo  "  Set one with:  docker compose exec ai-helper python -m app.cli hash-password"
    echo  "  then paste the ADMIN_PASSWORD_HASH= line into .env and restart."
fi

# ----------------------------------------------------------- the stack
green "Starting the stack…"
docker compose up -d --build

green "Waiting for the gateway to answer…"
for _ in $(seq 1 60); do
    if curl -fsS http://localhost:8000/healthz >/dev/null 2>&1; then break; fi
    sleep 2
done
curl -fsS http://localhost:8000/healthz >/dev/null 2>&1 \
    || die "the gateway did not come up — check: docker compose logs ai-helper"

# ------------------------------------------------------------- models
green "Pulling local models (this downloads several GB and takes a while)…"
for model in llama3.2:3b nomic-embed-text; do
    echo "  → ${model}"
    docker compose exec -T ollama ollama pull "${model}" \
        || warn "  could not pull ${model}; pull it later with: docker compose exec ollama ollama pull ${model}"
done

green "Done."
echo
echo "  Gateway     http://localhost:8000        (docs at /docs)"
echo "  Dashboard   http://localhost:8000/admin"
echo "  Open WebUI  http://localhost:3000"
echo "  n8n         http://localhost:5678"
echo
echo "Create a client key:"
echo "  docker compose exec ai-helper python -m app.cli create-client myapp"
echo
echo "Then check component health:"
echo "  ./scripts/health_check.sh"
