# Operations

## Daily

```bash
./scripts/health_check.sh
curl -s localhost:8000/api/v1/costs -H "Authorization: Bearer $ADMIN_KEY" | jq
```

Or open `/admin`. The numbers worth a glance each morning:

| Number | What a bad value means |
|---|---|
| **Local success rate** | falling → the local model got worse, or the questions got harder |
| **API fallback %** | rising → you are about to spend more |
| **Promoted solutions** | flat while fallbacks climb → the promotion pipeline is rejecting everything; look at `/admin/solutions` |
| **Spend today / month** | approaching a budget → decide before it decides for you |
| **Failed requests** | non-zero → something is down; check `/health` |
| **Embedder** | `DEGRADED` → the lexical fallback is in use and retrieval is much worse |

## Models

```bash
docker compose exec ollama ollama list
docker compose exec ollama ollama pull qwen2.5:7b
docker compose exec ollama ollama rm old-model
```

After installing a model, point config at it and restart:

```bash
# .env
STRONG_LOCAL_MODEL=qwen2.5:7b
docker compose up -d ai-helper
curl -s localhost:8000/api/v1/models -H "Authorization: Bearer $KEY" | jq
```

`resolved_to` in that response shows what `select()` would actually use, which
may be a different tag of the same base model.

## Rebuilding the vector index

Needed after changing `EMBEDDING_MODEL`, after installing the embedding model
for the first time, or after losing Qdrant's storage. The relational database
is the system of record; vectors are derived and can always be rebuilt from it.

```bash
docker compose exec ai-helper python - <<'PY'
from app.database.models import Client, DocumentChunk, MemoryItem, SolutionCandidate
from app.database.session import session_scope
from app.database.enums import SolutionStatus, MemoryStatus
from app.runtime import get_runtime
from sqlalchemy import select

runtime = get_runtime()
print("embedder:", runtime.embedder.id, "semantic:", runtime.embedder.semantic)

with session_scope() as session:
    for client in session.scalars(select(Client)):
        retriever = runtime.retriever(session, client.client_id)
        chunks = list(session.scalars(
            select(DocumentChunk).where(DocumentChunk.client_id == client.client_id)))
        retriever.index_chunks(chunks)
        memories = list(session.scalars(select(MemoryItem).where(
            MemoryItem.client_id == client.client_id,
            MemoryItem.status == MemoryStatus.ACTIVE.value)))
        for item in memories:
            retriever.index_memory(item)
        solutions = list(session.scalars(select(SolutionCandidate).where(
            SolutionCandidate.client_id == client.client_id,
            SolutionCandidate.status == SolutionStatus.PROMOTED.value)))
        for solution in solutions:
            retriever.index_solution(solution)
        print(f"{client.client_id}: {len(chunks)} chunks, {len(memories)} memories, "
              f"{len(solutions)} solutions")
PY
```

Then confirm retrieval actually works, rather than assuming it does:

```bash
curl -s "localhost:8000/api/v1/memory/search?q=<something+you+know+is+in+a+document>" \
  -H "Authorization: Bearer $KEY" | jq '.hits[0], .semantic'
```

## Reviewing what the system learned

`/admin/solutions`, or:

```bash
curl -s "localhost:8000/api/v1/solutions?status=CANDIDATE" -H "Authorization: Bearer $KEY" | jq
curl -s "localhost:8000/api/v1/solutions/sol_..." -H "Authorization: Bearer $KEY" | jq
```

The detail view shows the original question, the local model's failed attempt,
the paid answer, and both gates' results. Promote or reject from the dashboard.

With `AUTO_PROMOTE=false` (the default) every candidate waits for a human. Turn
it on once you have watched a few dozen decisions and agree with them.

**Rejecting matters as much as promoting.** A wrong answer that reaches
PROMOTED will be served confidently, from memory, for `SOLUTION_TTL_DAYS`.

## Expiring old knowledge

```bash
docker compose exec ai-helper python -m app.cli expire
```

Marks memory items and solutions past their TTL as `EXPIRED` so they stop being
retrieved. The rows stay for audit. Run it nightly (the n8n maintenance
workflow does).

## Tuning cost

Look at *why* you are paying before changing anything:

```bash
curl -s localhost:8000/api/v1/costs -H "Authorization: Bearer $ADMIN_KEY" \
  | jq '.by_escalation_reason'
```

| Dominant reason | What it means | What to do |
|---|---|---|
| `NO_KNOWLEDGE_FOUND` | the answers are not in the system | ingest the documents; this is the cheapest fix there is |
| `LOW_CONFIDENCE` | the local model nearly manages | try a stronger local model before touching the threshold |
| `VALIDATION_FAILURE` | the local model produces unusable output | a bigger model, or a `PAID_TASK_DENYLIST` entry for that task type |
| `LOCAL_MODEL_UNAVAILABLE` | Ollama is down or has no model | fix that; you are paying for an outage |
| `LOCAL_TIMEOUT` | the model is too slow | raise `LOCAL_TIMEOUT_SECONDS`, or use a smaller model |
| `TASK_TOO_COMPLEX` | genuinely beyond the local model | this is what the paid provider is for |

Lowering `CONFIDENCE_THRESHOLD` reduces spend by accepting more local answers,
and accepts more wrong ones with it. It is a real trade, not a free saving.
Move it in small steps and watch what the answers look like.

## Logs

```bash
docker compose logs -f ai-helper
docker compose logs ai-helper | grep '"level":"error"'
docker compose logs ai-helper | grep 'req_abc123'      # one request, end to end
```

JSON to stderr. Every line carries `request_id` and `client_id`. Content and
credentials are never logged — if you need to know what a request asked, the
audit trail has the metadata and the conversation has the text, both behind
authentication.

## Audit

```bash
curl -s "localhost:8000/api/v1/admin/audit?action=provider.external_call&limit=50" \
  -H "Authorization: Bearer $ADMIN_KEY" | jq
```

Actions worth knowing: `provider.external_call`, `privacy.escalation_blocked`,
`cost.budget_tripped`, `learning.solution_promoted`, `auth.failure`,
`client.created`, `client.revoked`.

The table is append-only at the ORM level — updates and deletes raise.

## Troubleshooting

### Everything escalates to the paid API

```bash
curl -s localhost:8000/api/v1/models -H "Authorization: Bearer $KEY" | jq '.local_available'
docker compose logs ollama | tail -50
```

Usually: no model installed, Ollama out of memory, or the model name in `.env`
not matching what is installed.

### Retrieval finds nothing

1. Is the document `ready`? `GET /api/v1/documents` — a `failed` document was
   extracted but never indexed, and answers nothing.
2. Is the embedder semantic? `GET /api/v1/models` → `embedder_semantic`. If
   false, you are on the lexical fallback: install `nomic-embed-text` and
   re-index.
3. Are you searching the right client? Every namespace is scoped to the key.

### "PAID API DISABLED"

A budget is exhausted. `GET /api/v1/costs` shows which. The system is still
answering locally; this is the designed behaviour, not a fault. Raise the
budget deliberately or wait for the window to roll over.

### The dashboard says 503 at login

`ADMIN_PASSWORD_HASH` is not set. `python -m app.cli hash-password`, paste the
line into `.env`, restart.

### A job is stuck

Jobs live in this process. A restart abandons anything running, and those rows
are marked `failed` with "the worker process restarted" on the next startup
rather than left claiming to run. Resubmit.

### Postgres will not start after a restart

Usually disk. `df -h`, then `docker compose logs postgres`.

## Restoring

```bash
docker compose down
docker compose up -d postgres
docker compose exec -T postgres pg_restore -U aihelper -d aihelper \
    --clean --if-exists < backups/<stamp>/postgres.dump
docker compose up -d
./scripts/health_check.sh
```

Then rebuild the vector index (above) — vectors are derived data and the
relational database is the system of record.

## A short maintenance calendar

| When | What |
|---|---|
| daily | health check; glance at spend |
| weekly | review CANDIDATE solutions; check the fallback reasons |
| monthly | verify a backup restores into a scratch environment; review client keys and revoke unused ones; check `pricing.py` against the providers' published rates |
| on any model change | confirm the embedder is still semantic; re-index if it changed |
