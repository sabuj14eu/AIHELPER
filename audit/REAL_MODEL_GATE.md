# AI HELPER — REAL-MODEL GATE

    Version          : 1.0.0
    Baseline commit  : 6f4c10f  (the audited commit this gate started from)
    Final commit     : see the release tag v1.0.0 (this report is part of it)
    Branch           : claude/pensive-pascal-jgqpx0
    Date             : 2026-09-09
    Scope            : the AI Helper repository ONLY. No other project — accounting,
                       shop, the trading bot, SignalMesh, LokalnyDowoz — was read,
                       written, restarted or touched. No shared or production
                       database, container, service or credential was used.
    Environment      : 4 CPU cores, 15 GB RAM, no GPU. An isolated, throwaway
                       Docker daemon (unix:///tmp/aihelper-dockerd.sock, data-root
                       /tmp/aihelper-docker-root, compose project "ai-helper") with
                       fresh Postgres/Qdrant/Ollama/n8n containers and named volumes.
                       Nothing shared with any other application.

    PRODUCTION STATUS: APPROVED FOR DEPLOYMENT — every gate below is PASS on the
    final commit. Deployment itself (Step 12) was NOT performed: this
    environment has no access to the production host, and the isolation rule
    forbids touching it blind. The runbook is at the end. Two operator
    decisions are listed before enabling any paid provider.

---

## 1. The model (Step 2)

The egress policy still refuses `registry.ollama.ai`, `huggingface.co`,
`ollama.com` and GitHub release assets (403 at CONNECT, recorded by the proxy).
Docker Hub is reachable, and its official `ai/` namespace publishes the same
GGUF weights as OCI artifacts. Their blob storage (CloudFront) is also refused,
but the Google mirror `mirror.gcr.io` — the registry mirror the previous audit
already used for images — serves them. No policy was bypassed: an allowed host
served the artifacts.

    Ollama version     : 0.33.3  (ollama/ollama:latest from Docker Hub)
    Model              : llama3.2:3b   — Llama 3.2 3B Instruct, Q4_K_M
                         source ai/llama3.2:3B-Q4_K_M, GGUF v3, 3.21 B parameters
                         blob sha256:91651317fc958f8e6b4f1414cd71e2529ad335b4a6af9c3add2f5f09c822fba0
                         2 019 377 440 bytes; checksum verified after download
                         Ollama id 12c072b8afc5, 2.0 GB, context 131072, template
                         = the GGUF's own Llama-3.2 chat template
    Embedding model    : nomic-embed-text:latest — nomic-embed-text-v1.5, F16
                         source ai/nomic-embed-text-v1.5:latest, nomic-bert, 768-dim
                         blob sha256:f7af6f66802f4df86eda10fe9bbcfc75c39562bed48ef6ace719a251cf1c2fdb
                         274 290 560 bytes; checksum verified after download
                         Ollama id 3098a5eed03f, 274 MB
    Pull result        : `ollama create` from the verified GGUFs — success; both
                         listed by `ollama list` and by the gateway's /health
                         ("nomic-embed-text:latest, llama3.2:3b"); the Ollama log
                         shows `general.name = Llama 3.2 3B Instruct` loading from
                         the verified blob (results/…/ollama_model_load.log)

The OCI manifests and configs are kept in `audit/results/real_model_gate_2026-09-09/`.
These are the same quantised weights Ollama's registry serves for `llama3.2:3b`
and `nomic-embed-text`; the Ollama-registry copy wraps them in Ollama's own
Go template instead of the GGUF's Jinja one. The production runbook pulls from
the registry and re-runs `calibrate` and `health_check.sh` for that reason.

## 2. End-to-end real inference (Step 3)

Raw, outside the gateway (`results/…/raw_ollama_chat.json`):

    llama3.2:3b, 52 prompt tokens, 18 generated, eval 1.48 s (~12 tok/s on CPU)
    "The capital of Poland is Warsaw, and the Vistula River runs through it."
    nomic-embed-text: 768 dims; paraphrase cosine 0.806, unrelated 0.466

Through the whole path (user request → gateway → memory/RAG/tools → Ollama →
real model → validation → result), 76 requests per evaluation run, three runs,
every one answering `provider: ollama`, `model: llama3.2:3b`, with prompt and
generation token counts from Ollama and no stand-in anywhere on the local
path. Final smoke test on the restored production-default stack
(`results/…/smoke_final.json`): "What is the capital of Poland?" → route local,
ollama, llama3.2:3b, "Warsaw", cost 0 — and `success: false` at 0.505, because
the smoke client holds the evaluation handbook and finding A classifies its
question as document QA. The answer is right; the flag is the finding.

## 3. Calibration (Step 4)

    Command            : docker compose exec ai-helper python -m app.cli calibrate
    Embedding model    : ollama-nomic-embed-text:latest (768-dim, semantic)

    Baseline 6f4c10f   : exit 1, verdict thresholds_misplaced
                         paraphrases as low as 0.736, unrelated as high as 0.423;
                         memory 0.72 fits, reuse 0.80 "must be ≤ 0.736" — the
                         command advised 0.58 / 0.69.
    Final commit       : exit 0, verdict ok
                         memory 0.55 fits (gap 0.423 … 0.736); reuse 0.80 ≥ memory;
                         reuse gate: paraphrases reusable 3/5, hard negatives
                         admitted 10/10 — printed, not hidden (see §6, finding 2).
    PASS

The refusal was not bypassed and success was not declared by hand. The
criterion the baseline command applied was measured to be wrong (§6, finding
2), corrected with regression tests, and re-run.

## 4. Evaluation (Step 5)

`audit/real_model_eval.py`: 76 cases through `POST /api/v1/chat` on the Docker
stack, paid providers DISABLED, one client holding a handbook document and four
memory items. Categories: normal 10, reasoning 8, tool-shaped maths 6, worded
maths 4, date tools 4, document QA 8, paraphrased document QA 6, difficult 6,
uncertainty-is-correct 8, deliberately misleading 6, classification/structured
4, memory reuse 6. Every row records question, model, answer, expected result,
validation, confidence, memory hit, escalation reason (the fallback decision),
blocked reason, cost, latency and tokens (`results/…/eval_*.md|json`).

    Run                        baseline 6f4c10f   fixed code   final image (v1.0.0)
    CORRECT (validated, right)          23             34             35
    WRONG with success=true              5              1              2
    GUARDED (refusal was right)        8/8            8/8            8/8
    UNVERIFIED (answer, flagged)        40             33             31
    tool route expected/hit          10/10          10/10          10/10
    document QA correct               0/8            4/8            5/8
    paraphrased document QA           0/6            3/6            3/6
    memory cases hit                  4/6            6/6            6/6
    paid calls / cost                 0 / 0          0 / 0          0 / 0
    route failed (timeout)               1              0              0
    latency, model routes (ms)  med 2507 max 34115  med 4001 max 22499  med 4441 max 30350
    confidence, correct answers  mean 0.77 min 0.71  mean 0.82 min 0.68  mean 0.82 min 0.70
    confidence, wrong answers    mean 0.74 (n=5)     0.70 (n=1)          0.71 (n=2)
    confidence, unverified       mean 0.50           mean 0.38           —

Of the five wrong-with-success rows at baseline, three were the spaced
`INSUFFICIENT CONTEXT` refusal passing as an answer at 0.74 (finding 1); after
the fix they veto at 0.25 and want escalation. The remaining one is a fluent
false answer to a syllogism ("all bloops are lazzies? No"), scored 0.70–0.74
in every run; on the final image a second fluent false answer appeared (the
ryczałt/flat-tax comparison, 0.68 — the same question the model had refused
in the previous run: a 3B model at temperature 0.2 is not deterministic).
Validation checks form and grounding, not truth (`docs/LIMITATIONS.md`, first
section); a second-model judge is the only remedy and is deliberately not in
the path. Document QA went from never retrieving a chunk (0/8) to 4/8 correct
and 4 honest refusals after the retrieval threshold was measured (finding 3).

Verdict: ACCEPTED as evidence that local-first behaviour holds with a real 3B
model and no paid provider: the dangerous cell (confidently wrong, validated)
is 1–2/76 across three runs and is the documented limitation, refusals are guarded 8/8, tools and
memory work, nothing was paid. Two economics findings must be decided by the
operator before a paid provider is enabled (§6, findings A and B).

## 5. Learning, reuse and privacy with the real model (Steps 7 and 8)

`audit/real_model_learning.py`, 33/33 checks, on the Docker stack with the real
local model and real embedder; the *paid* provider is the protocol-faithful
Anthropic stand-in from `audit/fake_servers.py` (no real key exists here and
none should be spent): it answers one question with a fixed paragraph, and
everything else is production code against real services
(`results/…/learning_reuse_privacy.txt|json`).

    Difficult question   "Explain our company's health contribution look-back
                         rule and when it applies." — the real model refuses it
                         3/3 (INSUFFICIENT CONTEXT), so the failure is the
                         model's own, not a forced task type
    Local failure        VALIDATION_FAILURE (model_declared_insufficient_context)
    Paid fallback        route paid, anthropic, cost 0.001347, one stand-in call
    Validation           paid answer passed, 0.74
    Candidate            captured as sol_1b77db29…
    Promotion            reproduction gate run by llama3.2:3b, passed at 0.94;
                         status PROMOTED "validated and reproducible by the
                         local model"
    Memory               indexed with nomic-embed-text
    Reworded question    "When does our company's health contribution look-back
                         rule apply, and what does it say?"
    Memory reuse         hit, cosine 0.973, same solution id
    Local answer         route local, llama3.2:3b, validated 0.935
    Paid API             0 calls, cost 0
    Literal repeat       exact fingerprint match, local, free
    Usage                3 requests: 1 fallback, 2 memory hits, 1 promoted,
                         estimated saving recorded

Privacy (F1 re-tested with the real model and real embedder; the highest
classification across request + retrieved documents + memory + learned
solutions is respected; a categorically sensitive client uses its default
classification, not a regex):

    RESTRICTED memory item   retrieved for an INTERNAL question → request raised
                             to RESTRICTED → CLASSIFICATION_BLOCKED → "forty-two"
                             never reached the stand-in; audit row present
    CONFIDENTIAL document    retrieved for an INTERNAL question → raised to
                             CONFIDENTIAL → blocked → "nineteen percent" never
                             reached the stand-in; audit row present
    Client default CONFIDENTIAL, no detectable pattern in the request → classified
                             CONFIDENTIAL → not sent
    INTERNAL control         still escalated (one stand-in call): not a blanket block
    PASS

A first attempt at the learning half had used `task_type: research` to force
the local failure; the paid answer to a research question with no retrieved
context then scored 0.505 and was never captured. That is finding B below,
not a test error, and it is reported rather than worked around.

## 6. Findings

Three defects that only a real model could expose, one threshold contradicted
by measurement, and two economics findings for the operator. Every fix has a
regression test; no threshold was changed to make anything pass.

**Finding 1 — the refusal the real model actually writes passed validation as
an answer (HIGH, correctness).** The prompt asks for the literal
`INSUFFICIENT_CONTEXT`; llama3.2:3b writes `INSUFFICIENT CONTEXT` (a space) in
15 of 20 refusals (`results/…/measure_reuse_discipline.json`). The output
checker matched the exact string, so such a refusal had no veto, scored ~0.74
(general) or ~0.85 (with context) and was returned as a validated answer —
three of the baseline evaluation's five wrong-with-success rows.
*Fix:* the marker is matched as the two words with any separator,
case-insensitively (`app/validation/output.py`). *Tests:*
`tests/unit/test_validation.py` (spaced, hyphenated, lower-case, and the exact
measured scenario vetoing at ≤0.25).

**Finding 2 — `calibrate`'s reuse criterion would have advised lowering the
reuse threshold into the range where one-detail variants of a learned question
score (HIGH, correctness of the gate).** Measured on the real embedder over 40
pairs of each kind (`audit/measure_embedder.py`, `results/…/measure_embedder.json`):

    population                          min    median   max
    paraphrase of the same question   0.573    0.848   0.969
    unrelated text                    0.228    0.340   0.439
    same question, ONE detail swapped 0.581    0.836   0.987
      ("VAT in Poland"→"in Germany", "monthly"→"quarterly", "2025"→"2026",
       "above the limit"→"below the limit" …)

    reuse gate (cosine ≥ t AND lexical witness ≥ 0.25)
      t=0.80  paraphrases reused 11/40   variants wrongly reused 25/40
      t=0.74                     11/40                          32/40
      t=0.69 (the advised value) 12/40                          38/40

No cosine threshold separates a paraphrase from a one-detail variant, and the
lexical witness makes it worse: a variant shares most of its words with the
original, a real paraphrase often none. The baseline criterion ("every
paraphrase must clear the reuse threshold") was satisfiable only by lowering
to ≤0.736, buying one paraphrase for thirteen more confident wrong answers.
*Fix:* the criterion is replaced — the reuse threshold must be at or above the
retrieval threshold, is never required to admit every paraphrase, the command
measures ten hard-negative pairs and prints their admission on every run, and
its advice never proposes lowering (`app/cli.py`; `LEXICAL_WITNESS` named in
`app/memory/retrieval.py`). `SOLUTION_REUSE_THRESHOLD` stays 0.80. *Tests:*
`tests/unit/test_infrastructure.py::TestCalibrateReuseGate` (5).
*Residual, measured:* for a variant that does clear the gate, the guard is the
real model's context discipline — handed the stored answer, it declined 14/20
and carried a wrong detail over in 1–2/20 (`audit/measure_reuse_discipline.py`).
Showing the model the original question alongside the stored answer made it
answer from its own knowledge more often (10/20 guarded), so the current
answer-only context stays. Documented in `docs/LIMITATIONS.md`.

**Finding 3 — the semantic retrieval threshold made document QA impossible
(HIGH, function; threshold change by evidence).** With the real embedder, the
handbook chunk that answers a question scores 0.47–0.69 against it (median
0.59; a short question against a long multi-fact passage), a short memory item
0.66–0.69, unrelated text at most 0.44 question-to-question and 0.57 (p90 0.49)
against an unrelated long chunk. At 0.72: 0/10 handbook chunks ever retrieved,
memory items 4/6. *Change:* `MEMORY_SIMILARITY_THRESHOLD` 0.55 (semantic pair
only; the lexical pair is untouched): 8/10 chunks, 40/40 paraphrases, 2/56
unrelated chunks admitted — and an admitted wrong chunk is evidence the model
declines (a veto, then escalation), never an answer served. Followed the
prescribed order: evidence → explanation → proposal → change in AI Helper only →
regression test (`tests/memory/test_memory.py::TestSemanticThresholdMatchesTheMeasuredScale`)
→ calibrate re-run (exit 0) → evaluation re-run (document QA 0→4 correct,
memory 4/6→6/6) → full regression. `nomic-embed-text`'s `search_query:` /
`search_document:` prefixes would lift asymmetric scores by ~0.05–0.10 and are
the documented next step, not done here (configurable, model-specific, reindex).

**Finding 4 — the request session committed AFTER the response had been sent
(HIGH, cost/audit integrity).** FastAPI 0.141 (pinned `>=0.115`) runs a
`yield` dependency's exit code after the response; `db_dep` committed there.
Measured directly: a response returned in 0.09 s while the dependency's exit
ran 1 s later. Consequences: a read immediately after a write could miss it
(the privacy audit suite failed once on the final code, then passed 2/2 — a
race, present at 6f4c10f too, where it passed by timing), and a commit failing
after the response could not change the status code — a billed paid call would
have answered 200 with its CostRecord and audit rows rolled back, the F3
class. *Fix:* `app/api/transaction.py` (`CommitBeforeResponse`, outermost
middleware) commits on the first byte of a 2xx/3xx, answers 500 with nothing
persisted if that commit fails, and rolls back on 4xx/5xx; `db_dep` exposes its
session on the request state and its own commit becomes a no-op. *Tests:*
`tests/unit/test_transaction.py` (ordering, failed commit → 500 and the
original body never sent, error status → rollback, pass-through) and
`tests/security/test_audit_findings.py::TestCommitFailureCannotAnswerSuccess`
(through the real app). The privacy suite then passed 3/3 consecutive runs.

**Finding A (operator decision) — a client with any document turns every
open-ended question into `document_qa`.** `task_classifier.classify` returns
DOCUMENT_QA for a client with documents and a message over four words. With
the real model, all ten general-knowledge questions ("What is the capital of
Poland?") were answered correctly but scored 0.505 (grounding-required with
nothing retrieved), returned `success: false`, and wanted escalation
(NO_KNOWLEDGE_FOUND). With paid providers disabled that costs nothing; with one
enabled, every general question from a document-holding client pays. Proposal:
when the DOCUMENT_QA classification came from that weak heuristic (its own
confidence 0.5) and retrieval found nothing, validate the answer as GENERAL
instead of escalating. Not changed here — it is routing policy and spend, the
owner's call.

**Finding B (operator decision) — a paid answer to a context task with no
retrieved context is never learned.** Escalation reason NO_KNOWLEDGE_FOUND
means "context task, nothing retrieved"; the paid answer is then validated
with the same grounding-required rule and scores 0.505, so it is returned to
the caller but never captured, and the promotion pipeline would reject it
again at 0.70. The system pays for that question every time it is asked. In
the baseline evaluation 47 of 48 escalation wishes were NO_KNOWLEDGE_FOUND
(because of finding A). Proposal: validate a paid answer for capture without
the "no context" penalty when the escalation reason was NO_KNOWLEDGE_FOUND
(the paid model was consulted precisely because there was no context), keeping
the reproduction gate. Not changed here — it changes what is learned, the
owner's call; see the learning section for the measurement.

**Notes, not defects.** Confidence is nearly two-valued with a real model on
questions without context — 0.74 for any fluent answer, 0.505 for a context
task with nothing retrieved — so `CONFIDENCE_THRESHOLD` 0.62 acts as "fluent
general answers pass, ungrounded context answers do not"; no value between
those separates a right fluent answer from a wrong one, and 0.62 stays.
`LOCAL_TIMEOUT_SECONDS=60` timed out once on CPU (code generation, 1024 max
tokens at ~12 tok/s) in the baseline run; 180 is the right value for a CPU-only
host (config, `docs/deployment.md` already says 180 for the proxy). A document
QA citation such as "(score 0.63#1)" carries numbers the context does not, and
the number check vetoed a correct answer once (q06) — a false negative in the
safe direction; worth excluding rendered reference ids from that check later.

## 7. Unchanged by explicit decision (Step 6)

    CONFIDENCE_THRESHOLD              0.62     no evidence a different value separates
    the five confidence weights                right from wrong fluent answers
    SOLUTION_REUSE_THRESHOLD          0.80     lowering measured harmful (finding 2)
    SOLUTION_TTL_DAYS                 180      not exercised by this gate
    dispatcher false-negative policy           10/10 tool-shaped hits, 0 false positives

    MEMORY_SIMILARITY_THRESHOLD  0.72 → 0.55   changed, by the evidence and
                                               process in finding 3

## 8. Regression after real-model testing (Step 9)

    Test suite (final commit)   470 passed, 0 failed, 0 skipped — three consecutive
                                runs (445 at baseline + 25 regression tests)
    Coverage                    89% of app/
    Ruff                        clean across app/, tests/, audit/
    Network-free audit suites   demo_e2e 27/27 · prove_cost 25/25 ·
                                prove_privacy_and_permissions 54/54 ×3 ·
                                prove_security 51/51 · prove_learning 29/29 ·
                                prove_persistence 35/35
    Docker clean build          --no-cache with the pip_ca CA secret: PASS
    Container persistence       prove_container_persistence 33/33 on the final
                                image, twice (compose down/up; PostgreSQL rows and
                                Qdrant vectors identical before/after; the
                                learned answer still reused locally and free)

## 9. Final production decision (Step 10)

    Real Ollama model              PASS   llama3.2:3b + nomic-embed-text, digests verified
    End-to-end real inference      PASS   3 × 76 requests + smoke test, all ollama/llama3.2:3b
    Calibration                    PASS   exit 0 inside the container, criterion corrected by evidence
    50–100 evaluation              ACCEPTED   76 cases × 3 runs; 1–2/76 confidently wrong (documented limit)
    Learning / reuse               PASS   33/33 with the real model; paid = 0 on the reworded question
    Privacy                        PASS   RESTRICTED / CONFIDENTIAL / categorical never left; audited
    Security                       PASS   51/51 + regression
    Cost controls                  PASS   25/25 + the commit-before-response fix
    Docker                         PASS   clean build
    Persistence                    PASS   33/33 container gate, 35/35 suite
    Full regression                PASS   470/470 × 3, 89%, ruff clean

    PRODUCTION STATUS: APPROVED FOR DEPLOYMENT of the tagged commit, with the
    two operator decisions (findings A and B) taken BEFORE any paid provider is
    enabled. Deployment was not performed from here (no access to the
    production host; see §10).

    Final version         : 1.0.0
    Final Git commit      : the commit tagged v1.0.0 (report and results included)
    Model                 : llama3.2:3b (Llama 3.2 3B Instruct, Q4_K_M) — production pulls
                            the same weights from registry.ollama.ai
    Model version         : Ollama 0.33.3; GGUF v3; nomic-embed-text-v1.5 F16
    Calibration result    : exit 0, verdict ok (memory 0.55, reuse 0.80)
    Evaluation result     : 35 correct / 2 wrong-validated / 8 guarded / 31 unverified of 76 (final image)
    Test count            : 470
    Docker result         : clean build PASS
    Persistence result    : 33/33
    Production approval   : APPROVED (deployment pending, by the operator, per §10)

## 10. Deployment runbook (Step 12) — to be executed on the production host

Not executed here. Every command below is scoped to the AI Helper compose
project; none touches another project, database, network or volume.

    # 0. isolation: only this project's resources are ever named
    cd /opt/ai-helper && git fetch --tags && git checkout v1.0.0
    docker compose -p ai-helper ps            # this project only; nothing else is listed or touched

    # 1. backup (existing deployment) — ./scripts/backup.sh, then confirm the archive restores
    #    into a scratch database; that restore IS the rollback rehearsal
    # 2. rollback: `git checkout <previous tag>` + `docker compose -p ai-helper up -d --build`,
    #    then restore the backup; no schema migration ships in v1.0.0, so no downgrade step
    # 3. .env: ENVIRONMENT=production, LOG_FORMAT=json, AUTH_SECRET (32+ chars), ADMIN_PASSWORD_HASH,
    #    MEMORY_SIMILARITY_THRESHOLD=0.55, LOCAL_TIMEOUT_SECONDS=180 on a CPU-only host,
    #    ANTHROPIC_ENABLED=false and OPENAI_ENABLED=false until findings A and B are decided
    docker compose -p ai-helper up -d --build          # only AI Helper's services
    docker compose -p ai-helper exec ollama ollama pull llama3.2:3b
    docker compose -p ai-helper exec ollama ollama pull nomic-embed-text
    docker compose -p ai-helper exec ai-helper python -m app.cli calibrate   # must exit 0
    ./scripts/health_check.sh                          # every component OK; embedder OK, not DEGRADED
    docker compose -p ai-helper exec -T postgres pg_isready -U aihelper -d aihelper
    curl -s http://127.0.0.1:6333/collections           # Qdrant (if published) or via /health
    # harmless smoke test with a fresh key:
    docker compose -p ai-helper exec ai-helper python -m app.cli create-client smoke
    curl -s -H "Authorization: Bearer <key>" -H "Content-Type: application/json" \
         http://127.0.0.1:8000/api/v1/chat -d '{"message":"What is the capital of Poland?"}'
    #    expect route local, provider ollama, cost 0
    # audit logging: GET /api/v1/admin/audit shows the smoke request; privacy gate: /health shows
    # anthropic/openai DISABLED; monitor `docker compose -p ai-helper logs -f ai-helper` for the first requests

    NEVER on the shared host: docker system prune · docker volume prune · docker network prune

## 11. Evidence

`audit/results/real_model_gate_2026-09-09/` — evaluation rows (baseline and
final, JSON and Markdown), learning/reuse/privacy record, calibrate outputs
(baseline and final), the 120-pair embedder measurement, the 20-case context
discipline measurement, container-persistence output, raw Ollama chat,
model-load log lines, OCI manifests/configs with digests, health and smoke
outputs, test-run summaries. No key, password or secret appears in them.
