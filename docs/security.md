# Security

## What this system is protecting

Business documents, the questions people ask about them, and a set of
credentials that can spend money. Three things follow: nothing sensitive leaves
without a decision, no client can read another's data, and no bug can run up a
bill.

## Authentication

**API keys** for machine access. `ahk_<key_id>.<secret>`, a 32-byte random
secret. Stored as SHA-256 and compared in constant time — a high-entropy random
secret does not need a slow KDF, and the digest is not reversible, so a key
cannot be recovered from the database. It is shown once, at creation.

**Passwords** for the dashboard get `hashlib.scrypt` with a per-hash random
salt. Standard library, deliberately: `passlib` + `bcrypt` silently truncates
at 72 bytes and the two packages drift apart across versions. There is no
bcrypt in `requirements.txt` and that is not an oversight.

**Sessions** are HMAC-SHA256 signed tokens in an `httponly`, `samesite=lax`
cookie, `secure` in production.

Authentication failures are uniform. Unknown key, wrong secret and disabled
client all produce the same 401 body, so the endpoint cannot enumerate clients.

## Authorisation

A client row carries:

| Field | Controls |
|---|---|
| `enabled`, `revoked_at` | whether it can call at all |
| `is_admin` | access to `/api/v1/admin/*` |
| `may_escalate` | whether it can cause a paid call |
| `allowed_tools` | which tools it may reach (`null` = the default set, `[]` = none) |
| `default_classification` | the sensitivity floor for its requests |
| `max_external_classification` | the ceiling for what may leave |
| `daily_budget_usd` | its own spend cap, on top of the global one |
| `rate_limit_per_minute` | its own rate limit |

Grant `may_escalate` only to clients that should be able to spend money. It is
off for a client created through the dashboard form unless the box is ticked.

## Isolation between clients

The rule: **every query filters on `client_id` in the query**, never by
discarding rows afterwards.

- Postgres: every table that can hold client data carries `client_id`, and
  every read in `app/` filters on it.
- Qdrant: the filter is part of the query, and any returned point whose payload
  names a different client is dropped and logged as an error — a filter bug
  must not become a data leak.
- The database vector fallback filters in SQL, and refuses a write that would
  land on another client's point.
- Tools receive `client_id` from the authenticated identity through the
  gateway's context, never as a tool argument. `client_id` is not in any tool's
  input schema, so a model asking for one gets a schema error.
- Not-found and not-yours return the same 404, so ids cannot be probed.

Proved by `tests/gateway/test_critical_regressions.py::test_9*` and
`tests/security/test_security.py::TestIsolationThroughTheApi`.

## Data classification

Four levels: `PUBLIC`, `INTERNAL`, `CONFIDENTIAL`, `RESTRICTED`.

A request's classification is the **most sensitive** of: the client's floor,
what the caller declared, and what the detector found. The detector can only
raise. A pattern matcher that could declassify data would be a hole, not a
feature.

The detector marks `RESTRICTED` on credential shapes — API keys, private keys,
AWS keys, JWTs, bearer tokens, database URLs with a password, IBANs, Luhn-valid
card numbers — and `CONFIDENTIAL` on personal identifiers. It errs toward more
sensitive: a long digit run that is not really a phone number becomes
CONFIDENTIAL, which costs a possible escalation, not a disclosure.

## The rule about external providers

**`RESTRICTED` never leaves.** Refused in `may_leave_system()` before any
configuration is read, and refused again in `PaidProviderManager.call()` — the
last function before the wire. Setting
`EXTERNAL_ALLOWED_CLASSIFICATIONS=...,RESTRICTED` does not enable it: the
application refuses to start.

Above that, `EXTERNAL_ALLOWED_CLASSIFICATIONS` (default `PUBLIC,INTERNAL`) and
the client's own ceiling both apply.

**Redaction is in addition, never instead.** With
`REDACT_BEFORE_ESCALATION=true`, emails, phone numbers, tax ids, IBANs, cards
and credentials are replaced with placeholders before the prompt leaves, and
restored in the answer. The placeholder map never leaves the process and is
never persisted.

What redaction is not: a guarantee. A regex cannot tell that "the client on the
third floor of the Warsaw office" identifies someone. That is precisely why
RESTRICTED is blocked outright rather than redacted, and why redaction does not
raise a classification's ceiling.

**Every external call is audited** with provider, model, escalation reason,
token counts, cost, and a redaction summary — and with none of the content. You
can always answer "what did we send out, when, why, and what did it cost"
without the audit log itself becoming a copy of the data.

## Logging

Logs go to **stderr** as JSON, so stdout stays clean for machine-readable
command output.

A redaction processor runs on every log line. Credential-shaped strings are
scrubbed by pattern, and a fixed set of keys is replaced wholesale — including
`message`, `prompt`, `answer`, `content`, `text` and `document`. **Request
content is never logged.** The request log table stores a fingerprint of the
question, not the question.

Audit `detail` records metadata only, truncated, with the same scrubbing.

## Prompt injection

The defence is structural, not a filter:

1. Retrieved text is **fenced** in `<<<CONTEXT … CONTEXT>>>` blocks.
2. The system prompt says that text inside those blocks is untrusted data
   supplied by users and documents, and that instructions found inside it must
   never be followed.
3. Injection phrasing in a *request* raises its risk level, is recorded, and
   **suppresses capture of the resulting answer** — an answer produced from a
   probable injection attempt is not learning material.
4. An answer that echoes injection phrasing present in retrieved context is a
   safety violation and fails validation.

This reduces the attack surface. It does not eliminate it; no known technique
does. See `docs/LIMITATIONS.md`.

## The tool system

There is no general executor. No `run_command`, no `eval`, no `exec`, no
filesystem write, no arbitrary HTTP.

The calculator parses to an AST and walks it with an explicit allow-list of
node types and functions. No name lookup, no attribute access, no call to
anything but the listed functions, no reachable builtin, and an exponent cap so
`9**9**9` cannot exhaust memory.

Every tool declares name, description, permissions, input schema, output
schema and risk level, and the registry refuses to register one that omits any.
Arguments are schema-validated before the handler runs. `web_search` — the only
tool that reaches the internet — carries the network permission, MEDIUM risk,
and three separate off-switches.

## Cost as a security property

A runaway loop against a paid API is a financial denial-of-service. The
controls are in `docs/architecture.md`; the security-relevant parts are that
the pre-flight check is pessimistic, that an unknown model is priced at its
provider's worst rate rather than zero, and that a budget has no override path.

## Deployment

- Generate `AUTH_SECRET` with `openssl rand -hex 32`. The default is a
  placeholder and must be changed.
- Never commit `.env`. It is git-ignored; `scripts/setup.sh` writes it mode 600.
- Compose binds every port to `127.0.0.1`. Terminate TLS in a proxy in front.
- Postgres and Qdrant publish no ports in the production compose file.
- The container runs as a non-root user (uid 10001).
- Back up regularly and **restore from a backup at least once**, or you do not
  have one. `scripts/backup.sh` verifies each artefact it writes.

## Reporting a problem

Do not open a public issue. Contact the maintainer directly with a description,
reproduction steps, and what you think the impact is.
