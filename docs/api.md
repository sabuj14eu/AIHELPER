# API

Base URL `http://localhost:8000`. Interactive docs at `/docs`, machine-readable
schema at `/openapi.json`.

## Authentication

Every endpoint except `/`, `/health`, `/healthz` and `/readyz` needs an API key.

```
Authorization: Bearer ahk_<key_id>.<secret>
X-API-Key: ahk_<key_id>.<secret>          # equivalent
```

Create one:

```bash
docker compose exec ai-helper python -m app.cli create-client myapp
```

The plaintext key is shown **once**. Only a SHA-256 digest is stored, so it
cannot be recovered — reissue instead.

Failures are uniform: an unknown key, a wrong secret and a disabled client all
return the same 401 body, so the endpoint cannot be used to enumerate client
ids.

## Rate limits

A token bucket per client: `RATE_LIMIT_BURST` requests at once, refilling at
`RATE_LIMIT_PER_MINUTE`. A 429 carries `detail.retry_after` in seconds. Set
`rate_limit_per_minute` on a client row to override it for that client.

The limiter is **per process** — see `docs/LIMITATIONS.md`.

## Errors

```json
{
  "error": "a message written for the caller",
  "code": "budget_exceeded",
  "detail": {},
  "request_id": "req_..."
}
```

| Code | HTTP | Means |
|---|---|---|
| `authentication_failed` | 401 | missing, malformed, unknown or revoked key |
| `permission_denied` | 403 | the client may not do this |
| `not_found` | 404 | no such resource *for this client* |
| `rate_limited` | 429 | slow down; `detail.retry_after` |
| `validation_error` | 422 | the request body or an uploaded file was rejected |
| `provider_unavailable` | 503 | no provider could answer |
| `internal_error` | 500 | a bug; the `request_id` finds it in the logs |

`request_id` also comes back as the `x-request-id` header on every response,
and correlates the request log, the audit trail and the cost records.

---

## `POST /api/v1/chat`

The one endpoint an integrating application needs.

```json
{
  "message": "What does our handbook say about invoice numbering?",
  "task_type": null,
  "agent": null,
  "conversation_id": null,
  "document_ids": [],
  "namespace": null,
  "classification": null,
  "response_format": "text",
  "model": null,
  "premium": false,
  "max_tokens": null,
  "user_ref": null,
  "store_conversation": true
}
```

Only `message` is required. Unknown fields are rejected with a 422 rather than
ignored — a typo in a field name should not silently change behaviour.

| Field | Notes |
|---|---|
| `task_type` | Overrides the classifier: `general`, `arithmetic`, `date`, `structured_data`, `document_qa`, `summarization`, `classification`, `extraction`, `research`, `code`, `reasoning` |
| `agent` | `general`, `research`, `document`, `developer`. Narrows tools and adds a system-prompt fragment; it can never widen permissions |
| `document_ids` | Naming documents forces `document_qa` |
| `classification` | `PUBLIC`…`RESTRICTED`. You can **raise** the sensitivity of your own request; you can never lower it below your client's floor |
| `premium` | Ask for a paid model directly. Honoured only if `ALLOW_USER_REQUESTED_PREMIUM=true`; off by default because it spends money without a validation failure behind it |
| `store_conversation` | `false` keeps the exchange out of conversation memory |

### Response

```json
{
  "request_id": "req_...",
  "answer": "Invoices are numbered FV/YYYY/NN.",
  "route": "local",
  "task_type": "document_qa",
  "classification": "CONFIDENTIAL",
  "provider": "ollama",
  "model": "llama3.2:3b",
  "agent": null,
  "confidence": 0.87,
  "memory_hit": true,
  "tool_used": null,
  "escalation_reason": null,
  "escalation_blocked_reason": null,
  "cost_usd": 0.0,
  "latency_ms": 412,
  "tokens": { "input": 380, "output": 24 },
  "conversation_id": "conv_...",
  "solution_id": null,
  "success": true,
  "sources": [{ "source": "document", "ref": "doc_abc#3", "score": 0.81 }],
  "validation": { "passed": true, "confidence": 0.87, "signals": {}, "vetoes": [] },
  "retrieval": { "memory_hit": true, "exact_match": false, "top_score": 0.81 },
  "notes": []
}
```

**`route`** — which level answered:

| Value | Meaning |
|---|---|
| `tool` | a deterministic tool; no model was consulted; free |
| `local` | the local model; free |
| `paid` | an external provider; `cost_usd` is non-zero |
| `failed` | nothing produced an acceptable answer; `notes` says why |

**`success: false` with a non-empty `answer`** means: we are giving you the
best attempt we have, and it did not pass validation. `notes` says so. Treat it
as unverified.

**`escalation_reason`** — set whenever escalation was *wanted*, even if it was
then blocked. Exactly one of `LOCAL_MODEL_UNAVAILABLE`, `LOCAL_TIMEOUT`,
`LOW_CONFIDENCE`, `VALIDATION_FAILURE`, `NO_KNOWLEDGE_FOUND`,
`TASK_TOO_COMPLEX`, `USER_REQUESTED_PREMIUM_MODEL`.

**`escalation_blocked_reason`** — why it did not happen:
`NOT_CONFIGURED`, `DISABLED`, `DAILY_BUDGET_EXHAUSTED`,
`MONTHLY_BUDGET_EXHAUSTED`, `REQUEST_COST_CAP`, `REQUEST_TOO_LARGE`,
`CLASSIFICATION_BLOCKED`, `TASK_TYPE_DENIED`, `CLIENT_NOT_PERMITTED`,
`PROVIDER_FAILED`.

---

## `POST /api/v1/tasks` · `GET /api/v1/tasks/{id}`

The same body as `/chat`, run in the background. Returns `202` with a
`task_id`; poll for `queued` → `running` → `succeeded` / `failed`. The
finished body carries the full chat response under `result`.

Use it for anything long: a large document, a heavy analysis. A task belonging
to another client returns 404, not 403.

---

## Documents

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/documents` | multipart upload (`file`, `namespace`, `classification`, `title`) |
| `GET /api/v1/documents` | list this client's documents |
| `GET /api/v1/documents/{id}` | one document |
| `GET /api/v1/documents/{id}/chunks` | its chunks |
| `DELETE /api/v1/documents/{id}` | delete it and its vectors |
| `GET /api/v1/documents/formats` | supported extensions |
| `GET /api/v1/documents/stats` | totals for this client |

Formats: PDF, TXT, Markdown, DOCX, CSV, JSON, JSONL.

Check `status` in the response. `ready` means chunked, embedded and searchable.
**`failed` means the text was extracted but the vectors did not land** — the
document exists and answers nothing. A scanned PDF with no text layer is
refused outright with a message saying it needs OCR, rather than ingested as an
empty document.

Re-uploading identical bytes is a no-op and returns `duplicate: true` with the
original id.

---

## Memory

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/memory` | write a long-term item |
| `GET /api/v1/memory` | list items |
| `GET /api/v1/memory/search?q=` | semantic search across memory, documents and promoted solutions |
| `DELETE /api/v1/memory/{id}` | revoke an item |
| `GET /api/v1/conversations` | list conversations |
| `GET /api/v1/conversations/{id}` | its turns |

A write requires `content`, `source` and `confidence` (0–1). Those are not
optional: a memory row without provenance is a rumour, and the write path
refuses to create one. `ttl_days` sets an expiry.

The search response reports which embedder produced the scores and whether it
is `semantic` — worth checking before reading much into a number.

---

## Solutions (the learning record)

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/solutions?status=CANDIDATE` | list learned solutions |
| `GET /api/v1/solutions/counts` | counts by status |
| `GET /api/v1/solutions/{id}` | one, with the answer, the local attempt and both gates' results |
| `POST /api/v1/solutions/{id}/promote` | run the promotion pipeline |
| `POST /api/v1/solutions/{id}/reject` | reject and unindex |

Statuses: `CANDIDATE` → `VALIDATED` → `PROMOTED`, or `REJECTED`, or `EXPIRED`.

---

## Observability

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/usage` | requests, local vs fallback, memory hits, promoted/rejected, escalation reasons, estimated saving |
| `GET /api/v1/costs` | spend against each budget, by provider and by escalation reason |
| `GET /api/v1/usage/fallbacks` | why local AI failed, who solved it, what happened to the answer |
| `GET /api/v1/usage/requests` | recent request log |
| `GET /api/v1/models` | installed models, the active embedder, provider status |
| `GET /api/v1/tools` | tools this client may use |
| `GET /api/v1/agents` | agent profiles |

A normal key sees its own numbers; an admin key sees the deployment's.

`estimated_money_saved_usd` is a **counterfactual**: requests answered
successfully without paying, times the mean cost of the paid calls actually
made. It is zero until at least one paid call gives it a basis. It is an
estimate of avoided spend, not an invoice.

## Health

`GET /health` returns every component with `OK` / `DEGRADED` / `DOWN` /
`DISABLED` / `UNAVAILABLE`, and 503 when the database or gateway is down.

`GET /healthz` is liveness only — process up, nothing more. Use that for the
orchestrator's restart decision; `/health` is for humans and dashboards.

Paid providers are reported as configured-or-not rather than probed, because
probing them costs money.

## Admin API

Admin-key only:

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/admin/clients` | list clients |
| `POST /api/v1/admin/clients` | create one; the key is returned once |
| `POST /api/v1/admin/clients/{id}/revoke` | revoke it |
| `GET /api/v1/admin/audit` | search the audit trail |
| `GET /api/v1/admin/overview` | everything the dashboard shows, as JSON |

---

## Integrating an application

1. `python -m app.cli create-client <name>` — grant `--may-escalate` only if
   that application should be able to spend money.
2. Store the key as a secret. Never in source.
3. Call `POST /api/v1/chat`.
4. Handle three cases: `success: true` (use it), `success: false` with an
   answer (unverified — decide whether that is good enough for your use), and
   `route: "failed"` (no answer; `notes` says why).
5. Watch `escalation_reason` in your own metrics. It is how you find out what
   is actually costing you money.

Nothing about that requires a change to AI Helper.
