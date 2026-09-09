# Limitations

The honest half of the README. Everything here is a real constraint of this
build, not a hypothetical.

## Validation cannot verify a free-text answer

The validation layer detects specific, mechanical failure modes: an empty
answer, a refusal, an invalid format, a degenerate loop, a claimed action, a
leaked credential, a number asserted that the sources do not contain, a
polarity flip against retrieved text, and low grounding.

It cannot tell you an answer is *true*. Nothing short of a second model or a
human can, and this system deliberately does not put a second model in the
path — that would double the cost of the thing whose cost it exists to reduce.

**Consequence:** a fluent, well-grounded, confidently-scored answer can still
be wrong. `confidence` is a routing signal. Treat it as one.

## Grounding is lexical overlap, not entailment

`factuality.py` measures how much of the answer's vocabulary appears in the
retrieved context. An answer that reuses the source's words while inverting
their meaning scores well on grounding; the polarity check catches some of
those and not all.

## The offline embedder is not semantic

Without an embedding model installed, retrieval falls back to a hashed
bag-of-words vectoriser. It matches wording, not meaning: it will find "what's
the VAT rate?" from "what is the VAT rate" and will not find it from "how much
sales tax do I charge".

This is reported — `/health` shows the embedder as `DEGRADED`, `/api/v1/models`
reports `embedder_semantic: false`, the dashboard says so — but it is easy to
run for months without looking. Install `nomic-embed-text`.

## Paraphrase reuse cannot tell a variant from a paraphrase

Measured on the real embedder (`nomic-embed-text`, 40 pairs of each kind,
`audit/measure_embedder.py`): a paraphrase of a learned question scores a
median 0.85 against it; the *same question with one answer-changing detail
swapped* ("VAT in Poland" → "VAT in Germany", "monthly" → "quarterly",
"2025" → "2026") scores a median 0.84, up to 0.99. The two populations
overlap. No cosine threshold separates them, and the lexical witness makes it
worse rather than better: a one-detail variant shares most of its words with
the original, a genuine paraphrase often shares none.

**Consequence:** `SOLUTION_REUSE_THRESHOLD` (0.80) is a scale check, not a
safety boundary. It keeps unrelated text out (0/40) and admits few paraphrases
(11/40) — and it admits most one-detail variants (25/40). Lowering it to gain
recall admits more variants for almost no paraphrase gained (38/40 at 0.69 for
+1 paraphrase), which is why `calibrate` refuses to advise that. The guard
that actually holds for a variant is the local model's context discipline: it
is handed the stored answer as evidence and must say `INSUFFICIENT_CONTEXT`
rather than answer the variant from it. Measured with llama3.2:3b
(`audit/measure_reuse_discipline.py`) it did so in 14 of 20 cases and carried
a wrong detail over in 1–2. That residual is real. Keep `AUTO_PROMOTE=false`
until the promoted set is small and reviewed, and read `solution_id` on
answers that matter.

Exact-fingerprint reuse (the literally repeated question) has none of this
problem and is where the saving actually comes from today.

## Retrieval thresholds are measured for one embedder

The semantic pair (`MEMORY_SIMILARITY_THRESHOLD` 0.55, `SOLUTION_REUSE_THRESHOLD`
0.80) was measured on `nomic-embed-text`. A different embedding model scores
on a different scale; run `python -m app.cli calibrate` after changing
`EMBEDDING_MODEL` and read its output rather than trusting the numbers. Even
on nomic, a question against a long multi-fact chunk scores lower than
against a paraphrase (median 0.59 vs 0.85), so two of ten handbook questions
still miss their chunk at 0.55 — shorter, single-topic documents retrieve
better than long ones. `nomic-embed-text` also expects the task prefixes
`search_query:` / `search_document:`, which lift asymmetric scores by roughly
0.05–0.10; this build does not send them (it would need a configurable,
model-specific prefix and a reindex) and that is the documented next step
for retrieval quality.

## Prompt injection is reduced, not solved

Retrieved text is fenced and marked untrusted, the system prompt forbids
following instructions inside it, flagged requests do not become learning
material, and an answer that echoes injection phrasing fails validation.

A sufficiently clever injection in a document can still influence an answer.
No known technique eliminates this. Treat ingested documents as data from
whoever supplied them.

## The rate limiter is per process

A token bucket in this process's memory. Two uvicorn workers means twice the
effective limit, and a restart resets every bucket. It is a guard against a
runaway client and an accidental loop, not a security boundary against a
determined attacker. Redis is the documented next step.

## Background jobs are in-process

The queue lives in this process. A restart abandons anything running — those
rows are marked `failed` with an explanatory message rather than left claiming
to run, but the work is gone and must be resubmitted. Jobs do not spread across
replicas. Celery or RQ would replace `app/api/jobs.py`; the `jobs` table and
the API contract stay as they are.

## The database vector fallback is linear

When Qdrant is unavailable, semantic search becomes a brute-force cosine scan
over that client's points inside the relational database. Durable and correct,
fine into the tens of thousands of points, and not a Qdrant replacement at
scale. `/health` says which backend is live.

## Prices drift

`app/cost/pricing.py` carries rates verified on the date at the top of the
file. Providers change prices. An unknown model is charged at its provider's
worst known rate — deliberately pessimistic, because a budget that
under-counts is worse than one that over-counts — but a *changed* price on a
*known* model will be wrong until the table is updated. Review it monthly
against the providers' published rates.

`estimated_money_saved_usd` is a counterfactual, not an invoice: requests
answered without paying, times the mean cost of the paid calls actually made.
It assumes each locally-answered request would otherwise have cost about what
an escalated one costs, which is an assumption, not a measurement.

## Classification is pattern matching

The detector finds credential shapes and common personal identifiers. It does
not understand context. It over-classifies (a long order number can read as a
phone number, costing a possible escalation) and it will miss sensitive
information that carries no recognisable pattern — a person described rather
than named, a figure that is confidential because of what it is rather than
how it looks.

That is exactly why `RESTRICTED` is blocked outright rather than redacted, and
why `EXTERNAL_ALLOWED_CLASSIFICATIONS` defaults to `PUBLIC,INTERNAL`. Set a
client's `default_classification` to `CONFIDENTIAL` when its data is
categorically sensitive, rather than relying on the detector to notice.

## Promotion can promote a wrong answer

Both gates check *usability*, not *truth*: does the answer validate, and can
the local model work with it. A confident, well-formed, wrong answer from a
paid provider passes both and is then served from memory for
`SOLUTION_TTL_DAYS`.

This is why `AUTO_PROMOTE` defaults to false. Review candidates at
`/admin/solutions` until you trust the pattern of decisions, and remember that
rejecting matters as much as promoting.

## Learning is per client

A solution learned for one client is never offered to another — the same
isolation rule that keeps their documents apart. Ten clients asking the same
hard question pay for it ten times. Sharing knowledge between clients would
need an explicit, audited mechanism that does not exist in v1.

## The dispatcher is conservative on purpose

Level 0 answers only unambiguous request shapes. "What is 1200 * 0.23?" is
matched; "roughly what is 1200 times 23 percent" is not, and goes to the model.
A false positive there returns a confidently wrong answer with no model in the
loop, so the bias is toward declining. Everything it declines costs nothing
extra.

## SQLite is for tests and demos

The default `DATABASE_URL` is SQLite so the suite and a laptop run need no
services. It is not a production target: concurrent writes serialise, and the
job runner and API contend. Use PostgreSQL.

## No streaming

`/api/v1/chat` returns a complete answer. A 3B model on CPU can take 10–30
seconds, so set proxy timeouts accordingly (`docs/deployment.md`) and use
`/api/v1/tasks` for anything long. Streaming would need the validation layer to
run on a partial answer, which is a different design.

## English-centric text handling

Stopwords, hedge phrases, refusal patterns and action-claim patterns are
English. Polish and other languages will produce worse grounding scores and may
miss a refusal or an action claim. The classification detector includes Polish
identifiers (NIP, PESEL) because those were the concrete case to hand.
