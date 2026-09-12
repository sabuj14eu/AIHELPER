# OPUS 5 — INDEPENDENT READ-ONLY AUDIT: AI HELPER

- **Repository:** `sabuj14eu/AIHELPER` · HEAD `b36ac85` · branch `claude/elegant-fermi-252t22`
- **Date:** 2026-09-12
- **Auditor role:** independent senior software architect · security reviewer · production-readiness auditor
- **Mode:** READ-ONLY. No application file was modified, created or deleted during the audit; no configuration, environment file, test, container or service was touched; nothing was deployed. The only artefact produced is this document.
- **Prior work reviewed:** `audit/AUDIT_REPORT.md`, `docs/HANDOVER_TO_FABLE.md`, `docs/LIMITATIONS.md` — treated as claims to test, never as findings.

## Execution caveat, stated first because the handover demands it

`pytest`, `fastapi`, `pydantic` and `sqlalchemy` are absent from the audit environment, no Docker daemon is available, and installing them would modify the environment the audit rules forbid touching. **Nothing was executed against this system.**

Per `docs/HANDOVER_TO_FABLE.md` §7 — *"Do not mark anything PASS from static inspection. If it was not executed, it is NOT RUN, and NOT RUN is not a pass"* — every gate in §9 is **NOT RUN** unless stated otherwise.

The **only** measured claims in this report are in finding **TOOL-01**. They come from re-creating `app/tools/calculator.py`'s evaluator in an isolated scratch directory, with the `app.*` imports stripped, so that no repository file was imported, executed or touched. Those results are marked `EXECUTED`.

---

## 1. Executive Verdict

### **NOT APPROVED** — and the blocker count goes from one to three.

The previous engineer's verdict was NOT APPROVED for one reason: no real language model has ever run against the system. That blocker stands, unchanged and un-closable here. This audit adds two findings that are independent of it and would each hold NOT APPROVED on their own:

1. **The privacy gate classifies the question; the payload that leaves is the question *plus retrieved context*.** Documents are ingested as CONFIDENTIAL by default, `EXTERNAL_ALLOWED_CLASSIFICATIONS` defaults to `PUBLIC,INTERNAL`, and a document's stored classification is never consulted at the escalation gate. An INTERNAL question that retrieves a CONFIDENTIAL chunk sends that chunk to a paid provider. Both "independent" privacy checks pass, because both re-check the same precomputed verdict about the question.
2. **The budget is a soft cap under concurrency.** `CostTracker.check()` reads `SUM(estimated_cost)` and the matching `record()` happens after a network call that takes seconds. There is no reservation, no row lock, no advisory lock. N in-flight requests all read the same pre-spend total and all spend. The README says "hard stop, no override path"; the tracker docstring says a budget "can be approached but not overshot." Both are true for one request in isolation and false for two.

Neither is hypothetical, neither is in `LIMITATIONS.md`, and neither has a test.

That said — and this matters for how the remaining work should be sized — **this is the best-engineered repository in this workspace.** The AI containment, the fail-closed defaults, the production-secret startup guard, the audit trail, the per-client isolation and the honesty of the documentation are all genuinely strong. Most of what follows is a list of gaps in a good system, not a rebuild.

---

## 2. Overall Risk Rating

### **MEDIUM**

Not High, because: the whole stack binds to `127.0.0.1`; paid providers are off by default and need a key; escalation, web search and auto-promotion are off or gated by default; there is no `eval`, no `exec`, no `subprocess`, no `pickle`, no shell and no string-built SQL anywhere in `app/`; and production refuses to start on a placeholder secret. The blast radius of every finding below is bounded by the fact that nothing is exposed and nothing spends money until an operator deliberately turns it on.

Not Low, because: the two headline gaps sit precisely on the two properties the project advertises as its reason to exist (privacy governance and cost governance), the admin login has no throttle of any kind, and 435 green tests exercise a vector backend the production deployment does not use.

**If paid providers are enabled and documents are ingested, this becomes HIGH**, because SEC-01 goes live on the first escalated document question.

---

## 3. What Is Correct

Verified by reading, and worth protecting.

**The ladder is real control flow, not a preference.** `GatewayRouter._handle` (`app/gateway/router.py:186-446`) physically cannot reach `_run_paid` without passing through level 0 tools, level 1 retrieval, level 2 local model and level 3 validation. I looked for a bypass and there is none. Even the documented exception is weaker than documented: `premium` is a *reason* inside `why_escalate`, and the router returns at level 3 before ever consulting it when local validation passes — so a premium request the local model answers well is still answered locally. The implementation is more local-first than the README claims.

**Unknown model pricing fails expensive, not free.** `app/cost/pricing.py:41` sets `UNKNOWN_PRICE = ModelPrice(15.00, 75.00)`, and `price_for` falls back to *the provider's worst known rate* for an unlisted model. This is the single most common way a budget system silently fails, and it is explicitly reasoned about in the docstring. Correct.

**AI cannot author an execution value, and cannot raise a limit.** No LLM sits in any control decision — task classification, tool dispatch, escalation, budget and privacy are all deterministic code. Stated as policy in the handover §7, and it holds in the code.

**Production refuses to start on placeholder secrets.** `app/core/config.py:141-165` raises rather than warns when `ENVIRONMENT=production` and `AUTH_SECRET` is the published default or under 32 characters. `_no_restricted_externally` (`:167-176`) makes it impossible to configure `RESTRICTED` into the externally-allowed set at all. Refusing to boot is the right control; most projects only log.

**RESTRICTED is refused before any configuration is read.** `may_leave_system` (`app/privacy/classification.py`) returns False for RESTRICTED on its first line, before consulting `allowed` or the client ceiling. The detector is a floor and cannot declassify. Both correct.

**Per-client isolation is enforced twice, not once.** The README claims scoping happens "in the query, not by filtering afterwards." It is actually both: `client_id` is a filter in the vector query *and* every hydrated row is re-checked (`app/memory/retrieval.py:229, 322, 350`). Stronger than advertised.

**Expiry is enforced at read time, not only by a purge job.** `_expired(solution.expires_at)` gates both the exact-match and vector-similarity solution paths (`retrieval.py:195, 231`), and `_is_stale` filters memory listings (`app/memory/long_term.py:110-118`). An expired solution cannot be served while waiting for a nightly job. Many systems get this wrong.

**Promotion is fail-closed in the right direction.** `app/learning/promotion.py:186-197`: when the reproduction gate *cannot be attempted*, the candidate is held at VALIDATED — "Cannot check. That is not a pass." And an unindexed PROMOTED row is rolled back to VALIDATED (`:209-220`) because "an unindexed PROMOTED row would never be found again." Both are the careful choice.

**The calculator is a real AST allow-list, not a sandboxed `eval`.** No name lookup, no attribute access, no builtins reachable. It has one defect (TOOL-01) but the design is right.

**No dangerous primitives anywhere.** `grep -rn "eval(\|exec(\|subprocess\|os.system\|pickle\|yaml.load\|__import__\|shell=True" app/` returns nothing outside the calculator's AST module. Raw SQL is two `text("SELECT 1")` health probes. For a system whose job is running model output, that discipline is the whole ballgame.

**The Dockerfile and compose are above average.** Two-stage build, non-root `uid 10001`, no `apt-get`, `--only-binary=:all:` as a deliberate guard, stdlib healthcheck, everything bound to `127.0.0.1`, Postgres unpublished, `${VAR:?}` forcing required secrets to be set rather than defaulting.

**`docs/LIMITATIONS.md` is the most honest document in this workspace.** It pre-empts roughly a dozen findings that would otherwise appear here, including the genuinely hard ones (validation cannot verify truth, grounding is lexical overlap, promotion can promote a wrong answer, prompt injection is reduced not solved). Nothing it already states is re-reported below. That document made this audit shorter and better.

---

## 4. Critical Findings

Reported in the format `docs/HANDOVER_TO_FABLE.md` §8 requests.

---

### SEC-01 — The privacy gate classifies the question; retrieved context leaves unclassified

```
Issue:      Data classification is computed from the user's message alone. The
            payload actually sent to a paid provider is the message PLUS
            retrieved document chunks, memory items and promoted solutions.
            Those carry their own stored classification, which is never read.
Severity:   HIGH — blocks production
Cause:      app/gateway/router.py:204-209 computes `classification` from
            `message` only. app/gateway/router.py:545 then builds the outgoing
            prompt as `build_user_prompt(message, retrieval.items)`.
            app/database/models.py:252 stores a per-document classification and
            app/knowledge/ingestion.py:79 defaults it to CONFIDENTIAL — but
            `grep -n classification app/memory/retrieval.py` returns nothing.
            Retrieval neither filters on it nor propagates it.
Fix:        NOT IMPLEMENTED. Direction below.
Regression: None exists. test_8_restricted_information_cannot_be_sent_externally
            (tests/gateway/test_critical_regressions.py:147) puts the secret in
            the QUESTION. No test puts it in a document.
Verification: NOT RUN (static).
```

**Why it matters.** This is the product's headline privacy claim. The README says *"RESTRICTED data never leaves the system — refused in the policy layer and again in the last function before the wire."* Both of those checks call `may_leave_system(classification, ...)` on the **same precomputed value** — `app/gateway/escalation.py` at the policy layer and `app/gateway/provider_manager.py:117` before the wire. That is genuine defence-in-depth against a *code-path bypass*, and the comment at `router.py:352-357` says so accurately. But it is not two independent determinations, and neither of them ever looks at what retrieval put in the prompt.

**Realistic failure scenario, using only defaults.** A client uploads a contract via `POST /api/v1/documents`; `classification` defaults to `CONFIDENTIAL` (`app/api/routes/documents.py:22`). The client's `default_classification` is `INTERNAL`. `EXTERNAL_ALLOWED_CLASSIFICATIONS` is `PUBLIC,INTERNAL`. `PAID_TASK_DENYLIST` is empty, so `DOCUMENT_QA` may escalate. The client asks *"what are the termination terms?"* — an INTERNAL question with no credential shapes in it. The local 3B model produces a low-confidence answer, `why_escalate` returns `LOW_CONFIDENCE`, `may_escalate` sees INTERNAL and says yes, and the CONFIDENTIAL contract text goes to the paid provider. The system has a field recording that the document was CONFIDENTIAL and never reads it.

**What partly covers it, and why that is not enough.** `REDACT_BEFORE_ESCALATION` defaults true and `PaidProviderManager.prepare()` redacts the *combined* messages, so redaction does see the retrieved text. That catches credential and identifier *shapes*. It does not catch the contract. `LIMITATIONS.md` correctly says the detector "will miss sensitive information that carries no recognisable pattern" — but it frames that as a detector-coverage limit, not as "the detector is not applied to most of the outgoing payload."

**Direction (do not implement from this document).** The classification that gates escalation should be the maximum over {client default, declared, detected-in-question, **detected-in-retrieved-context**, **stored classification of every retrieved item**}. The data model already has every field required. The likely consequence is that document questions stop escalating under default settings — which is arguably the correct behaviour and should be an explicit, documented decision rather than a side effect.

---

### COST-01 — The budget is not atomic; concurrent requests can overshoot it

```
Issue:      check() reads spend and record() writes it, with a multi-second
            provider call in between and no reservation, lock or serialisation.
            Concurrent requests all observe the same pre-spend total.
Severity:   HIGH — blocks production for any multi-worker deployment
Cause:      app/cost/tracker.py:147-215 (check) reads SUM(estimated_cost) via
            _spend_between. app/cost/tracker.py:218-250 (record) inserts after
            the call returns. Nothing bridges them. WORKER_CONCURRENCY defaults
            to 2 (app/core/config.py:139) and uvicorn may run more workers.
Fix:        NOT IMPLEMENTED.
Regression: None. test_7_the_budget_prevents_further_paid_calls and its 7b/7c
            siblings are all single-threaded.
Verification: NOT RUN (static).
```

**Why it matters.** The overshoot is bounded by `concurrency x AI_MAX_COST_PER_REQUEST` (default $0.50) per window. With the default `AI_DAILY_API_BUDGET=5.00` and `WORKER_CONCURRENCY=2`, that is up to 20% over a daily budget — annoying, not alarming. But the bound scales with concurrency and per-request cap, and the `n8n/` workflows in this repo exist precisely to fan out batches of requests. `nightly-maintenance.json` and `document-ingestion.json` are the shapes that produce simultaneous escalations.

The docstring at `tracker.py:1-14` is the thing to correct: *"The pre-flight check is pessimistic: it assumes the response will be the full max_tokens, so a budget can be approached but not overshot by a request the system chose to make."* The pessimism is real and good; the conclusion does not survive a second concurrent request.

**Direction.** A `SELECT … FOR UPDATE` on a per-day spend row, a Postgres advisory lock around check-and-reserve, or an explicit reservation row written before the call and reconciled after. The third is the most honest: it makes the in-flight commitment visible, which the current design cannot express at all.

---

### SEC-02 — The admin login has no rate limit, no lockout, and runs scrypt per attempt

```
Issue:      POST /admin/login is unauthenticated, unthrottled, and performs
            hashlib.scrypt(n=2**14, r=8) on every attempt. It is both an
            unlimited password-guessing oracle and a CPU/memory amplifier.
Severity:   MEDIUM — would be HIGH on any exposed deployment
Cause:      Rate limiting lives inside current_client (app/api/deps.py:96),
            i.e. AFTER API-key authentication. There is no global limiter
            middleware in app/main.py. /admin/login (app/api/routes/admin.py:219)
            does not depend on current_client, so no limiter runs at all.
Fix:        NOT IMPLEMENTED.
Regression: tests/security/test_security.py covers per-client throttling
            (test_a_client_is_throttled_and_told_when_to_retry) but nothing
            covers an unauthenticated path.
Verification: NOT RUN (static).
```

**Why it matters.** `ADMIN_PASSWORD_HASH` is generated from a human-chosen password via `app.cli hash-password`. scrypt at `n=2**14` costs roughly 16 MB and tens of milliseconds per attempt — the right choice for a KDF, and it makes each request expensive *for the server* as well as the attacker. A few hundred concurrent login POSTs is a memory and CPU denial of service against a service whose worker count defaults to 2.

**The same root cause has a second consequence.** Every failed API-key authentication writes an audit row (`app/api/deps.py:78-91`) before any rate limit is consulted. An unauthenticated client can insert unbounded rows into an append-only table that by design is never pruned: storage exhaustion on the Postgres volume, and pollution of the trail a security review would later read.

**Direction.** A limiter keyed on client IP applied before authentication, covering `/admin/login` and unauthenticated `/api/v1/*` failures; and a decision about whether every *failed* auth deserves a durable row, or whether a counter plus a sampled row is the right shape.

---

### TOOL-01 — `MAX_POWER` is bypassable via the allow-listed `pow()` function

```
Issue:      The exponent guard is applied to the ast.Pow binary operator but not
            to the pow() function, which is on the allow-list. Arbitrary CPU and
            memory can be consumed by a short expression.
Severity:   MEDIUM
Cause:      app/tools/calculator.py:22 defines MAX_POWER = 1_000 with the
            comment "refuse 9**9**9 style resource exhaustion". The guard is
            applied at :72-73, inside the ast.BinOp branch only. "pow": pow is
            registered at :36 and reached through the ast.Call branch at
            :90-102, which applies no exponent check.
Fix:        NOT IMPLEMENTED.
Regression: None found for pow() as a call.
Verification: EXECUTED — evaluator re-created in an isolated scratch directory
            with app.* imports stripped; no repository file imported or touched:
              '10 ** 5000'       -> refused: exponent larger than 1000 is refused
              'pow(10, 5000)'    -> ACCEPTED
              'pow(3, 3000000)'  -> ACCEPTED,  0.29 s CPU, 0.6 MB integer
              'pow(3, 10000000)' -> ACCEPTED,  2.05 s CPU, 2.0 MB integer
```

**Why it matters.** The 500-character expression limit does not help, because the exponent can itself be an expression: `pow(3,pow(3,17))` is 16 characters and asks for 3 to the power of 129,140,163. The default rate limit is 60 requests/minute per client, per process, and the tool runs synchronously on a worker. This is the one finding with measured numbers rather than an argument.

**Second defect in the same file.** `_format` calls `str(value)` at `:132`, **outside** the `try` that wraps `evaluate` in `calculate` (`:135-140`). For a large integer result, Python 3.11+ raises `ValueError: Exceeds the limit (4300 digits) for integer string conversion`. Verified EXECUTED: `calculate('pow(10, 5000)')` raises an **uncaught `ValueError`** rather than returning `ToolResult(ok=False, …)`. The tool's own error contract is bypassed and the exception escapes into the dispatcher.

**Direction.** Apply the same exponent bound inside the `ast.Call` branch for `pow` (and consider `exp`), and move `_format` inside the guarded block so every failure returns a `ToolResult`.

---

### REL-01 — Qdrant/database backend flips mid-run, and there is no reindex path

```
Issue:      The vector backend is chosen at startup, silently falls back to the
            database store if Qdrant is unreachable, and is then flipped back
            mid-process by a health poll. Vectors written under one backend are
            invisible to the other, and nothing migrates them.
Severity:   MEDIUM — data-visibility, not data-loss
Cause:      app/runtime.py:67-89 (_connect_qdrant) returns None on any failure
            and logs a warning. app/runtime.py:91-95 (recheck_qdrant) reconnects
            later; app/api/routes/health.py:42 calls it on every /health poll.
            app/runtime.py:102-105 (vector_store) then returns a different store
            for subsequent requests. `grep -rn "reindex\|migrate_vectors\|def
            rebuild" app/ scripts/` returns nothing.
Fix:        NOT IMPLEMENTED.
Regression: None. The suite runs with QDRANT_ENABLED=False throughout
            (tests/conftest.py:36), so neither backend transition is exercised.
Verification: NOT RUN (static).
```

**Why it matters, and why the author will likely accept it.** This codebase already reasons about exactly this hazard one layer up. `app/runtime.py:8-11`: *"The embedder is resolved once at startup so that a deployment does not silently flip between a semantic and a lexical index mid-run: vectors from two embedders are never comparable, and a store that mixed them would return nonsense with a confident score."* That reasoning is correct and applies verbatim to the **store**. The embedder was pinned; the store was given a `recheck` method that un-pins it.

**Realistic failure scenario.** Qdrant is restarting during a deploy. The gateway comes up, logs `qdrant_unavailable`, and serves from the database store. A client uploads three documents; ingestion reports READY, because the vectors genuinely landed — in the database. Two minutes later a `/health` poll reconnects Qdrant. Every subsequent retrieval queries Qdrant, which has never heard of those three documents. They appear in `/api/v1/documents` with status READY and answer nothing, forever. That is the precise failure mode `app/knowledge/extraction.py:1-8` says the system refuses to allow: *"a document that silently ingests as zero characters is worse than a rejected upload: it looks present in the listing and answers nothing."*

`LIMITATIONS.md` covers the database fallback as a *scale* limitation ("the database vector fallback is linear"). It does not cover it as a *visibility* one.

**Direction.** Either pin the backend for the process lifetime the way the embedder is pinned and require a restart to change it, or write to both stores while degraded, or ship the reindex command that does not currently exist. Any of the three; the current state is the only one that loses data silently.

---

### SEC-03 — Uploads are read fully into memory before the size limit is applied

```
Issue:      The 20 MB cap is enforced after the entire request body has been
            read. A DOCX is additionally a zip, decompressed with no bound on
            the expanded size.
Severity:   MEDIUM
Cause:      app/api/routes/documents.py:33 — `data = await file.read()` —
            precedes app/knowledge/ingestion.py:84, which raises only once
            `len(data) > self.max_bytes`. app/knowledge/extraction.py:118-125
            passes an arbitrary <=20 MB zip to docx.Document() with no
            decompressed-size check.
Fix:        NOT IMPLEMENTED.
Regression: tests/unit/test_extraction_formats.py covers format handling; no
            test covers an oversized body or a compression bomb.
Verification: NOT RUN (static).
```

Starlette spools large uploads to disk above ~1 MB, so the first half is disk pressure followed by memory pressure at `.read()`; the second half is a classic zip bomb, where a 20 MB archive can expand to gigabytes of XML inside `python-docx`. Both require an authenticated client, which bounds this to an insider or a leaked key.

**Adjacent, smaller.** `classification: str = Form(default="CONFIDENTIAL")` is passed to `Classification(str(classification).upper())` (`ingestion.py:115`). An invalid value raises `ValueError`, which the generic handler (`app/main.py:138`) turns into a 500 rather than a 400.

---

### SEC-04 — Qdrant runs with no API key by default, on a network shared with n8n and Open WebUI

```
Issue:      Every other required secret in docker-compose.yml uses ${VAR:?} to
            force it to be set. Qdrant uses ${QDRANT_API_KEY:-}, i.e. empty.
Severity:   MEDIUM
Cause:      docker-compose.yml:65 — QDRANT__SERVICE__API_KEY: ${QDRANT_API_KEY:-}
            vs :49 POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?...}, :90
            N8N_ENCRYPTION_KEY: ${...:?...}, :119 WEBUI_SECRET_KEY: ${...:?...}.
            scripts/setup.sh:22 generates AUTH_SECRET, N8N_ENCRYPTION_KEY and
            WEBUI_SECRET_KEY, and :27 a Postgres password. It does not generate
            QDRANT_API_KEY. .env.example:25 ships it empty.
Fix:        NOT IMPLEMENTED.
Regression: None applicable.
Verification: NOT RUN (static).
```

**Why it matters.** Qdrant publishes no host port, so this is not internet-exposed. But it sits on the `ai-helper` docker network alongside two third-party images — `n8nio/n8n` and `ghcr.io/open-webui/open-webui` — and n8n exists specifically to run operator-authored workflows with HTTP nodes. The per-client isolation the gateway enforces so carefully at the API is absent one layer down: anything on that network can read or write every client's vectors and payloads unauthenticated. The gateway is a front door with a good lock, on a room that has another door.

---

### PROMPT-01 — The context fence can be closed by the content it fences

```
Issue:      Retrieved text is wrapped in <<<CONTEXT … CONTEXT>>> markers and the
            content is not escaped. A document containing the literal closing
            marker terminates the fence early; text after it appears to the
            model as though it were outside any untrusted block.
Severity:   LOW-MEDIUM
Cause:      app/local_ai/prompts.py:81 —
            block = f"<<<CONTEXT {header}\n{body}\nCONTEXT>>>", body unescaped.
Fix:        NOT IMPLEMENTED.
Regression: tests/security/test_security.py:250
            (test_retrieved_text_cannot_issue_instructions) tests instruction
            text inside an intact fence, not a forged fence boundary.
Verification: NOT RUN (static).
```

`LIMITATIONS.md` is right that "a sufficiently clever injection in a document can still influence an answer" and that no technique eliminates this. But *this* particular hole is not the unsolvable part — it is a missing escape, and the fencing mechanism is specifically named in `app/validation/safety.py:18-19` as "the real defence."

---

### COST-02 — `may_escalate`'s docstring overstates what it checks

```
Issue:      "Everything that can forbid an escalation, checked before any spend."
            Budget is not among them.
Severity:   LOW (correctness of documented reasoning, not behaviour)
Cause:      app/gateway/escalation.py:120 docstring vs the function body, which
            checks classification, client permission, task denylist, the
            escalation switch and provider configuration — but not cost. Budget
            is enforced later, per-provider, in
            app/gateway/provider_manager.py:160-169.
Fix:        NOT IMPLEMENTED.
Verification: NOT RUN (static).
```

The placement is architecturally right — budget must be checked per provider and per model, which is only knowable inside the manager. The sentence is what needs correcting, because it is the sentence a future reader will trust when deciding where to add the next guard.

---

### DEP-01 — The dependency policy stated in `requirements.txt` is not the policy it implements

```
Issue:      The file's own comment says "Pinned to a minor range: patch updates
            flow, a surprise major does not." Two entries have no upper bound.
Severity:   LOW
Cause:      requirements.txt — `pypdf>=5.0` and `structlog>=24.1` carry no upper
            bound, unlike every other entry. There is no lockfile and no
            --require-hashes anywhere; the Dockerfile installs from this file.
Fix:        NOT IMPLEMENTED.
Verification: NOT RUN (static).
```

`pypdf` is the parser for untrusted uploaded files, which makes it the dependency where an unexpected major version matters most. Separately, the absence of a lock means "the image builds, 36 s cold cache, 522 MB" is not a reproducible claim — a rebuild next month resolves different versions.

---

## 5. Security Findings — summary

| ID | Severity | Component | Finding |
|---|---|---|---|
| SEC-01 | **High** | `router.py:204,545` | Retrieved context leaves the system unclassified |
| COST-01 | **High** | `cost/tracker.py:147,218` | Budget check-and-spend is not atomic |
| SEC-02 | **Medium** | `deps.py:96`, `admin.py:219` | No rate limit or lockout before authentication; scrypt DoS; unbounded audit-row insertion |
| SEC-03 | **Medium** | `documents.py:33`, `extraction.py:118` | Upload cap applied after full read; no decompressed-size bound on DOCX |
| SEC-04 | **Medium** | `docker-compose.yml:65` | Qdrant unauthenticated on a network shared with two third-party images |
| TOOL-01 | **Medium** | `calculator.py:22,36,90,132` | `MAX_POWER` bypassable via `pow()`; uncaught `ValueError` in `_format` |
| REL-01 | **Medium** | `runtime.py:67-105`, `health.py:42` | Vector backend flips mid-run; no reindex path |
| PROMPT-01 | **Low-Med** | `prompts.py:81` | Context fence delimiters are not escaped in fenced content |
| SEC-05 | **Low** | `admin.py:239` | Username compared with `!=` and short-circuited before `verify_password` — a username-validity timing oracle |
| SEC-06 | **Low** | `main.py:128` | `/docs` and `/openapi.json` are served unconditionally; no `docs_url=None` in production, unlike the `is_production` treatment given to HSTS and the cookie `secure` flag |
| SEC-07 | **Low** | `.env.example:17` | `ENVIRONMENT=development` is the shipped default and `scripts/setup.sh` never changes it, so the production startup guard, the HSTS header and the `secure` cookie flag are all inert on the README's quick-start path. `docs/deployment.md:33` documents the change; the README does not mention it |
| SEC-08 | **Low** | `router.py:405-421` | A paid answer vetoed for `safety_violation` (credential-shaped values in the output) is still returned in the response body with `success=False`. Same-client data, so not a cross-boundary leak, but the behaviour is undocumented |
| COST-02 | **Low** | `escalation.py:120` | Docstring claims budget is checked where it is not |
| DEP-01 | **Low** | `requirements.txt` | Two unbounded dependencies; no lockfile |

**Checked and clean:** no `eval`/`exec`/`subprocess`/`pickle`/`os.system`/`shell=True`; no string-interpolated SQL; API keys stored as SHA-256 of a 32-byte urlsafe secret and compared with `compare_digest`; passwords scrypt with per-hash salt; the hand-rolled JWT verifies the HMAC before parsing the payload and computes HS256 unconditionally, so `alg: none` does not apply; uniform authentication failure messages prevent client-id enumeration; `web_search` takes its URL from operator config, not from the request, and `httpx` does not follow redirects by default — no SSRF.

---

## 6. Reliability Findings

| ID | Severity | Finding |
|---|---|---|
| REL-01 | Medium | Vector backend flips mid-run with no reindex path (§4) |
| REL-02 | Low | `_connect_qdrant` swallows every exception into a warning and a silent downgrade. The downgrade is visible on `/health`, which is honest, but it is a log line away from being invisible in practice — `LIMITATIONS.md` itself notes it is "easy to run for months without looking" about the analogous embedder downgrade |
| REL-03 | Low | `alembic upgrade head` runs inside the app container's start command. Single-replica today; two replicas starting together would race on migrations |
| REL-04 | Low | `uvicorn --proxy-headers` is set without `--forwarded-allow-ips`. Nothing security-relevant currently derives from client IP, so this is latent — but it becomes live the moment SEC-02 is fixed with an IP-keyed limiter |
| REL-05 | Low | Open WebUI ships in the stack talking to Ollama directly, explicitly bypassing the gateway's budget, privacy gate, audit trail and learning. Honestly documented in the compose comment. It reaches only the local model, so no cost or external-privacy exposure — but the audit trail is therefore not a complete record of what the local model was asked |

---

## 7. Testing Gaps

435 tests, 89% coverage, ruff clean — **NOT RUN** here, and there is no reason to doubt the number. The naming is excellent; `tests/gateway/test_critical_regressions.py` maps one-to-one onto the specification's ten guarantees, which is the right structure.

**Tests that give false confidence:**

1. **`test_a_paraphrase_is_also_answered_locally`** (`tests/fallback/test_cost_saving_cycle.py:68`). The test is careful — it explicitly asserts the fingerprint differs, so it really does exercise the vector path. But the suite runs `HashingEmbedder` (`tests/conftest.py:109`), a lexical bag-of-words vectoriser, and the two questions share every content word: *"Explain the {MARKER} rule and when it applies"* vs *"When does the {MARKER} rule apply, and what exactly does it say?"*. That is a lexical near-duplicate, not a semantic paraphrase. The test proves the vector *plumbing* works; its name asserts a capability the project's own gate (`ai-helper calibrate`, currently exiting 1) says is unproven. The handover is honest about this — the test name is not.

2. **`test_no_endpoint_is_reachable_without_a_key_by_accident`** (`tests/security/test_security.py:382`). Enumerating `/openapi.json` and probing every route is a genuinely excellent technique. But line 388 skips any path containing `{` — every parameterised route. Those are precisely the endpoints where cross-tenant access by ID is possible. Individual tests do cover tasks and conversations by id; documents-by-id and memory-by-id rely on the blanket test that excludes them. The guarantee in the name is broader than the guarantee in the body.

**Missing coverage on the paths that matter:**

| Gap | Consequence |
|---|---|
| **The production vector backend is never exercised.** `QDRANT_ENABLED=False` throughout the suite; `TestQdrantStore` runs against a `MagicMock`. All 435 tests use `DatabaseVectorStore`. | The store production actually runs on has no integration coverage, and neither backend transition (REL-01) is testable as written. |
| **No test places sensitive data in a document rather than a question.** | SEC-01 is invisible to the suite. |
| **No concurrency test on the budget.** | COST-01 is invisible to the suite. |
| **No unauthenticated-path test.** Rate limiting is tested per-client, i.e. post-auth only. | SEC-02 is invisible to the suite. |
| **No `pow()` test in the calculator suite.** | TOOL-01 is invisible to the suite. |
| **No oversized-upload or compression-bomb test.** | SEC-03 is invisible to the suite. |
| **No forged-fence injection test.** | PROMPT-01 is invisible to the suite. |

The pattern is consistent and worth naming: **the suite tests the paths the author reasoned about, and the gaps line up exactly with the boundaries between components** — question vs. retrieved context, one request vs. two, authenticated vs. not, operator vs. one of the three enumerated tools. That is the normal shape of self-authored tests, and it is the reason the handover asked for an outside opinion.

---

## 8. Architecture Findings

**ARCH-01 (Medium) — The system classifies a request but sends a payload.** The single structural observation behind SEC-01 and PROMPT-01. Classification, safety input checks and injection detection all take `message` as their subject. Redaction and the model both take the assembled prompt. The gap between those two subjects is where the retrieved context lives, and it is the largest thing the governance layer does not govern.

**ARCH-02 (Low) — Governance is enforced at the gateway, not at the data layer.** Per-client isolation is excellent in `Retriever` and absent in Qdrant and Ollama, which sit on a shared network with two third-party containers. The gateway is the only thing enforcing the boundary, so anything that reaches the network behind it inherits everything.

**ARCH-03 (positive) — The advisory-only boundary is real.** No tool performs an outside action: calculator, dates, json, document list/search/memory, system info, web search. `web_search` is the only one touching the network and carries three independent off-switches, off by default. `ACTION_CLAIM_PATTERNS` in `safety.py` vetoes an answer that *claims* to have acted. The claim in the README holds.

**ARCH-04 (positive) — Layer separation is clean.** No circular imports; `app/core` imports nothing upward; providers are HTTP-only with no vendor SDKs; `app/main.py` builds the app in `__getattr__` so importing the module has no side effects. The reasoning comments throughout explain *why* a boundary is where it is, not just what it does — which is what made this audit possible to do quickly.

---

## 9. Production Readiness — the handover's own gate table

Re-graded independently. Per handover §7, nothing is PASS from static inspection.

| Gate | This audit | Note |
|---|---|---|
| Real Ollama (real weights) | **NOT RUN** | Unchanged blocker. No model weights reachable here either. |
| Calibration | **NOT RUN** | Previously FAIL. Not re-run. |
| Local-first routing | **NOT RUN** (design reviewed, no bypass found) | The ladder is enforced in control flow; §3. |
| Fallback | **NOT RUN** | |
| Learning / validation | **NOT RUN** | |
| Promotion | **NOT RUN** (design reviewed, fail-closed) | |
| Memory reuse (exact match) | **NOT RUN** | |
| Memory reuse (paraphrase) | **NOT PROVEN** | Concur. See §7. |
| Cost controls | **FAIL** | COST-01: not atomic under concurrency. |
| Privacy | **FAIL** | SEC-01: retrieved context is not classified. |
| Security / auth / authz | **FAIL** | SEC-02: no pre-authentication rate limit or lockout. |
| Docker build | **NOT RUN** | No daemon. Dockerfile reviewed and sound. |
| Container restart | **NOT RUN** | |
| PostgreSQL persistence | **NOT RUN** | |
| Qdrant persistence | **NOT RUN** | And REL-01 means "persisted" and "retrievable" can diverge. |
| Full regression suite | **NOT RUN** | Cannot install dependencies without modifying the environment. |

**Verdict, in the handover's own terms — NOT APPROVED.** Three FAILs, one NOT PROVEN, twelve NOT RUN.

---

## 10. Recommended Fix Priority

### Must fix before production

1. **SEC-01** — classify the payload, not the question. The data model already has every field needed.
2. **COST-01** — make the budget check-and-spend atomic, or make the in-flight commitment explicit.
3. **SEC-02** — rate-limit before authentication; decide whether every failed auth needs a durable row.
4. **REL-01** — pin the vector backend for the process lifetime, or write through, or ship a reindex.
5. **The original blocker** — run a real model, get `calibrate` to exit 0, then run the 50-100 real questions nobody has run. The handover is right that this is the part that decides whether the economics work.

### Should fix soon

6. **TOOL-01** — bound `pow()`; move `_format` inside the guarded block.
7. **SEC-03** — enforce the upload cap before buffering; bound DOCX decompression.
8. **SEC-04** — generate `QDRANT_API_KEY` in `setup.sh` and make it `${VAR:?}` like its three siblings.
9. **PROMPT-01** — escape or neutralise fence delimiters in fenced content.
10. **Testing** — a Qdrant-backed integration run; a sensitive-document escalation test; a concurrent-budget test; an unauthenticated-path test. Rename the paraphrase test to what it proves, and remove the `{` exclusion from the endpoint sweep or state it in the test name.
11. **DEP-01** — bound `pypdf` and `structlog`; add a lockfile so "the image builds" is reproducible.
12. **COST-02 / SEC-07** — correct the `may_escalate` docstring; have `setup.sh` prompt for or set `ENVIRONMENT`.

### Optional

13. `docs_url=None` in production; constant-time username comparison; `--forwarded-allow-ips`; document the `safety_violation`-still-returned behaviour.

---

## 11. On the four things the handover asked me to argue with

It asked for disagreement, so here it is, specifically.

**The confidence weights (0.20/0.15/0.30/0.20/0.15, threshold 0.62).** I have no basis to argue the numbers and neither does anyone else — that is the point the handover already makes, and it is correct. What I will argue is the framing: these are not "the least evidence-backed thing in the repository," they are *unmeasurable* with the current tooling, which is a different and worse problem. Backlog item 1 (an evals harness) is not the first thing to do *after* the production gate; it is a prerequisite *for* the gate, because without it the 50-100 real questions produce impressions rather than a number. Move it before the soak, not after.

**The promotion gates.** I agree with the author's own answer — yes, a reproduction gate that only asks "can you use this" is worth its cost, because it eliminates the specific failure of promoting something the local model cannot exploit, which is the failure that would make the whole learning loop pointless. The honest defence is narrower than "it is worth it": it is *cheap* and it catches one specific class. `AUTO_PROMOTE=false` by default is what actually carries the risk, and that is the right call. What I would add: `SOLUTION_TTL_DAYS=180` with no correction path means a wrong promoted answer has a six-month half-life and nothing but a human notices. Handover backlog item 6 (prompt/model version pinning on solutions) is more urgent than its position suggests.

**The dispatcher's conservatism.** Agreed, no argument. A level-0 false positive is a confidently wrong answer with nothing in the loop to catch it. False negatives cost one model call. The asymmetry is real and the choice is right.

**The two threshold pairs.** The semantic pair (0.72/0.80) being inherited convention is correctly flagged. I would add that REL-01 makes this worse than described: if the store can change backend mid-run, the *scores* those thresholds are compared against can change characteristics mid-run too, and the threshold pair is selected from the embedder alone (`for_embedder`), not from the embedder-and-store combination.

**And one the handover did not list.** `LIMITATIONS.md` is load-bearing — it is the control that makes several accepted risks acceptable. It has no owner, no review cadence and no link from the code to the constraint it documents. The moment it drifts from the implementation, several "documented limitation" answers silently become "undocumented defect." That document deserves the same protection the code has.

---

## 12. Final Verdict

### **NOT APPROVED.**

The original blocker stands and could not be closed here. Two more are added: the privacy gate does not see most of what it is gating, and the cost gate is not atomic. Both sit on the two properties this system exists to provide, and neither is in `LIMITATIONS.md`, so neither is a known accepted risk — they are gaps.

**The smallest set of actions before production:**

- Classify the outgoing payload, not the question (SEC-01), with a test that puts the secret in a document.
- Make the budget check atomic (COST-01), with a concurrent test.
- Rate-limit before authentication (SEC-02).
- Pin or reconcile the vector backend (REL-01).
- Then the original gate: real weights, `calibrate` exits 0, and the 50-100 real questions — ideally behind an evals harness rather than by eye.

**Said plainly:** this is careful, honest work. The documentation argues against itself where it should, the defaults are conservative in every place checked, the fail-closed choices are consistently the ones a cautious engineer would make, and `LIMITATIONS.md` pre-empted about a dozen findings that would otherwise appear above. The findings that remain exist because the system is good enough that the gaps are subtle ones — at component boundaries, under concurrency, and in the space between what a test's name claims and what its body checks. That is a much better place to be than most systems at this stage.

---

# FABLE IMPLEMENTATION HANDOFF

> **This document is an independent READ-ONLY audit. Do not treat every finding as an instruction to change code. First verify each finding against the current repository state, distinguish genuine defects from deliberate decisions, and implement only the approved P0/P1 work.**

**Additional standing constraints for the implementing session.** These come from this repository's own rules, not from the auditor:

- **Feature freeze holds** (`docs/HANDOVER_TO_FABLE.md` §1). A defect found is in scope to fix, with a regression test. Nothing else. No architecture changes, no redesign of routing, memory, privacy, security, cost, learning or validation beyond what a named finding requires.
- **Scope is this repository only.** No integration with accounting, SignalMesh, LokalnyDowoz, spa booking or anything else. Not partially, not "while I'm here."
- **Do not weaken a gate to make a test pass.** If `calibrate` fails, fix the embedder or the threshold — do not lower the bar.
- **Do not add an LLM to a control decision.** Task classification, tool dispatch, escalation, budgets and privacy are deterministic on purpose.
- **Do not enable paid providers to "see if it works"** before the real-model gate is done.
- Line numbers are from HEAD `b36ac85`. **Re-locate every anchor before editing** — do not trust a line number.
- Every fix ships with a regression test, and the report format is `Issue / Severity / Cause / Fix / Regression test / Verification`.
- **Nothing here was executed except where a finding says `EXECUTED`.** Reproduce a finding before fixing it; if it does not reproduce, say so and close it rather than changing code to match this document.

---

## P0 — MUST FIX BEFORE REAL MONEY

Read "real money" here as: **before paid providers are enabled with a real API key, on real data.** These are the genuine production blockers. P0-1 and P0-2 also block *trustworthy soak evidence*, because until they are fixed the soak measures a system whose two headline guarantees do not hold.

---

### P0-1 · SEC-01 — Classification is computed from the question; the payload that leaves also contains retrieved context

- **Component:** `app/gateway/router.py:204-209` (classification source) · `app/gateway/router.py:545` (outgoing prompt) · `app/memory/retrieval.py` (no classification anywhere) · `app/database/models.py:252` and `app/knowledge/ingestion.py:79,115` (the stored classification that is never read)
- **Problem:** `classify_sensitivity(message, …)` sees only the user's message. The prompt sent to the paid provider is `build_user_prompt(message, retrieval.items)` — message **plus** document chunks, memory items and promoted solutions. Documents carry their own classification (default `CONFIDENTIAL`) and retrieval neither filters on it nor propagates it into the escalation decision.
- **Why it matters:** This is the product's headline privacy claim. Under stock defaults — client `default_classification=INTERNAL`, `EXTERNAL_ALLOWED_CLASSIFICATIONS=PUBLIC,INTERNAL`, `PAID_TASK_DENYLIST` empty — an INTERNAL question that retrieves a CONFIDENTIAL contract chunk escalates, and the contract text goes to the provider. The "checked twice" claim is two call sites of `may_leave_system()` on the *same precomputed verdict about the question*, which is real defence against a code-path bypass but is not an independent look at the payload. `REDACT_BEFORE_ESCALATION` does see the retrieved text and catches credential *shapes*; it does not catch the contract.
- **Implementation direction:** Make the gating classification the maximum over {client default, declared, detected-in-question, detected-in-retrieved-context, **stored classification of every retrieved item**}. Every field needed already exists in the data model. Expect a behaviour change: document questions will stop escalating under default settings. **That change is significant enough to be an explicit, recorded decision rather than a side effect** — surface it, do not absorb it. Regression test must place the sensitive value in a *document*, not in the question, mirroring `test_8` one level down.
- **Existing rule reference:** README "Privacy that is checked twice" · `docs/security.md` external-call rules · `docs/LIMITATIONS.md` "Classification is pattern matching" (which documents detector coverage, but **not** that the detector is not applied to the retrieved half of the payload — that document needs updating alongside the fix).

---

### P0-2 · COST-01 — The budget check is not atomic; concurrent requests overshoot it

- **Component:** `app/cost/tracker.py:147-215` (`check`) and `:218-250` (`record`) · `app/gateway/provider_manager.py:160-169` (the call site) · `app/core/config.py:139` (`WORKER_CONCURRENCY=2`)
- **Problem:** `check()` reads `SUM(estimated_cost)`; `record()` inserts after the provider call returns, seconds later. Nothing bridges them — no reservation row, no `FOR UPDATE`, no advisory lock. Every in-flight request observes the same pre-spend total.
- **Why it matters:** The overshoot is bounded by `concurrency × AI_MAX_COST_PER_REQUEST` and scales with both. At stock settings that is ~20% over a $5 daily budget; it grows with worker count and per-request cap. The `n8n/` workflows in this repository (`nightly-maintenance.json`, `document-ingestion.json`) exist to fan out batches, which is exactly the shape that produces simultaneous escalations. The README promises "a hard stop, no override path."
- **Implementation direction:** Three viable shapes, in increasing order of honesty: a Postgres advisory lock around check-and-reserve; `SELECT … FOR UPDATE` on a per-day spend row; or an explicit **reservation row** written before the call and reconciled (or released) after. The third is preferred because it makes the in-flight commitment representable, which the current design cannot express at all. Also correct the docstring at `tracker.py:1-14`: the pessimistic `max_tokens` projection is real and good, but "approached but not overshot" does not survive a second concurrent request. Regression test must be concurrent — a single-threaded test cannot see this.
- **Existing rule reference:** README "Cost protection that cannot be talked out of" · `app/cost/tracker.py` module docstring · `docs/architecture.md` cost section.

---

### P0-3 · SEC-02 — No rate limit or lockout before authentication; the admin login is a scrypt amplifier

- **Component:** `app/api/deps.py:96` (limiter is inside `current_client`, i.e. post-auth) · `app/api/routes/admin.py:219-252` (`/admin/login`, no limiter dependency) · `app/main.py:118-126` (no global limiter middleware) · `app/api/deps.py:78-91` (audit row written on failed auth, before the limiter)
- **Problem:** Two consequences of one root cause. (a) `/admin/login` is unauthenticated and unthrottled and runs `hashlib.scrypt(n=2**14, r=8)` per attempt — an unlimited guessing oracle against a human-chosen password, and ~16 MB plus tens of milliseconds of server cost per request. (b) Every failed API-key authentication writes a durable row into an append-only, never-pruned audit table before any limit applies.
- **Why it matters:** (a) is both credential brute-force and a memory/CPU denial of service against a service defaulting to two workers. (b) lets an unauthenticated caller exhaust the Postgres volume and pollute the trail a later security review would read. Neither is covered by `docs/LIMITATIONS.md`, which scopes the limiter's weakness as "per-process" — a statement about horizontal scale, not about it being absent pre-auth.
- **Implementation direction:** An IP-keyed limiter applied before authentication, covering `/admin/login` and unauthenticated `/api/v1/*` failures. Add progressive backoff or a lockout window on repeated admin failures. Separately decide whether every failed auth deserves a durable row or whether a counter plus a sampled row is the right shape — that is a design decision, not a mechanical fix. Note the interaction with **P2 REL-04**: `--proxy-headers` is currently set without `--forwarded-allow-ips`, which is harmless today and becomes load-bearing the moment the limiter keys on client IP. Fix both together or the limiter is spoofable.
- **Existing rule reference:** `docs/security.md` authentication section · `docs/LIMITATIONS.md` "The rate limiter is per process" (needs extending to say it is also post-auth only).

---

### P0-4 · REL-01 — The vector backend flips mid-run and there is no reindex path

- **Component:** `app/runtime.py:67-89` (`_connect_qdrant`, silent fallback) · `:91-95` (`recheck_qdrant`) · `:102-105` (`vector_store`) · `app/api/routes/health.py:42` (calls `recheck_qdrant` on every poll)
- **Problem:** Qdrant is connected once at startup; any failure downgrades silently to `DatabaseVectorStore`; a `/health` poll later flips it back mid-process. Vectors written under one backend are invisible to the other, and `grep -rn "reindex\|migrate_vectors\|def rebuild" app/ scripts/` returns nothing.
- **Why it matters:** A document ingested during a Qdrant outage reports READY (the vectors genuinely landed — in the database), and becomes permanently unfindable once Qdrant reconnects. That is precisely the failure `app/knowledge/extraction.py:1-8` says the system refuses to allow: *"a document that looks present in the listing and answers nothing."* The codebase already reasons about this exact hazard for the embedder (`app/runtime.py:8-11`: resolved once at startup so the index cannot silently flip mid-run) — the store was given a `recheck` method that un-pins what the embedder deliberately pinned. `docs/LIMITATIONS.md` covers the fallback as a *scale* issue, not a *visibility* one.
- **Implementation direction:** Pick one and be explicit: (a) pin the backend for the process lifetime, as the embedder is pinned, and require a restart to change it — smallest change, matches existing reasoning; (b) write through to both stores while degraded; or (c) ship the reindex command that does not exist. Any of the three is acceptable; the current state is the only one that loses data silently. Whichever is chosen, `docs/LIMITATIONS.md` needs the visibility consequence added.
- **Existing rule reference:** ADR-equivalent reasoning in `app/runtime.py:8-11` (embedder pinning) · `app/knowledge/extraction.py:1-8` (a document that answers nothing is worse than a rejected upload) · `docs/LIMITATIONS.md` "The database vector fallback is linear".

---

### P0-5 · The original blocker — no real language model has ever run against this system

- **Component:** whole system · `docs/HANDOVER_TO_FABLE.md` §3
- **Problem:** Unchanged and not closable from this audit. `ai-helper calibrate` exits 1; every "local model" and "paid provider" in the existing evidence is a protocol-faithful HTTP stand-in.
- **Why it matters:** Every threshold in the system — `CONFIDENCE_THRESHOLD=0.62`, the five confidence weights, the semantic threshold pair 0.72/0.80 — is calibrated against something that answers by rule. Until a real embedder runs, learned solutions are not reused for a reworded question and the system pays repeatedly for the same problem.
- **Implementation direction:** Follow §3 of the handover verbatim: pull `nomic-embed-text` and `llama3.2:3b`, `calibrate` must exit 0, `health_check.sh` must read OK not DEGRADED, re-run `audit/demo_e2e.py`. Then the part nobody has done: 50-100 real questions with paid providers disabled, watching `local_success_rate` and `escalations_blocked`. **One disagreement with the handover's ordering:** build the evals harness (its backlog item 1) *before* that soak rather than after. Without it the 50-100 questions produce impressions, not a number, and there is no way to tell whether a later threshold change helped.
- **Existing rule reference:** `docs/HANDOVER_TO_FABLE.md` §3 and §7 ("NOT RUN is not a pass").

---

## P1 — SHOULD FIX BEFORE PRODUCTION

Important, not immediate blockers for a local demo deployment.

---

### P1-1 · TOOL-01 — `MAX_POWER` is bypassable via `pow()`, and `_format` can raise uncaught

- **Component:** `app/tools/calculator.py:22` (`MAX_POWER`), `:36` (`"pow": pow`), `:72-73` (guard, BinOp branch only), `:90-102` (Call branch, no guard), `:132` (`return str(value)`), `:135-140` (`calculate`'s `try` covers only `evaluate`)
- **Problem:** The exponent guard that exists specifically to "refuse 9**9**9 style resource exhaustion" applies only to the `**` operator. `pow()` is on the allow-list and reached through a branch that does not check. Separately, `_format` calls `str()` on the result outside the guarded block, so a large integer raises an uncaught `ValueError` instead of returning `ToolResult(ok=False, …)`.
- **Why it matters:** **This is the only finding in the report with measured numbers.** EXECUTED, in an isolated re-creation of the evaluator with `app.*` imports stripped: `'10 ** 5000'` → refused; `'pow(10, 5000)'` → accepted; `'pow(3, 3000000)'` → accepted, 0.29 s CPU; `'pow(3, 10000000)'` → accepted, 2.05 s CPU, 2.0 MB integer. The 500-character expression limit does not help — `pow(3,pow(3,17))` is 16 characters and asks for 3^129140163. The tool runs synchronously on a worker, default limit 60 req/min per client per process.
- **Implementation direction:** Apply the same exponent bound inside the `ast.Call` branch for `pow`, and consider `exp` for the same reason. Move `_format` inside `calculate`'s `try` so every failure path returns a `ToolResult` and the tool's error contract holds. Two regression tests: `pow()` past `MAX_POWER` is refused; a large-integer result returns `ok=False` rather than raising.
- **Existing rule reference:** the comment at `calculator.py:22` states the intent this finding shows is unmet · `docs/security.md` tool sandbox section · handover §5 backlog item 8 ("a real security review … focused on the tool sandbox").

---

### P1-2 · SEC-03 — Upload cap applied after the full body is read; no decompressed-size bound

- **Component:** `app/api/routes/documents.py:33` (`data = await file.read()`) · `app/knowledge/ingestion.py:84` (the cap, applied after) · `app/knowledge/extraction.py:118-125` (`docx.Document()` on an arbitrary ≤20 MB zip)
- **Problem:** The 20 MB limit is enforced only once the entire body is in memory. A DOCX is a zip and is decompressed with no bound on the expanded size.
- **Why it matters:** Starlette spools above ~1 MB to disk, so a large upload is disk pressure followed by memory pressure at `.read()`; a 20 MB archive can expand to gigabytes of XML inside `python-docx`. Both require an authenticated client, so this is an insider or leaked-key scenario rather than an anonymous one — which is why it is P1 and not P0.
- **Implementation direction:** Stream and abort at the limit rather than buffering, or check `content-length` before reading with a hard ceiling behind it. Bound decompressed size when opening a DOCX. Adjacent, small, same file: an invalid `classification` form value raises `ValueError` from `Classification(...)` at `ingestion.py:115` and surfaces as a 500 via the generic handler (`app/main.py:138`) rather than a 400 — validate it at the route boundary.
- **Existing rule reference:** `app/knowledge/extraction.py:1-8` (an unreadable format is an explicit error, never silence) · `docs/security.md`.

---

### P1-3 · SEC-04 — Qdrant runs unauthenticated on a network shared with two third-party images

- **Component:** `docker-compose.yml:65` (`QDRANT__SERVICE__API_KEY: ${QDRANT_API_KEY:-}`) · `scripts/setup.sh:22,27` (generates four secrets, not this one) · `.env.example:25` (ships empty)
- **Problem:** Every other required secret in the compose file uses `${VAR:?}` to refuse to start when unset — `POSTGRES_PASSWORD` (`:49`), `N8N_ENCRYPTION_KEY` (`:90`), `WEBUI_SECRET_KEY` (`:119`). Qdrant alone uses `:-`, defaulting to no authentication.
- **Why it matters:** Qdrant publishes no host port, so this is not internet-exposed. But it shares the `ai-helper` network with `n8nio/n8n` — which exists to run operator-authored workflows with HTTP nodes — and `ghcr.io/open-webui/open-webui`. The per-client isolation the gateway enforces carefully at the API is absent one layer down: anything on that network reads or writes every client's vectors and payloads. The gateway is a front door with a good lock on a room that has another door.
- **Implementation direction:** Generate `QDRANT_API_KEY` in `setup.sh` alongside the other four, switch the compose entry to `${QDRANT_API_KEY:?set QDRANT_API_KEY in .env}`, and confirm `Runtime._connect_qdrant` passes it (it already accepts `api_key=self.settings.QDRANT_API_KEY`). Note this is a breaking change for existing deployments — document it in `docs/CHANGELOG.md` with the migration step.
- **Existing rule reference:** the `${VAR:?}` pattern already used three times in the same file · README "Per-client isolation" · `docs/deployment.md`.

---

### P1-4 · PROMPT-01 — The context fence can be closed by the content it fences

- **Component:** `app/local_ai/prompts.py:81` (`block = f"<<<CONTEXT {header}\n{body}\nCONTEXT>>>"`, `body` unescaped)
- **Problem:** A document containing the literal string `CONTEXT>>>` terminates the fence early. Text after it appears to the model as though it were outside any untrusted block.
- **Why it matters:** `app/validation/safety.py:18-19` names this fencing as "the real defence" against injection, with pattern detection explicitly described as advisory. `docs/LIMITATIONS.md` is right that clever injection cannot be eliminated — but this specific hole is not the unsolvable part, it is a missing escape with a mechanical fix.
- **Implementation direction:** Escape or strip the delimiter sequence in `body` before interpolation, or switch to a delimiter that includes a per-request random nonce so content cannot predict it. Regression test must forge a fence boundary, which `test_retrieved_text_cannot_issue_instructions` (`tests/security/test_security.py:250`) does not — it tests instructions inside an intact fence.
- **Existing rule reference:** `app/validation/safety.py:18-19` · `docs/LIMITATIONS.md` "Prompt injection is reduced, not solved".

---

### P1-5 · Testing — the production vector backend is never exercised, and two test names overstate

- **Component:** `tests/conftest.py:36` (`QDRANT_ENABLED=False`), `:109` (`HashingEmbedder`) · `tests/unit/test_infrastructure.py:15-77` (`TestQdrantStore` against a `MagicMock`) · `tests/fallback/test_cost_saving_cycle.py:68` · `tests/security/test_security.py:382,388`
- **Problem:** Three separate issues in one area. (a) All 435 tests run on `DatabaseVectorStore`; the Qdrant store production uses has only mock-based unit coverage, and neither backend transition (P0-4) is testable as written. (b) `test_a_paraphrase_is_also_answered_locally` runs under the lexical `HashingEmbedder` with two questions sharing every content word — it proves the vector *plumbing* works, while its name asserts a capability the project's own `calibrate` gate says is unproven. (c) `test_no_endpoint_is_reachable_without_a_key_by_accident` skips every path containing `{` (line 388) — i.e. every parameterised route, which is exactly where cross-tenant access by ID lives.
- **Why it matters:** These are the three places where a green suite means less than it appears to. (c) is the most consequential: the test's name is the guarantee a reader takes away, and the body excludes the routes most likely to break it.
- **Implementation direction:** Add a Qdrant-backed integration run (docker-compose service, marked so it can be skipped offline). Rename the paraphrase test to what it proves (`…_via_the_vector_path`) and keep the real paraphrase assertion for after `calibrate` passes. Either remove the `{` exclusion and supply valid ids, or rename the test so the exclusion is visible in the name. Also add the missing regression tests named in P0-1, P0-2, P0-3, P1-1, P1-2 and P1-4 — each finding above specifies what its test must do.
- **Existing rule reference:** handover §7 ("NOT RUN is not a pass") applies to coverage as much as to gates · handover §5 (the author's own request to argue with what was decided and then tested).

---

### P1-6 · DEP-01 — The stated dependency policy is not the implemented one

- **Component:** `requirements.txt` (`pypdf>=5.0`, `structlog>=24.1`) · `Dockerfile:33-37` (installs from it directly)
- **Problem:** The file's own comment says "Pinned to a minor range: patch updates flow, a surprise major does not." Two entries carry no upper bound, and there is no lockfile or `--require-hashes` anywhere.
- **Why it matters:** `pypdf` parses untrusted uploaded files, making it the dependency where an unexpected major version matters most. Without a lock, "the image builds — 36 s cold cache, 522 MB" is not a reproducible claim; a rebuild next month resolves different versions, which also means the audit evidence for the build gate decays.
- **Implementation direction:** Bound both to a minor range consistent with the stated policy, and add a lockfile (`pip-compile`/`uv lock`) so the image is reproducible. Keep `--only-binary=:all:` — that guard is correct and should not be relaxed to accommodate a pin.
- **Existing rule reference:** the policy comment at the top of `requirements.txt` · `Dockerfile:17-22` (the `--only-binary` reasoning).

---

### P1-7 · COST-02 / SEC-07 — Two statements that will mislead the next reader

- **Component:** `app/gateway/escalation.py:120` (docstring) · `.env.example:17` + `scripts/setup.sh` (environment default)
- **Problem:** (a) `may_escalate`'s docstring claims it is "everything that can forbid an escalation, checked before any spend" — budget is not among its checks; it lives in `provider_manager.py:160-169`. (b) `ENVIRONMENT=development` is the shipped default and `setup.sh` never changes it, so the production startup guard (`config.py:141-165`), the HSTS header and the `secure` cookie flag are all inert on the README's quick-start path. `docs/deployment.md:33` documents the change; the README's install section does not mention it.
- **Why it matters:** (a) is the sentence a future engineer will trust when deciding where to add the next guard, and it will send them to the wrong function. (b) means the best security control in this repository — refusing to boot on a placeholder secret — does not fire for anyone who follows the README and stops there.
- **Implementation direction:** (a) Correct the docstring to say what it checks and name where budget is enforced; the architectural placement is right and should not move. (b) Have `setup.sh` prompt for or set `ENVIRONMENT`, or add the step to the README install block. Neither is a code-behaviour change.
- **Existing rule reference:** `app/core/config.py:141-165` (the guard being bypassed) · `docs/deployment.md:33`.

---

## P2 — NON-BLOCKING

Recorded so they are not lost. No implementation direction given.

| ID | Component | Item |
|---|---|---|
| SEC-05 | `app/api/routes/admin.py:239` | Username compared with `!=` and short-circuited before `verify_password` — a timing oracle for username validity. Low value to an attacker; inconsistent with the constant-time discipline everywhere else in `app/core/security.py`. |
| SEC-06 | `app/main.py:128` | `/docs` and `/openapi.json` are served unconditionally. `is_production` already gates HSTS and the cookie `secure` flag; OpenAPI is not gated. |
| SEC-08 | `app/gateway/router.py:405-421` | A paid answer vetoed for `safety_violation` (credential-shaped values in the output) is still returned in the response body with `success=False`. Same-client data, so not a cross-boundary leak, but the behaviour is undocumented. |
| REL-02 | `app/runtime.py:81-89` | `_connect_qdrant` swallows every exception into a warning and a silent downgrade. Visible on `/health`, which is honest — and `LIMITATIONS.md` itself notes the analogous embedder downgrade is "easy to run for months without looking." |
| REL-03 | `docker-compose.yml:37-39` | `alembic upgrade head` runs in the app container's start command. Single-replica today; two replicas starting together would race. |
| REL-04 | `Dockerfile:66`, `docker-compose.yml:38` | `--proxy-headers` without `--forwarded-allow-ips`. Latent today; becomes load-bearing the moment P0-3 lands an IP-keyed limiter. |
| REL-05 | `docker-compose.yml:116-129` | Open WebUI talks to Ollama directly, bypassing budget, privacy gate, audit trail and learning. Honestly documented in the compose comment; local-model only, so no cost or external-privacy exposure. Consequence: the audit trail is not a complete record of what the local model was asked. |
| DOC-01 | `docs/LIMITATIONS.md` | The document is load-bearing — it is the control that makes several accepted risks acceptable — and has no owner, no review cadence, and no link from code to the constraint it documents. When it drifts, "documented limitation" silently becomes "undocumented defect." |
| BL-01 | handover §6 backlog item 6 | Prompt/model version pinning on promoted solutions. More urgent than its position suggests: `SOLUTION_TTL_DAYS=180` with no correction path gives a wrong promoted answer a six-month half-life. |

---

## DELIBERATE / NOT A BUG

**Do not "fix" any of these automatically.** Each is an intentional decision with a recorded rationale, or a design property that is correct as written. Most are already argued for in `docs/LIMITATIONS.md`, which is the reason they are not findings.

| Item | Component | Why it is deliberate |
|---|---|---|
| **Validation cannot verify truth** | `app/validation/` | Explicit: a second model in the path would double the cost of the thing whose cost the system exists to reduce. `confidence` is a routing signal, documented as such. |
| **Grounding is lexical overlap, not entailment** | `app/validation/factuality.py` | Documented limitation with its failure mode named (reused vocabulary, inverted meaning). |
| **Promotion can promote a wrong answer** | `app/learning/promotion.py` | Both gates check usability, not truth — stated in `LIMITATIONS.md` and in the handover §5. This is why `AUTO_PROMOTE` defaults to false. Agreed with; see §11. |
| **The dispatcher is conservative** | `app/tools/dispatcher.py` | False negatives chosen over false positives because a level-0 wrong answer has no model in the loop. Correct asymmetry; do not "improve" matching. |
| **Rate limiter is per-process** | `app/api/ratelimit.py` | Documented, with Redis named as the next step. Note P0-3 is a *different* problem (post-auth only), not this one. |
| **Background jobs are in-process** | `app/api/jobs.py` | Documented; orphans are marked `failed` rather than left claiming to run. |
| **Database vector fallback is linear** | `app/memory/semantic.py` | Documented as a scale limitation. P0-4 is the *visibility* consequence, which is not the same thing and is not documented. |
| **Learning is per client; no sharing** | `app/learning/`, `app/memory/retrieval.py` | Ten clients pay ten times, by design. Sharing needs an explicit audited mechanism that does not exist in v1. |
| **No streaming** | `app/api/routes/chat.py` | Validation would have to run on a partial answer — a different design. Documented. |
| **English-centric text handling** | `app/validation/`, `app/privacy/` | Documented, with the Polish identifier exception explained. |
| **SQLite default** | `app/core/config.py:37` | For tests and laptops; `LIMITATIONS.md` says plainly it is not a production target. |
| **Unknown model priced at the worst known rate** | `app/cost/pricing.py:41` | Deliberately pessimistic. **Do not "optimise" this to zero or to an average** — it is the single most common way a budget system fails silently. |
| **RESTRICTED blocked outright rather than redacted** | `app/privacy/classification.py` | Because a regex cannot recognise a described person. Correct, and the reasoning should survive P0-1's fix. |
| **No LLM in any control decision** | throughout | Handover §7. Task classification, tool dispatch, escalation, budgets and privacy stay deterministic. |
| **Paid providers off by default; escalation, web search, auto-promote off or gated** | `app/core/config.py` | The whole system is functional with no API key from anyone. Do not enable anything to "see if it works." |
| **Everything in `docs/LIMITATIONS.md`** | — | Read it before treating anything above as new. It pre-empted roughly a dozen findings that would otherwise be in this report. |

---

## NOT VERIFIED

Requires runtime, container or model evidence this audit could not obtain. **Do not code against an assumption here — measure first.** Several severities above would change materially depending on what the measurement says.

| # | Item | What would settle it |
|---|---|---|
| 1 | **The 435-test / 89%-coverage / ruff-clean result.** `pytest`, `fastapi`, `pydantic` and `sqlalchemy` are absent here and installing them was not permitted. Test *source* was audited; nothing was executed. | Run the suite at HEAD and attach the output. |
| 2 | **Every one of the seven `audit/prove_*.py` suites and the 251 live checks.** Not re-run. | Re-run them; each exits non-zero on failure. |
| 3 | **Docker build, container restart, PostgreSQL persistence, Qdrant persistence.** No daemon available. The Dockerfile and compose were reviewed and are sound; that is not the same as built. | `docker compose up`, then `audit/prove_container_persistence.py`. |
| 4 | **The real-model gate.** `calibrate` exit code, embedder OK-vs-DEGRADED, real paraphrase reuse. | Handover §3, verbatim. |
| 5 | **Whether concurrent budget overshoot reproduces, and by how much.** P0-2 is derived from reading the code path, not from a measured race. | Fire N simultaneous escalating requests against a near-exhausted budget and compare recorded spend to the cap. |
| 6 | **Whether a CONFIDENTIAL document actually reaches a provider under stock settings.** P0-1 is derived from the same kind of reading. | With a fake provider, ingest a CONFIDENTIAL document, ask an INTERNAL question that retrieves it, and inspect the captured outgoing prompt. |
| 7 | **Whether the Qdrant/database split-brain reproduces end to end.** | Start with Qdrant down, ingest, bring Qdrant up, poll `/health`, then query for the ingested document. |
| 8 | **Real DOCX zip-bomb behaviour in `python-docx`.** Expansion ratios are library- and file-specific. | Feed a known bomb at the 20 MB boundary and measure peak RSS. |
| 9 | **Whether `/admin/login` under concurrent load actually exhausts the worker.** The scrypt parameters make it plausible; the threshold is deployment-specific. | Load-test the endpoint and watch RSS and latency at `WORKER_CONCURRENCY=2`. |
| 10 | **Whether `QDRANT_API_KEY` is set in any existing deployment.** The repository ships it empty; a given `.env` may differ. | Inspect the live `.env`. Determines whether P1-3 is an active exposure or a hardening step. |
| 11 | **Whether `ENVIRONMENT=production` is set in any existing deployment.** Determines whether the startup guard, HSTS and the `secure` cookie flag are live. | Inspect the live `.env`. |
| 12 | **Actual `pow()` cost at the extremes.** Measured up to `pow(3, 10**7)` = 2.05 s; `pow(3,pow(3,17))` was reasoned about, not run, because running it is the denial of service. | Bound it in a sandbox with a hard timeout, or simply fix P1-1 and do not measure it. |

---

*End of handoff. This document adds no code, changes no behaviour and authorises nothing. It is an input to the production gate, not a substitute for it — and per `docs/HANDOVER_TO_FABLE.md` §7, nothing in it may be marked PASS on the strength of having been read.*
