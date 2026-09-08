# AI Helper — handover for the next auditor

> **Update — 2026-09-08 final audit (branch `claude/ai-helper-final-audit-uv46bj`).**
> A second, independent line-by-line audit ran. Full report: `audit/FINAL_AUDIT.md`;
> results: `audit/RESULTS.txt`. It found and fixed **five** real defects, each with
> a regression test in `tests/security/test_audit_findings.py`:
> 1. **Retrieved context bypassed the classification gate** — RESTRICTED memory /
>    CONFIDENTIAL chunks retrieved for an INTERNAL question were sent to the paid
>    provider. The request is now raised to the highest classification across the
>    message and everything retrieved. *(HIGH, privacy.)*
> 2. Auth-failure and rate-limit refusals left no audit row (rolled back) →
>    `audit.record_durable`.
> 3. A billed CostRecord could be discarded by a failure in post-call bookkeeping →
>    those steps are now guarded.
> 4. Bad classification / cross-client `conversation_id` returned 500 → now 422 / 404.
> 5. `/costs` leaked every client's provider/model breakdown → scoped per client.
>
> State now: **445/445 tests (3 consecutive runs), 89% coverage, ruff clean**; the six
> network-free audit suites pass; the Docker build (via the `pip_ca` CA secret) and
> the **30/30 container-persistence gate** pass on an isolated daemon. The scope rule
> was honoured absolutely: only this repository was touched.
>
> **Production status is still NOT APPROVED, for exactly one reason:** no real model
> weights are obtainable here (registry.ollama.ai / huggingface.co / ollama.com all
> 403), so the Real Ollama and calibration gates cannot run. `calibrate` correctly
> exits 1 on the lexical fallback. Everything below still applies.
>
> ---


You are taking over an audit of **AI Helper**, a self-hosted local-first AI
gateway. The previous engineer built it and then audited it, which is the
weakness this handover exists to correct: the same judgement that made the
design decisions also wrote the tests that confirm them. Your most valuable
work is not re-running what already passes — it is disagreeing with what was
decided.

---

## 1. Scope

**In scope:** this repository only.

**Out of scope, and must not be touched, imported, referenced or integrated:**
accounting, SignalMesh, LokalnyDowoz, spa booking, or any other application.
AI Helper stays an independent project until it passes its own production
gate. There is no "while I'm here" integration.

**Feature freeze.** Do not add features, redesign the architecture, or change
routing, memory, privacy, security, cost, learning or validation — *unless you
find a defect*. A defect you find is in scope to fix, with a regression test.
Everything else waits.

---

## 2. Where it stands

```
Version           1.0.0
Commit            2198864
Branch            claude/self-hosted-ai-helper-ew0x2m

Tests             435 passed, 0 failed, 0 skipped, 89% coverage, ruff clean
Live audits       251 checks across 7 suites, all passing
Code              11,579 lines app · 4,240 tests · 2,076 audit · 1,629 docs
API               35 endpoints

PRODUCTION STATUS NOT APPROVED — one blocker, see §3
```

Gate status:

```
Real Ollama (real weights)   NOT RUN   ← blocker
Calibration                  FAIL      ← blocker (same cause)
Local-first routing          PASS
Fallback                     PASS
Learning / validation        PASS
Promotion                    PASS
Memory reuse (exact match)   PASS
Memory reuse (paraphrase)    NOT PROVEN
Cost controls                PASS
Privacy                      PASS
Security / auth / authz      PASS
Docker build                 PASS   36s cold cache, 522 MB
Container restart            PASS   30/30, twice
PostgreSQL persistence       PASS
Qdrant persistence           PASS
Full regression suite        PASS   twice consecutively
```

Read `audit/AUDIT_REPORT.md` for the detail. Eight defects were found and
fixed across two audit passes; each has a regression test.

---

## 3. The one blocker

**No real language model has ever run against this system.**

The build environment refused every model-weight source — `registry.ollama.ai`,
`huggingface.co`, `ollama.com` all returned 403 by network policy; only pypi
was reachable. So every "local model" and "paid provider" in the audit is a
protocol-faithful HTTP stand-in. The real `OllamaClient`, `ModelManager`,
`AnthropicProvider`, gateway, validation, cost tracker and database all execute
exactly as in production — but the thing answering is a rule, not a network.

If your environment can reach `registry.ollama.ai`, you can close this in about
an hour:

```bash
docker compose up -d
docker compose exec ollama ollama pull nomic-embed-text
docker compose exec ollama ollama pull llama3.2:3b

docker compose exec ai-helper python -m app.cli calibrate   # MUST exit 0
./scripts/health_check.sh                                   # embedder must read OK, not DEGRADED
python audit/demo_e2e.py                                    # re-run against the real model
```

`calibrate` currently exits 1 and says the lexical fallback embedder cannot
separate a paraphrase from unrelated text. That is the gate working correctly,
not a bug. Until it exits 0, learned solutions will not be reused for a
reworded question and the system pays for the same problem repeatedly.

Then the part that actually takes time, and that nobody has done:

**Run 50–100 real questions with paid providers disabled.** Watch
`local_success_rate` and `escalations_blocked` on `/api/v1/usage`. Tune
`CONFIDENCE_THRESHOLD` against what a real 3B model actually produces. This
decides whether the economics work, and it is pure guesswork right now.

---

## 4. How to verify everything

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest                      # 435 tests, no external services

.venv/bin/python audit/demo_e2e.py                          # 27 checks
.venv/bin/python audit/prove_cost.py                        # 25
.venv/bin/python audit/prove_privacy_and_permissions.py     # 54
.venv/bin/python audit/prove_security.py                    # 51
.venv/bin/python audit/prove_learning.py                    # 29
.venv/bin/python audit/prove_persistence.py                 # 35
.venv/bin/python audit/prove_container_persistence.py       # 30  (needs the stack up)
```

Each exits non-zero on any failure. `audit/README.md` explains what each proves
and, importantly, what it does not.

If Docker Hub is blocked in your environment, `mirror.gcr.io` worked here:

```json
/etc/docker/daemon.json
{ "registry-mirrors": ["https://mirror.gcr.io"] }
```

---

## 5. Where a second opinion is worth most

These are things I *decided*, then tested. A passing test proves the code does
what I intended — not that I intended the right thing. Please argue with these.

**The confidence weights.** `app/validation/confidence.py` has five weighted
signals summing to 1.0 (structure .20, decisiveness .15, grounding .30,
retrieval .20, tool agreement .15) and a `CONFIDENCE_THRESHOLD` of 0.62. Every
one of those numbers is a judgement call, calibrated against a stand-in that
answers by rule. They directly control how much money the system spends. They
are the least evidence-backed thing in the repository.

**The promotion gates.** `app/learning/promotion.py` promotes an answer if it
validates *and* the local model can restate it with the answer in front of it.
Both check **usability, not truth**. A confident, well-formed, wrong answer from
a paid provider passes both and is then served from memory for
`SOLUTION_TTL_DAYS` (180). Is a reproduction gate that only asks "can you
parrot this back" worth what it costs? I think yes; I would like to be argued
with.

**The dispatcher's conservatism.** `app/tools/dispatcher.py` answers only
unambiguous shapes — `"What is 1200 * 0.23?"` matches, `"roughly what is 1200
times 23 percent"` does not. I chose false negatives over false positives
because a level-0 wrong answer has no model in the loop to catch it. That may
be leaving free answers on the table.

**Two threshold pairs.** Semantic and lexical embedders score on different
scales, so config carries a pair for each (`app/memory/thresholds.py`). The
lexical pair is set from a measured distribution; the *semantic* pair (0.72 /
0.80) is inherited convention and has never been measured against a real model.
`ai-helper calibrate` exists to check it — run it, don't trust it.

**Classification is regex.** `app/privacy/classification.py` finds credential
shapes and common identifiers. It cannot recognise that "the client on the
third floor of the Warsaw office" identifies someone. That is why RESTRICTED is
blocked outright rather than redacted — but check whether the detector's
coverage matches what your data actually looks like.

**Everything in `docs/LIMITATIONS.md`.** Short, and the honest half of the
README. Read it before trusting anything.

---

## 6. On "world class"

Worth being precise, because the comparison in the original brief is a
category error for three of the four repositories:

| Repo | What it is | Relationship |
|---|---|---|
| `ollama/ollama` | local inference runtime | AI Helper **runs it** as a service |
| `open-webui/open-webui` | chat UI | AI Helper **ships it** as an optional surface |
| `n8n-io/self-hosted-ai-starter-kit` | compose bundle (n8n + Ollama + Qdrant + Postgres) | AI Helper **is a superset** — same services, plus the gateway |
| `mudler/LocalAI` | OpenAI-compatible API over local models | the one genuine alternative, at a **different layer** |

AI Helper is not competing with Ollama any more than a web app competes with
PostgreSQL. It is a **governance and learning layer** that sits on top. Claiming
it is "better than Ollama" would be nonsense and would damage credibility with
anyone technical.

What it genuinely does that none of those four do:

- **Cost governance with a hard stop** — per-request, daily, monthly and
  per-client budgets, a pessimistic pre-flight check, and no override path.
- **A privacy classification gate** — RESTRICTED data cannot reach an external
  provider, refused in two independent places.
- **Learning from fallback, behind gates** — a paid answer is not trusted
  because it was expensive; CANDIDATE → VALIDATED → PROMOTED.
- **An append-only audit trail** that records what was refused as well as what
  was sent.
- **Per-client isolation** of memory, documents, solutions and logs.

That combination is genuinely uncommon. It is also, right now, unproven against
a real model — so it is a good design, not yet a world-class product.

### What would actually make it world class

Roughly in order of what I would do first. **None of this is authorised yet** —
it is a backlog for after the production gate, not work to start now.

1. **An evals harness.** The single biggest gap. There is no way to measure
   whether a change to the confidence weights makes answers better or worse.
   A fixed question set with expected outcomes, run on every change, reporting
   local-success-rate and cost. Without it, every threshold is superstition.
2. **Streaming responses.** A 3B model on CPU takes 10–30 seconds and the API
   returns nothing until it is done. Streaming means validation has to run on a
   partial answer, which is a real design problem — but users notice this more
   than anything else on the list.
3. **Redis for rate limiting, and a real job queue.** Both are per-process
   today (`docs/LIMITATIONS.md`). That caps the deployment at one worker.
4. **Reranking.** Retrieval is a single vector search. A cross-encoder rerank
   over the top ~20 is the highest-value quality improvement in RAG, and would
   directly reduce escalations.
5. **Multi-tenant knowledge sharing, deliberately designed.** Ten clients
   asking the same hard question pay ten times today. Sharing needs an
   explicit, audited mechanism — not an accident.
6. **Prompt/version pinning on promoted solutions.** A solution promoted under
   one model and one prompt is being reused under another. Record the model and
   prompt version, and expire on change.
7. **OpenTelemetry.** Structured logs are good; traces across gateway →
   retrieval → model → validation would be better.
8. **A real security review by someone who did not write it**, focused on the
   tool sandbox and the classification detector.

Items 1 and 2 are what separate "an impressive private system" from "something
you would put in front of other people".

---

## 7. What not to do

- Do not integrate any other application. Not yet, not partially.
- Do not add an LLM to a control decision. Task classification, tool dispatch,
  escalation, budgets and privacy are deterministic on purpose — a classifier
  that needed a model would be a model call on every request, including the
  ones a tool answers for free.
- Do not weaken a gate to make a test pass. If `calibrate` fails, fix the
  embedder or the threshold — do not lower the bar.
- Do not enable paid providers to "see if it works" before step §3 is done.
- Do not commit `.env`, and do not give the AI unrestricted shell, Docker, git
  or production access.
- Do not mark anything PASS from static inspection. If it was not executed, it
  is NOT RUN, and NOT RUN is not a pass.

---

## 8. The report to return

Same format as `audit/AUDIT_REPORT.md`. For every failure:

```
Issue:
Severity:
Cause:
Fix:
Regression test:
Verification:
```

And the verdict, which stays NOT APPROVED if **any** line is FAIL, NOT RUN or
UNKNOWN:

```
Real Ollama · Local-first · Fallback · Learning · Validation · Promotion ·
Memory reuse · Calibration · Cost · Privacy · Security · Authentication ·
Authorization · Docker build · Container restart · PostgreSQL persistence ·
Qdrant persistence · Full regression suite
```
