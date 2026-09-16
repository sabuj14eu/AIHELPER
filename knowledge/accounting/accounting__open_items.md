---
title: Accounting application open items
domain: accounting
repo: sabuj14eu/Accounting-
sources: docs/OPEN_ITEMS.md, docs/ROADMAP.md, docs/FABLE_BRIEFING_2026-09-08.md, docs/DEFINITION_OF_DONE.md, docs/RELEASE_CHECKLIST.md, docs/RELEASE_RECORD_2026-09-07.md, docs/PRODUCTION_AUDIT_2026-09-07.md, docs/SIGNALMESH_NAV_LINK.md, shop-intelligence/docs/ISOLATION.md, shop-intelligence/docs/REGRESSION_MAP.md
verified_on: 2026-09-16
classification: INTERNAL
---

# Accounting application open items (deferred work, as docs/OPEN_ITEMS.md and ROADMAP carry it)

## The rule of this file

`docs/OPEN_ITEMS.md` carries the deferred work of the accounting application. "An item deferred in conversation is an item forgotten — if it is not here, it does not exist. Delete an entry only when it is done and verified, and say where the proof is." The list below mirrors that file as of the last commit (2026-09-07), with status.

## P0 — must be settled before real accounting use (status: OPEN)

**The rate tables have not been verified against official sources.** Every version in `modules/poland/config/rates/` is `secondary` — taken from competent Polish accounting publications and cross-checked arithmetically against its own formula, which catches transcription errors but not a wrong source. Verification from the build environment was impossible: zus.pl, gov.pl, isap.sejm.gov.pl, stat.gov.pl and api.nbp.pl were refused by the network egress policy (403 on CONNECT). The software refuses to hide this: every report names the unverified tables as a filing blocker; `POLAND_REQUIRE_OFFICIAL_RATES=true` makes the engine throw; preparation refuses to build a document. Worklist: `php artisan poland:rate-provenance --todo`; procedure in `docs/RATE_VERIFICATION.md`. **Most critical single item:** whether the 2026 health-contribution reform (9% of 75% of the minimum wage) really did not take effect — secondary sources say it was vetoed; if wrong, every 2026 health figure is wrong. Owner: the taxpayer's accountant. Proof required: `status => 'official'` with a source URL on every version, plus the OPEN_ITEMS note deleted. Status: OPEN, BLOCKED on a human with network access.

**Which ryczałt rate applies has not been determined.** `examples/profile.json` ships 3% (trade in goods) as an example, not advice. The rate depends on the actual activity under art. 12; a shop selling goods and providing services may fall under two rates at once, and choosing wrong changes tax by multiples. The engine supports several rates per taxpayer; the profile carries one. Status: OPEN, blocked on the taxpayer confirming PKD activity and rate(s).

**No cost register, so only ryczałt is exact.** For skala and liniowy the engine can only bound PIT from above; this is reported, not hidden, but those regimes are not usable for a real filing from cash-register data alone. Phase 2 (KPiR) closes it. Status: OPEN.

## P1 — needed for a complete Phase 1 (status: OPEN)

- **Polish chart of accounts and company defaults not configured.** Liberu ships its own chart; Polish numbering, VAT registers and document types are configuration work, not a runtime unknown.
- **KSeF HTTP transport is not implemented.** `ksef.mf.gov.pl` and `ksef-test.mf.gov.pl` were refused by network policy; writing a client from remembered documentation was refused. Everything around it is built and executed (FA parser, dedup, cursor, immutable XML, encrypted InvoiceRead-only tokens, REQUIRES REVIEW propagation). `UnconfiguredKsefClient` refuses until a transport exists. Next step: implement `KsefClient` against the current official API, verified at source, tested against the KSeF test environment (12-step checklist in `docs/PRODUCTION_AUDIT_2026-09-07.md` §1).
- **No OCR or PDF text extraction.** No tesseract or pdftotext; `UnavailableTextExtractor` refuses; `PdfStatementParser` refuses with a route forward (CSV/MT940/camt). Next step: install a toolchain on the server and implement the `TextExtractor` port.
- **No KSeF or JPK schema version is registered.** `SchemaRegistry` selects by period and refuses unregistered ones; no XSD registered, so no document can be prepared. Phase 3/4.
- **Filing is not implemented for any channel.** `UnconfiguredSubmitter` throws for every channel; the taxpayer files themselves and records the reference through `markFiled()`. Deliberate.
- **No exchange-rate adapter.** `UnavailableExchangeRateProvider` refuses; NBP adapter is Phase 2.
- **Backup and restore have not been drilled on a real database** — as written in OPEN_ITEMS. Note: the later `docs/RELEASE_RECORD_2026-09-07.md` §10 records the drill performed for real on MariaDB (27 checks passed) in the gate environment; OPEN_ITEMS still says to run `bin/data-safety-drill.sh` on the Contabo box before going live and that it must exit 0. Status: partially addressed; on-box drill UNKNOWN.
- **Multi-rate ryczałt is supported by the engine but not by data entry.** Per-line rates and proportional apportionment are tested; dashboard and CLI accept one rate.
- **Quarterly VAT (JPK_V7K) is modelled but not settled quarterly.** Profile carries the frequency; settlement is monthly throughout.

## P2 — known limitations, acceptable for now (status: ACCEPTED)

- Suspension and sickness do not shorten a month; only an incomplete FIRST month prorates, and the report states the full-month assumption.
- Mały ZUS Plus base is supplied, not derived (previous-year income and the 36-in-60-months limit are configured and validated, not computed).
- The public holiday calendar ends in 2027 (`config/rates/deadlines.php` has 2025–2027); beyond that the report returns the statutory date and says the shift could not be applied. Add years before then.
- Annual reconciliation of the health contribution is warned about, not computed (belongs with PIT-28, not built).

## Recorded for the CI argument (status: DONE)

Three bugs found by executing the Laravel layer and fixed: `RateProvenance` positional argument order (named args + `test_provenance_fields_are_read_in_the_right_order`); sales correction inserting before superseding (order now load-bearing and commented); dashboard `$errors` binding (guarded). None visible to `php -l` or the engine suite — the argument for the `laravel-integration` CI job.

## Shop Profit Intelligence — not built yet (status: OPEN)

Analysis core built and tested (60 tests, 469 assertions). Not built: (1) user interface — three pages exist only as `shop-intelligence/docs/BANKING_UX.md` and a text renderer; (2) database and migrations — nothing persists; (3) authentication, users, sessions — `.env.example` describes them; (4) importers — bank statement, card terminal, Glovo, Uber Eats, supplier invoices, OCR; (5) month close and immutable snapshot; (6) deployment — no database, vhost, systemd unit or backup; (7) **the 27 regression tests were derived from the specification body, not transcribed from its §29 list** — someone must read §29 line by line against `shop-intelligence/docs/REGRESSION_MAP.md` and report what is missing. Every threshold is invented (target margin, stock tolerance, alert levels, payout tolerance, three-period baseline minimum). Owner: whoever picks up the briefing. Proof required: a deployed application with its own database and login, and the §29 reconciliation written down.

Work order from `docs/FABLE_BRIEFING_2026-09-08.md` §6: P0 schema/migrations under `shop_intelligence` with its own user and grants plus database-level dedup (unique index on natural fingerprint, `possible_duplicate_of` column); own authentication and session cookie on its own domain; immutable month close with versioned snapshot; re-run the isolation guard after each. P1 the three pages to BANKING_UX. P2 the importers, each fail-closed (bank statement first — copy the accounting module's approach, not its code). P3 same-month-last-year baselines, thresholds from real history, recipe book from the actual kitchen.

Briefing §5 "where I am most likely to be wrong" (status: to be reviewed): all thresholds invented; `ReviewFlag` word list incomplete; `CASH_COUNTED` classified ACTUAL but uncorroborated; `Baseline` median may be wrong for a seasonal shop; demo figures invented; `ChannelResult::contribution()` is not profit.

## Deliberately not done (status: DEFERRED BY DECISION)

- **The SignalMesh navigation link (Phase 6).** Not applied; the instruction was to start with Phase 1 and the trading platform is not modified without a deliberate decision. Exact change in `docs/SIGNALMESH_NAV_LINK.md`.
- **Single sign-on with the trading platform.** Phase 1 has its own login by design; SSO would be a deliberate OAuth/OIDC integration between separate apps, never a shared session store.

## Roadmap phases (docs/ROADMAP.md)

- Phase 1 Foundation — BUILT (Liberu pinned; Polish locale/PLN/Warsaw; profile, cash-register sales, purchase register, ledger; VAT/ZUS/PIT with 2025/2026 tables; monthly report; dashboard, artisan, CLI; audit trail; own DB/queue/storage/login; isolation guard). Not yet in Phase 1: customer/supplier records, invoice issuing, chart of accounts configured for Polish defaults.
- Phase 2 Poland tax engine completion — NOT BUILT: NBP table A rates stored per transaction; Polish chart of accounts and VAT registers; KPiR / ewidencja przychodów as a proper book; multi-rate ryczałt from an invoice register.
- Phase 3 KSeF — NOT BUILT: FA(2)/FA(3) XML validated against the official XSD at runtime; auth per current API; submission, status polling, reference storage; DB-enforced idempotency; rejection handling and retries; incoming invoice download; retain original XML and validation results. Production credentials only after the suite passes against the KSeF test environment.
- Phase 4 JPK — NOT BUILT: JPK_V7M/V7K from VAT registers; JPK_FA and JPK_KR where needed; XSD validation before export; every export audited.
- Phase 5 Automation — the roadmap lists it as NOT BUILT (document inbox status flow, bank import, matching, dedup, recurring invoices, categorisation, reminders, accountant export). Note: `docs/AUTOMATION.md` and the CHANGELOG fourth entry record that bank import (CSV/MT940/camt.053), matching, government inbox and month close were subsequently built; the ROADMAP text was not updated.
- Phase 6 SignalMesh navigation — one link, deliberately not applied.

ROADMAP's own definition-of-done tally (its numbering differs from DEFINITION_OF_DONE.md): satisfied 1–4, 8, 9, 11, 13, 14, 16, 17; outstanding Polish invoicing (5), KSeF (6), VAT/JPK generation (7), NBP recording (10), tested restore on the real server (12), navigation link (15).

## Release-order priorities from the audit (docs/PRODUCTION_AUDIT_2026-09-07.md §25)

P0: official Polish rate verification · full regression suite · backup and restore test · security audit · monthly report verification · historical reproducibility verification. P1: real KSeF HTTP transport · real OCR · bank reconciliation hardening · government inbox. P2: KSeF incremental sync · automatic monthly close · notifications · more bank formats · accountant export. Later: KSeF submission · JPK · controlled government filing. "The next objective is not more AI. It is: connect the real official sources, verify them, and prove the end-to-end workflow with real documents."

## Human gates still open (docs/RELEASE_RECORD_2026-09-07.md)

- Gate 12 real-data pilot — REQUIRES HUMAN (one real bank statement, real invoices, real monthly sales, an accountant's records).
- Official rate verification — accountant with network access.
- Upstream Liberu index-name bug — to be reported upstream; patch re-applied on every upgrade until then.
- Audit §18 interpretation provenance — page number and model version noted as open.
