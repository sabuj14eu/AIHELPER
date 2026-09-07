# Audit

Executable verification for the claims in the main README. Every script here
runs a **real** gateway process and attacks or exercises it over HTTP; each
exits non-zero on any failure, so they work as CI gates.

| Script | Proves | Checks |
|---|---|---|
| `demo_e2e.py` | the cost-saving cycle end to end | 27 |
| `prove_cost.py` | budgets and caps actually stop spending | 25 |
| `prove_privacy_and_permissions.py` | RESTRICTED never leaves; clients are isolated | 54 |
| `prove_security.py` | auth, authz, rate limits, validation, SSRF, uploads | 51 |
| `prove_learning.py` | an API answer is never automatically trusted | 29 |
| `prove_persistence.py` | migrations, restart, backup/restore, no lost memory | 35 |
| `prove_container_persistence.py` | real `docker compose down`/`up`; PostgreSQL and Qdrant counts survive | 30 |

`prove_container_persistence.py` needs the Docker stack running. It reads row
counts with `psql` and vector counts from Qdrant's own API rather than through
the application, which could otherwise report whatever it had cached.

`fake_servers.py` provides protocol-faithful stand-ins for Ollama and
Anthropic. They fake the **wire protocol**, not the application: the real
`OllamaClient`, `ModelManager`, `AnthropicProvider`, gateway, validation, cost
tracker and database all execute exactly as they would in production.

What is still simulated is the neural network. There are no model weights in
this environment. The "local model" answers from a rule — it can restate a fact
that is in its prompt and cannot answer a hard question that is not — which is
a faithful model of the property the cost-saving cycle depends on, but it is a
simulation. `AUDIT_REPORT.md` says exactly what that leaves unproven.

Run everything:

```bash
python -m pytest
for s in demo_e2e prove_cost prove_privacy_and_permissions \
         prove_security prove_learning prove_persistence; do
    python audit/$s.py || echo "FAILED: $s"
done
```

Results of the last full run are in `RESULTS.txt`; the report is
`AUDIT_REPORT.md`.
