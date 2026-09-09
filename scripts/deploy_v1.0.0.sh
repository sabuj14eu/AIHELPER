#!/usr/bin/env bash
# Deploy the approved AI Helper v1.0.0 commit on the production host.
#
# Encodes audit/REAL_MODEL_GATE.md §10 as a guarded script. Every Docker
# command is scoped to the compose project "ai-helper"; nothing here names,
# lists or touches any other project, container, volume, network or service.
# It STOPS (exit 1) rather than guess whenever a check fails.
#
#   cd /opt/ai-helper                                  # the AI Helper checkout
#   git fetch origin claude/pensive-pascal-jgqpx0 && git checkout origin/claude/pensive-pascal-jgqpx0 -- scripts/deploy_v1.0.0.sh
#   cp scripts/deploy_v1.0.0.sh /tmp/ && git checkout -- scripts && /tmp/deploy_v1.0.0.sh
#
# Run it from a COPY: this script is committed after the approved commit, so
# pinning 080bdf1 removes it from the working tree while it runs.
#
# Optional: SKIP_BACKUP=1 for a first install with no data to back up.
set -euo pipefail

APPROVED=080bdf10cbec7eb961243e436bf184970caa3965
PROJECT=ai-helper
C=(docker compose -p "$PROJECT")

stop() { printf '\nSTOP: %s\n' "$*" >&2; exit 1; }
step() { printf '\n== %s\n' "$*"; }

step "1. verify target and repository"
pwd
ROOT=$(git rev-parse --show-toplevel) || stop "not inside a git repository"
[ "$ROOT" = "$(pwd)" ] || stop "run this from the repository root ($ROOT)"
[ -f app/main.py ] && [ -f docker-compose.yml ] && grep -q '^name: ai-helper' docker-compose.yml \
    || stop "this is not the AI Helper repository"
git remote -v | grep -qi aihelper || stop "the git remote is not the AI Helper repository"
[ -z "$(git status --porcelain)" ] || stop "working tree is not clean"

step "2-4. fetch and pin the approved commit"
git fetch origin claude/pensive-pascal-jgqpx0
git checkout --quiet --detach "$APPROVED"
[ "$(git rev-parse HEAD)" = "$APPROVED" ] || stop "HEAD is not the approved commit"
[ -z "$(git status --porcelain)" ] || stop "uncommitted modifications after checkout"
git tag -a v1.0.0 "$APPROVED" -m "AI Helper 1.0.0" 2>/dev/null || true
echo "HEAD = $APPROVED (v1.0.0)"

step "5. AI Helper resources only"
"${C[@]}" ps
docker volume ls --filter "name=${PROJECT}_" --format '{{.Name}}'
for port in 8000 3000 5678; do
    # A port published by this project's own containers is ours (re-runs).
    if "${C[@]}" ps --format '{{.Ports}}' | grep -q ":${port}->"; then continue; fi
    holder=$(ss -ltnp 2>/dev/null | awk -v p=":$port" '$4 ~ p"$" {print $NF}' | head -1 || true)
    if [ -n "$holder" ] && ! echo "$holder" | grep -qi docker; then
        stop "port $port is held by a non-Docker process ($holder); resolve before deploying"
    fi
done

step "6. backup of AI Helper data (rollback rehearsal)"
[ -f .env ] || stop ".env is missing — create it from .env.example first"
if [ "${SKIP_BACKUP:-0}" != "1" ]; then
    ./scripts/backup.sh || stop "backup failed; nothing was changed"
fi

step "7. .env checks (values are not printed)"
req() { grep -q "^$1=$2\$" .env || stop ".env must have $1=$2"; }
req ENVIRONMENT production
req MEMORY_SIMILARITY_THRESHOLD 0.55
req SOLUTION_REUSE_THRESHOLD 0.80
req ANTHROPIC_ENABLED false
req OPENAI_ENABLED false
grep -q '^LOCAL_TIMEOUT_SECONDS=180' .env || echo "note: LOCAL_TIMEOUT_SECONDS=180 is recommended on a CPU-only host"
grep -q '^AUTH_SECRET=CHANGE_ME' .env && stop "AUTH_SECRET is still the placeholder"
grep -q '^ADMIN_PASSWORD_HASH=.\+' .env || stop "ADMIN_PASSWORD_HASH is empty (python -m app.cli hash-password)"

step "deploy: AI Helper services only"
"${C[@]}" up -d --build
"${C[@]}" exec -T ollama ollama pull llama3.2:3b
"${C[@]}" exec -T ollama ollama pull nomic-embed-text
"${C[@]}" exec -T ai-helper python -m app.cli calibrate || stop "calibrate did not exit 0"

step "9-10. smoke tests"
./scripts/health_check.sh || stop "health check failed"
"${C[@]}" exec -T postgres pg_isready -U aihelper -d aihelper || stop "PostgreSQL not ready"
SMOKE="smoke-$(date +%s)"
KEY=$("${C[@]}" exec -T ai-helper python -m app.cli create-client "$SMOKE" \
      | python3 -c 'import sys,json;print(json.load(sys.stdin)["api_key"])')
AUTH=(-H "Authorization: Bearer $KEY")
[ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/api/v1/usage)" = "401" ] || stop "authentication is not enforced"
chat=$(curl -s "${AUTH[@]}" -H 'Content-Type: application/json' http://127.0.0.1:8000/api/v1/chat \
       -d '{"message":"What is the capital of Poland?"}')
echo "$chat" | python3 -c '
import sys, json
d = json.load(sys.stdin)
print({k: d.get(k) for k in ("route", "provider", "model", "success", "cost_usd", "latency_ms")}, "|", (d.get("answer") or "")[:60])
assert d["route"] == "local" and d["provider"] == "ollama" and d["cost_usd"] == 0, "local inference did not answer"
' || stop "local model inference failed"
curl -s "${AUTH[@]}" -H 'Content-Type: application/json' http://127.0.0.1:8000/api/v1/memory \
     -d '{"content":"The smoke-test printer is on the second floor.","source":"smoke","confidence":0.9}' > /dev/null
curl -s "${AUTH[@]}" 'http://127.0.0.1:8000/api/v1/memory/search?q=which+floor+is+the+printer' | python3 -c '
import sys, json
d = json.load(sys.stdin); assert d["semantic"] and d["hits"], "semantic memory search found nothing"
print("memory/RAG:", d["embedder"], "top score", d["hits"][0]["score"])' || stop "memory/RAG failed"
curl -s "${AUTH[@]}" -H 'Content-Type: application/json' http://127.0.0.1:8000/api/v1/chat \
     -d '{"message":"Explain the Nowak margin rule","classification":"RESTRICTED","task_type":"research"}' | python3 -c '
import sys, json
d = json.load(sys.stdin); print("privacy gate:", d["classification"], d["escalation_blocked_reason"], "cost", d["cost_usd"])
assert d["classification"] == "RESTRICTED" and d["cost_usd"] == 0 and d["route"] != "paid"' || stop "privacy gate failed"
curl -s "${AUTH[@]}" http://127.0.0.1:8000/api/v1/costs | python3 -c 'import sys,json; d=json.load(sys.stdin); print("cost tracking: today", d.get("api_cost_today"), "budget", d.get("daily_budget"))'
curl -s http://127.0.0.1:8000/health | python3 -c '
import sys, json
c = {x["name"]: x["status"] for x in json.load(sys.stdin)["components"]}
print("paid providers:", c.get("openai"), c.get("anthropic"))
assert c.get("openai") == "DISABLED" and c.get("anthropic") == "DISABLED"' || stop "a paid provider is enabled"
"${C[@]}" restart ai-helper
for _ in $(seq 1 60); do curl -sf -o /dev/null http://127.0.0.1:8000/healthz && break; sleep 2; done
curl -s "${AUTH[@]}" 'http://127.0.0.1:8000/api/v1/memory/search?q=which+floor+is+the+printer' | python3 -c '
import sys, json; assert json.load(sys.stdin)["hits"], "memory lost across restart"; print("persistence across restart: OK")' \
    || stop "data did not survive a restart"
echo "admin dashboard /admin/login: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/admin/login) (expect 200)"
echo "open-webui 127.0.0.1:3000: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/) (expect 200; loopback only)"
"${C[@]}" ps --format '{{.Name}} {{.Status}}'
ADMIN_KEY="${AI_HELPER_ADMIN_KEY:-}"
if [ -n "$ADMIN_KEY" ]; then
    curl -s -X POST -H "Authorization: Bearer $ADMIN_KEY" "http://127.0.0.1:8000/api/v1/admin/clients/$SMOKE/revoke" > /dev/null && echo "smoke client revoked"
else
    echo "note: revoke the smoke client '$SMOKE' from /admin or with an admin key"
fi

step "11. other projects: observe only"
docker ps --format '{{.Names}} {{.Status}}' | grep -v "^${PROJECT}-" || true
echo
echo "DEPLOYED $APPROVED at $(date -u +%Y-%m-%dT%H:%M:%SZ). Record this output in docs/DEPLOYMENT_RECORD_v1.0.0.md."
