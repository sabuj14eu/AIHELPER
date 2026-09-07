# n8n workflows

n8n is here for **orchestration around** the Gateway — ingestion pipelines,
notifications, scheduled housekeeping. It is deliberately **not** the
intelligence, and nothing here makes a routing, budget, privacy or promotion
decision. Those live in the Python service, where they are tested (see
`tests/gateway/test_critical_regressions.py`). A workflow that reimplemented
one of them would be a second, untested policy engine.

The JSON files in this directory are importable starting points. In n8n:
**Workflows → Import from file**, then set the credential for the AI Helper API
key. They mount read-only at `/workflows` inside the container.

| Workflow | What it does | What it must never do |
|---|---|---|
| `document-ingestion.json` | Watches a folder, POSTs each file to `/api/v1/documents`, reports the result | Decide a document's classification on its own |
| `fallback-review.json` | Every hour, lists CANDIDATE solutions and notifies a reviewer | Promote a solution |
| `budget-watch.json` | Every 15 min, reads `/api/v1/costs`; alerts at 80% of a budget | Disable or re-enable paid providers — the tracker already does that, atomically |
| `nightly-maintenance.json` | Runs the TTL sweep and a health check, alerts on a degraded component | Restart or reconfigure anything |

## Credentials

Create one n8n **Header Auth** credential:

- Name: `AI Helper API`
- Header: `Authorization`
- Value: `Bearer ahk_…` (from `python -m app.cli create-client n8n`)

Give that client only what its workflows need. `--may-escalate` is not one of
those things: a workflow that can escalate is a workflow that can spend money
on a schedule.
