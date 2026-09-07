# Deployment

## Sizing

| Local model | RAM for the model | Total RAM | Disk |
|---|---|---|---|
| `llama3.2:1b` | ~2 GB | 6 GB | 15 GB |
| `llama3.2:3b` (default) | ~4 GB | 8 GB | 20 GB |
| `qwen2.5:7b` | ~8 GB | 16 GB | 30 GB |

Add ~2 GB for Postgres, Qdrant, n8n and Open WebUI together. CPU inference
works; expect 5–30 s for a 3B model on a modern server core. A GPU is not
required and changes only latency.

Disk grows with documents and their vectors. A thousand pages of PDF is on the
order of a few hundred MB once chunked and embedded.

## Install

```bash
git clone <repo> /opt/ai-helper && cd /opt/ai-helper
./scripts/setup.sh
```

Then, before anyone uses it:

```bash
# 1. dashboard credentials
docker compose exec ai-helper python -m app.cli hash-password
#    paste ADMIN_PASSWORD_HASH= into .env

# 2. production settings in .env
#    ENVIRONMENT=production
#    LOG_FORMAT=json
#    AI_DAILY_API_BUDGET / AI_MONTHLY_API_BUDGET to what you will actually accept

docker compose up -d

# 3. verify
./scripts/health_check.sh
```

## TLS and the reverse proxy

Compose binds everything to `127.0.0.1`. Nothing is reachable from outside the
host until you put a proxy in front. nginx:

```nginx
server {
    listen 443 ssl http2;
    server_name ai.example.com;

    ssl_certificate     /etc/letsencrypt/live/ai.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ai.example.com/privkey.pem;

    # A local model is slow. A 60s proxy timeout will cut off answers that
    # were about to arrive, and the caller sees a 504 for a request that
    # actually succeeded and was billed.
    proxy_read_timeout 180s;
    proxy_send_timeout 180s;

    client_max_body_size 25M;   # match MAX_UPLOAD_BYTES

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # The dashboard has its own login, but restricting it by network is
    # cheap and worth doing.
    location /admin {
        allow 10.0.0.0/8;
        deny all;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 80;
    server_name ai.example.com;
    return 301 https://$host$request_uri;
}
```

Do **not** expose Open WebUI (3000) or n8n (5678) publicly. They are operator
tools with their own auth models, and neither goes through the Gateway's
budget, privacy or learning layers.

## Building behind a TLS-intercepting proxy

On a corporate network that inspects TLS, `pip` inside the build will not trust
the proxy's certificate. Supply it as a build secret rather than copying it
into a layer, where it would ship with the image:

```bash
docker build --secret id=pip_ca,src=/etc/ssl/certs/corporate-ca.crt -t ai-helper .
```

Ollama pulls its models over the same network. If model pulls fail with a
certificate error, mount the CA into that container too — in an override file,
not in `docker-compose.yml`:

```yaml
# docker-compose.override.yml
services:
  ollama:
    volumes:
      - ollama_models:/root/.ollama
      - /etc/ssl/certs/corporate-ca.crt:/usr/local/share/ca-certificates/proxy-ca.crt:ro
    entrypoint: ["/bin/sh", "-c", "update-ca-certificates >/dev/null 2>&1 || true; exec /bin/ollama serve"]
```

## Migrations

The compose command runs `alembic upgrade head` before starting uvicorn, so a
deploy migrates itself. To run it by hand:

```bash
docker compose exec ai-helper alembic upgrade head
docker compose exec ai-helper alembic current
```

**Order for any deploy that changes the schema:**

```
backup  →  migrate  →  restart  →  verify the logs
```

Never the other way round. `scripts/backup.sh` verifies the dump it writes;
take one and check its output before migrating.

Every schema change ships with an Alembic revision and a note in
`docs/CHANGELOG.md`. `0001_baseline` materialises the v1.0 schema; everything
after it is a hand-reviewed revision with an explicit upgrade and downgrade.

## Upgrading

```bash
cd /opt/ai-helper
./scripts/backup.sh
git pull
docker compose build ai-helper
docker compose up -d
docker compose logs -f ai-helper        # watch it migrate and start
./scripts/health_check.sh
```

Rollback: `git checkout <previous-tag>`, rebuild, and restore the database from
the backup if the migration was not reversible.

## Models

```bash
docker compose exec ollama ollama pull llama3.2:3b
docker compose exec ollama ollama pull nomic-embed-text
docker compose exec ollama ollama list
```

`nomic-embed-text` matters more than it looks. Without it the system falls back
to a **lexical** vectoriser that has no semantic understanding — it still works,
retrieval simply gets much worse at paraphrases. `/health` reports the embedder
as `DEGRADED` when that happens, and the dashboard says so on the Runtime row.
It is easy to run for months without noticing, so check after any change to
Ollama.

Changing `EMBEDDING_MODEL` starts a new vector collection rather than
invalidating the old one, so existing documents need re-indexing:
`docs/operations.md`, "Rebuilding the vector index".

## Scaling

One process handles the request rate this is designed for. When it does not:

- **More workers** — `uvicorn --workers 4`. Two things become per-process and
  stop being global: the rate limiter and the background job queue. Move the
  limiter to Redis and the jobs to Celery or RQ before doing this seriously;
  the `jobs` table and the API contract stay as they are.
- **Bigger Ollama** — a GPU, or `OLLAMA_MAX_LOADED_MODELS` raised so a model
  swap does not stall requests.
- **Qdrant** — the database vector fallback is linear per client. Past the tens
  of thousands of points, run Qdrant properly.
- **Postgres** — the request log and audit trail grow monotonically. Partition
  or archive `request_logs` before it becomes the biggest table.

## Backups

```bash
./scripts/backup.sh
# BACKUP_DIR=/mnt/backups BACKUP_RETAIN_DAYS=90 ./scripts/backup.sh
```

Nightly cron:

```
0 3 * * * cd /opt/ai-helper && BACKUP_DIR=/mnt/backups ./scripts/backup.sh >> /var/log/ai-helper-backup.log 2>&1
```

The backup contains `.env`, which contains secrets. Store it accordingly.

Ollama's models are deliberately **not** backed up — tens of gigabytes,
re-downloadable with one command, and backing them up starves the storage the
irreplaceable data needs.

**Restore your backup at least once, into a scratch environment.** A backup
that has never been restored is a hypothesis.

## Monitoring

- `GET /healthz` — liveness. Use this for the restart decision.
- `GET /readyz` — readiness (database reachable).
- `GET /health` — component detail. 503 when the database or gateway is down.
- `./scripts/health_check.sh` — the same, formatted; exits non-zero on a
  problem, so it works as a deploy gate.
- `GET /api/v1/costs` — spend against budgets. Alert at 80%.

Watch `local_success_rate` and `fallback_percentage` on `/api/v1/usage`. A
fallback rate that climbs means either the local model got worse (a model
change, a resource problem) or the questions got harder. Both are worth
knowing before the invoice tells you.

## Rollback of a bad configuration

Everything is environment variables, so:

```bash
docker compose exec ai-helper env | grep -E 'BUDGET|ENABLED|THRESHOLD'
vi .env
docker compose up -d ai-helper
```

Turning off paid providers (`OPENAI_ENABLED=false`,
`ANTHROPIC_ENABLED=false`) is always safe: the system keeps answering locally
and every blocked escalation is reported as `NOT_CONFIGURED`.
