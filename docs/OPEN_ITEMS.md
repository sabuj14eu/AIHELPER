# Open items — AI Helper / Brother

An item deferred in conversation is an item forgotten. If it is not here, it
does not exist. Delete an entry only when it is done and verified, and say
where the proof is. Status vocabulary: OPEN · IN PROGRESS · BLOCKED · DONE
(with proof).

## P1 — affects what the owner sees today

- **AIH-1 Trading connector not configured on the box.** `TRADING_PLATFORM_URL`
  and `TRADING_PLATFORM_API_KEY` are empty in the box's `.env`, so "bot
  status" answers "not configured". Needs a USER key from the platform's
  `/api-access` page, then `docker compose restart ai-helper`. Owner action.
  Opened 2026-09-16. OPEN.
- **AIH-2 The plan answer under qwen2.5:7b has not been observed.** The
  recipe document and the plan law were added after the last observed
  answer (a refusal from llama3.2:3b). qwen2.5:7b was pulled 2026-09-16
  19:35 UTC and the Brother agents prefer it automatically. Nobody has yet
  seen an answer from it. Ask the gold plan question and read the result;
  if it still refuses, teach the correct plan through the chat form and
  re-ask. Opened 2026-09-16. OPEN.
- **AIH-3 48 seeded solutions were REJECTED by llama3.2:3b's reproduction
  gate** (229 promoted, 1 validated, 48 rejected on 2026-09-16 ~17:30 UTC).
  Their facts are still in the documents. Under qwen2.5:7b many would pass.
  Re-seeding skips known fingerprints, so a re-run cannot retry them; a
  `--retry-rejected` option (delete the REJECTED knowledge-pack rows, then
  re-seed) is the smallest change. Opened 2026-09-16. OPEN.

## P2 — quality and robustness

- **AIH-4 Retrieval quality for pack questions is unmeasured.** The semantic
  embedder is live (`nomic-embed-text`), `calibrate` has not been run on the
  box since the pack loaded. Run `python -m app.cli calibrate`; expect exit 0.
  Then a fixed question set (10–20 questions about the six repos with
  expected sources) run through `python -m app.cli ask` is the evals harness
  the 1.0 handover named as the biggest gap. OPEN.
- **AIH-5 The trading mirror's `stats` keys are assumed.** `trading_status`
  renders `win_rate`, `profit_factor` etc. only if present; the platform's
  `core_stats` field names were not read. Verify against
  `Sniper-System/app/services/analytics.py` once AIH-1 is done. OPEN.
- **AIH-6 Outlook board is not readable.** The plan recipe says "restate
  the posted outlook" but no connector reads the platform's outlook board
  (its API v1 has no outlook endpoint; the desk page is session-authed).
  Either the platform adds `GET /api/v1/outlooks` (read-only, Iron Rule 1
  compatible) or Brother keeps saying ABSENT. Platform-side change; raise
  it there. OPEN.
- **AIH-7 Digests were written 2026-09-16 and have no refresh procedure
  beyond hand editing.** `sources/` re-syncs mechanically; the eight digests
  per repo do not. When a repo's laws change, a session must edit the
  digest and bump `verified_on`. Consider a `knowledge-status --stale-digests`
  that compares each digest's `verified_on` to the source repo's HEAD date. OPEN.
- **AIH-8 Open WebUI on port 3000 (chat.signalmesh.dev) bypasses Brother.**
  It talks to Ollama directly: no pack, no laws, no live data, and it
  showed "Arena Model: Cannot choose from an empty sequence" before models
  were pulled. Either point people to `/admin/chat` only, or remove the
  service from compose for this deployment. Owner decision. OPEN.

## P3 — deferred by design

- **AIH-9 Streaming answers.** Would need validation on a partial answer;
  the queued-job chat makes the wait tolerable. Deferred (1.0 backlog). OPEN.
- **AIH-10 Rate limiter and job queue are per process.** One worker only.
  Deferred (1.0 LIMITATIONS). OPEN.
- **AIH-11 Production gate from the 1.0 audit.** `HANDOVER_TO_FABLE.md` §3:
  the real-model calibration and the 50–100 real-question run were never
  done. The box now has real models, so this is runnable. Same as AIH-4. OPEN.

## Done this session (proof)

- Login redirect for browsers → `tests/integration/test_api.py::TestBrotherChat::test_the_page_needs_a_session`, commit 7e989e7.
- Pack shipped in the image → `tests/unit/test_container_build.py::TestKnowledgePackShipsInTheImage`, commit 04df5f0.
- Resumable seeding → `TestSeeding::test_seeding_is_resumable_in_batches_with_progress`, commit 7235386.
- Chat independent of proxy timeout → `TestBrotherChat.ask_and_wait`, commit 9a5d2fe; observed live 2026-09-16 (an answer arrived through nginx after the change).
- Small talk and the loose marker → commit 51b5a32.
- Teaching through the gate → `tests/unit/test_teaching.py`, commit 952255d.
