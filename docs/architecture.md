# Architecture

## The shape of it

```
                    application / user
                             │  API key
                    ┌────────▼─────────┐
                    │      FastAPI     │  auth · rate limit · request id
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  GatewayRouter   │  the whole routing decision
                    └────────┬─────────┘
        ┌────────────┬───────┴───────┬──────────────┐
        │            │               │              │
   ToolRegistry  Retriever    ProviderRegistry  CostTracker
   (level 0)     (level 1)    (levels 2 and 4)  (the money)
        │            │               │              │
        │       ┌────┴────┐     ┌────┴────┐         │
        │    Qdrant   Postgres  Ollama  paid API    │
        │    (or the  (memory,  (local)  (opt-in)   │
        │     DB      solutions,                    │
        │     store)  documents)                    │
        └────────────┴───────┬───────┴──────────────┘
                             │
                     ValidationPipeline
                             │
                     PromotionPipeline  →  learned solutions
```

## The routing ladder

`GatewayRouter.handle` walks exactly one path. Each level is cheaper than the
next, and each is tried before the next.

### Level 0 — deterministic tools (`app/tools/`)

Arithmetic, dates, JSON, document search. Zero tokens, zero cost, exactly
right. The dispatcher (`app/tools/dispatcher.py`) is deliberately
conservative: it fires only on unambiguous request shapes, because a false
positive here returns a confidently wrong answer with no model in the loop to
catch it. Everything it declines falls through, which costs nothing extra.

There is **no general executor**. No `run_command`, no `eval`, no filesystem
write, no arbitrary HTTP. A tool is a named Python function with a declared
input schema, output schema, permission set and risk level, and the registry
refuses to register one that omits any of those.

### Level 1 — retrieval (`app/memory/retrieval.py`)

Four sources, consulted in this order:

1. **Promoted solutions, exact fingerprint.** The same question asked twice
   must never be paid for twice. The fingerprint is a hash of the normalised
   question, so it is independent of the embedding model and keeps working
   when that model changes.
2. **Promoted solutions, vector similarity.** Catches the paraphrase. A vector
   hit is corroborated by lexical overlap before it is trusted enough to answer
   from — one similarity number is one witness, and one witness is how you get
   a confident answer to a question nobody asked.
3. **Long-term memory** for this client.
4. **Document chunks** for this client.

Only `PROMOTED` solutions are returned. A `CANDIDATE` is a record, not
knowledge.

### Level 2 — the local model (`app/local_ai/`)

The model class is chosen from the task type (`TASK_MODEL_CLASS`), never
hard-coded, and degrades gracefully to whatever is installed. Retrieved
material goes into the prompt as *evidence with provenance*, fenced and marked
untrusted, so a document cannot issue instructions to the model.

### Level 3 — validation (`app/validation/`)

Four stages, then a score:

| Stage | Question it answers |
|---|---|
| `output.py` | Did the model produce an answer, in the shape we asked for? |
| `safety.py` | Did it leak a credential or claim to have performed an action? |
| `factuality.py` | Is the answer supported by what we retrieved? |
| `confidence.py` | Combining all of that, do we believe it? |

**The model's own claimed confidence is never used.** Confidence is computed
from observable properties — structure, decisiveness, grounding, retrieval
quality, agreement with a deterministic tool — and it is a routing signal, not
a claim of correctness.

Some signals are vetoes rather than weights. An empty answer, an invalid
format, a refusal, a safety violation or a detected contradiction cannot be
averaged away by good scores elsewhere.

What the validation layer honestly cannot do is *verify* a free-text answer.
Without a second model there is no such check. It detects specific, mechanical
failure modes; it does not certify truth. See `docs/LIMITATIONS.md`.

### Level 4 — escalation (`app/gateway/escalation.py`)

Two questions, kept apart on purpose:

- `why_escalate()` — *should* this go to a paid provider? Answers with exactly
  one `EscalationReason`, which is the field that later answers "why are we
  paying for AI?".
- `may_escalate()` — *is it allowed to*? Answers with an
  `EscalationBlockReason` when not: disabled, not configured, client not
  permitted, task type denied, classification blocked.

Both must say yes. Then `PaidProviderManager` applies, in order: the
classification gate again, redaction, a per-provider budget check against the
redacted prompt, the call, cost recorded from the provider's own token counts
(whether it succeeded or failed — a failed call still consumed input tokens),
and an audit row naming the provider, model, reason and cost but never the
content.

## Learning (`app/learning/`)

```
paid answer
    │
    ├─ empty? RESTRICTED? injection-flagged? ──► not captured, and the
    │                                            response says why
    ▼
CANDIDATE  ── recorded with the question, the local attempt, the failure
    │          reason, the provider, the answer and its validation
    │
    ├─ gate 1: does it pass the validation pipeline on its own terms?
    │          no ──► REJECTED
    ▼
VALIDATED
    │
    ├─ gate 2: hand it back to the LOCAL model as context and ask the
    │          original question again. Can the local model produce a
    │          passing answer with the solution in front of it?
    │          no  ──► REJECTED   (promoting it would buy nothing: retrieval
    │                              would find it and the request would
    │                              escalate anyway)
    │          cannot check ──► held at VALIDATED, never silently promoted
    ▼
PROMOTED   ── indexed, and only now offered back as context
```

`EXPIRED` is the fifth state: an answer that was right last March is not
automatically right today (`SOLUTION_TTL_DAYS`).

A promotion whose indexing fails is **rolled back** to VALIDATED. A PROMOTED
row that is not in the index would never be found again, which is worse than
not promoting it.

## Cost control (`app/cost/`)

The only thing standing between a bug and a bill.

- Every paid call has a pre-flight check, and the check is **pessimistic**: it
  assumes the response will be the full `max_tokens`, so a budget can be
  approached but not overshot by a request the system chose to make.
- Every completed call is recorded from the provider's own reported counts.
- An **unknown model is priced at its provider's worst known rate**, never at
  zero. A budget that under-counts is worse than one that over-counts.
- When a budget is reached, paid providers stop. There is no "just this once"
  path, and `tests/gateway/test_critical_regressions.py::test_7*` proves it.

## Privacy (`app/privacy/`)

Every request carries a classification, from three sources in descending
authority: what the client declared, the client's configured floor, and what
the detector infers. **The detector is a floor, not a ceiling** — it can only
push a request to a more sensitive class. A pattern matcher that could
declassify data would be a hole, not a feature.

`RESTRICTED` never leaves, refused before any configuration is consulted.
Redaction is applied *in addition to* the classification gate, never instead
of it: a regex cannot recognise that "the client on the third floor of the
Warsaw office" identifies someone, which is exactly why RESTRICTED is blocked
outright rather than redacted.

## Isolation

Every row that can hold client data carries `client_id`, and every query
filters on it **in the query**, not by discarding results afterwards. The
Qdrant backend additionally drops any returned point whose payload names a
different client, so a filter bug cannot become a data leak. Tools receive
`client_id` from the authenticated identity, never as an argument, so a model
cannot ask for another client's namespace.

## Storage

| Store | Holds | If it is unavailable |
|---|---|---|
| PostgreSQL | clients, memory, solutions, documents, request log, audit, costs, jobs | the service is down; this is the system of record |
| Qdrant | vectors | falls back to a durable table in PostgreSQL; `/health` says so |
| Ollama | local inference | escalates with `LOCAL_MODEL_UNAVAILABLE`, or fails honestly |

The Qdrant fallback is a brute-force cosine scan. It is durable and correct,
linear in the number of points for one client, fine into the tens of thousands
— and it is not a Qdrant replacement at scale.

## Embeddings, and a trap worth naming

Two implementations:

- `OllamaEmbedder` — real semantic embeddings. What a deployment should run.
- `HashingEmbedder` — a deterministic **lexical** vectoriser. It has no
  semantic understanding at all: it matches "what is the VAT rate" to "what's
  the VAT rate?" and will not match it to "how much sales tax do I charge". It
  exists so the system is fully functional and testable with no model server,
  and so a broken embedding model degrades retrieval instead of taking the
  gateway down.

The two score on **different scales** — a real embedding model scores unrelated
text around 0.3–0.5, a hashed bag-of-words scores it near 0.0 — so a single
threshold cannot serve both, and the config carries a pair for each. The
lexical threshold is set from a measured distribution, not from taste, and
`tests/memory/test_memory.py::TestThresholdsAreEvidenceBased` fails if a change
closes the gap it sits in.

Vectors from different embedders live in **separate collections** and are never
compared. Changing `EMBEDDING_MODEL` therefore invalidates nothing: it starts a
new collection, and the old one stops being read.

## Agents (`app/agents/`)

An agent is a *named routing profile*, not a second brain. It contributes a
system-prompt fragment, a default task type and a narrowed tool set — and it can
only ever narrow what the client may already do. Everything still goes down the
same ladder, is still validated, budget-checked and privacy-gated. An agent
framework that could bypass the Gateway would be a second, unaudited path to a
paid provider.

Four generic agents ship: `general`, `research`, `document`, `developer`. None
of them knows anything about accounting, trading, delivery or bookings; those
belong to the applications that connect later, and adding one is a new
`AgentSpec` with no Gateway change.

## What is deliberately not here

- **No LLM in a control decision.** Task classification, tool dispatch,
  escalation, budgets and privacy are deterministic code. A classifier that
  needed a model would be a model call on every request, including the ones a
  tool answers for free.
- **No business logic in the Gateway.** Clients differ only in permissions,
  budgets and namespaces — all data.
- **No autonomous action.** Advisory only, and an answer that claims otherwise
  fails validation.
- **No microservice split.** One Python service, one database, two optional
  sidecars. It can be split later; splitting it first would buy operational
  complexity before it bought anything else.
