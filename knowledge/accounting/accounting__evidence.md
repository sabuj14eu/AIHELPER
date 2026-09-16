---
title: Accounting application evidence record
domain: accounting
repo: sabuj14eu/Accounting-
sources: docs/RELEASE_RECORD_2026-09-07.md, docs/PRODUCTION_AUDIT_2026-09-07.md, docs/RELEASE_CHECKLIST.md, docs/DEFINITION_OF_DONE.md, docs/SUPPORTED_VERSIONS.md, docs/RATE_VERIFICATION.md, docs/CHANGELOG.md, docs/FABLE_BRIEFING_2026-09-08.md, shop-intelligence/docs/ISOLATION.md, shop-intelligence/docs/REGRESSION_MAP.md, bin/release-gate.sh, README.md
verified_on: 2026-09-16
classification: INTERNAL
---

# Accounting application evidence: release records, audits, gates, rate verification

## Principle of this record

Every number in the accounting app's evidence documents came from a command that ran ("Measured, not estimated" — `docs/RELEASE_RECORD_2026-09-07.md`; "Everything here was executed, not read off a composer.json" — `docs/SUPPORTED_VERSIONS.md`). Nothing is marked done on the strength of code existing (`docs/DEFINITION_OF_DONE.md`). All evidence below is dated 2026-09-07 unless stated; all eight repository commits carry that date.

## Release record 2026-09-07 (docs/RELEASE_RECORD_2026-09-07.md) — the measured gate

Reproduce with `PHP_BIN=/path/to/php8.5 bin/release-gate.sh /srv/accounting/foundation`.

**§1 Complete test suite:** 309 tests, 874 assertions, 0 failures, 0 errors, 0 skipped, 0 incomplete/risky; identical on PHP 8.4.19 and 8.5.0; application PHP 8.5.0 (built from `php-src` tag `php-8.5.0`); Laravel 13.29.0; MariaDB 10.11.14-0ubuntu0.24.04.1; 295 migrations applied; commit `87ff25c559cb09eababf95bb4303d42149967ca7` plus one; branch `claude/poland-accounting-app-pijnfm`. `phpunit.xml` has `failOnWarning="true"` and `failOnRisky="true"`.

**§2 Production configuration fails closed:** measured on the running `.env` and the installer defaults — `POLAND_REQUIRE_OFFICIAL_RATES=true`, `KSEF_TRANSPORT_ENABLED=false`, `KSEF_TRANSPORT=disabled`, `FilingChannel::automated()` false for every channel (asserted by test). Changed for this gate: the installer previously wrote `POLAND_REQUIRE_OFFICIAL_RATES=false`; it now writes `true`. `TransportGate` throws when production is configured with `KSEF_TRANSPORT=fake`; there is no admin UI for it.

**§3 BLOCKED semantics — six tests:** unverified rates → BLOCKED / `OFFICIAL_RATES_NOT_VERIFIED` / Accountant; KSeF unavailable → BLOCKED / `KSEF_TRANSPORT_UNAVAILABLE` / Operator; missing bank statement → NOT ENOUGH DATA / `BANK_STATEMENT_MISSING` / Taxpayer; ambiguous duplicate → REQUIRES REVIEW / `POSSIBLE_DUPLICATE_TRANSACTION` / Taxpayer. A test asserts all four signatures differ; only the third is `isUserActionable()`.

**§4 Engine boundary — 46 tests:** one per `RESERVED_FOR_ENGINE` field plus the named list; a companion test asserts no field is on both the reserved and evidence lists; disagreement yields MANUAL REVIEW REQUIRED in both directions.

**§5 Report immutability — verified end to end on MariaDB:** August report v1 generated; new KSeF invoice imported; v1 unchanged (model refuses updates/deletes; checksum verified); `report.requires_review` audit event recorded; regeneration produced v2, both retained; month reports REQUIRES REVIEW with `NEW_DOCUMENTS_AFTER_REPORT`. `pl_report_versions` = 2 rows, both restored byte-identical.

**§6 Bank completeness — four distinct states:** 1–31 August with balances → COMPLETE; 1–15 August → PARTIAL; no period stated → UNKNOWN (`complete => null`); 1–30 June → OUTSIDE_PERIOD. Asserted: UNKNOWN ≠ COMPLETE, PARTIAL ≠ COMPLETE.

**§7 KSeF failure semantics:** the disconnected display reads "KSeF — NOT CONNECTED. Transport HTTP do KSeF nie jest włączony. System NIE pobiera faktur zakupowych. To nie znaczy, że faktur nie ma — znaczy, że ich nie widzimy." A test asserts "no invoices found" / "brak faktur" do not appear; the client throws rather than returning an empty page.

**§8 OCR failure semantics:** an unreadable document is UNKNOWN / MANUAL REVIEW, never INFORMATION ONLY; `textUnavailable = true`, `needsManualReview = true`, original filename retained; `UnavailableTextExtractor` throws.

**§9 Security sweep:** no credential literals committed; no token reaches a logger; `reveal()` call sites in `src/` = 0 (bound ≤ 2); `.env` gitignored; KSeF password never stored; token encrypted at rest (verified as ciphertext in the MariaDB column); token absent from `toArray()`/JSON/debug/`__toString` (11 regression tests); `InvoiceWrite` not obtainable by editing a database row.

**§10 Backup and restore — performed for real:** MariaDB dump restored into a scratch database; 27 checks, all passed; row counts identical across 17 tables (users and 16 `pl_` tables); original KSeF XML byte-identical (SHA-256 both sides); report versions identical with stored checksums; reconciliation decisions identical; settlement amounts identical; audit trail complete (11 events); no orphaned payment obligations. Design conflict found and fixed: the least-privilege accounting DB user could not create the scratch database; the installer now grants a dedicated `<db>_drill` namespace and the drill fails loudly if it is missing.

**§11 Historical reproducibility — 12 tests:** January 2026 settles on the 2025/2026 contribution year (461,66), February on 2026/2027 (498,35); a 2025 month uses the 2025 social base (5 203,80 → 1 773,96), never the 2026 one; settling the same historical month twice yields identical figures and rate sources; every settlement stores the version identifier of each table used.

**§12 Real-data pilot — REQUIRES HUMAN:** needs one real bank statement, real invoices, real monthly sales and an accountant's records. The gate script reports it as `REQUIRES HUMAN`.

**§13 Honest UI — 12 tests:** the dashboard panel renders KSeF NOT CONNECTED, Import wyciągów bankowych AVAILABLE, OCR / odczyt tekstu NOT AVAILABLE, Stawki podatkowe NOT VERIFIED, Wysyłka do organów DISABLED, each non-operational row with meaning and next step; asserted in the live HTML.

**The blocker this gate found:** the Liberu ERP could not migrate onto MySQL or MariaDB — Laravel-derived index/FK names exceeded the 64-character identifier limit (the record says 112 names; `bin/patch-foundation-index-names.sh` header says 92), `php artisan migrate` failed partway leaving a half-created schema, and the one-command installer provisions MariaDB, so the deploy command previously handed over would have failed. Found only because the gate insisted on a real database rather than SQLite. Fixed by `bin/patch-foundation-index-names.sh` (deterministic, lossless, idempotent, `--check` mode; installer runs it before migrating; upstream bug to report). After the fix: 295 of 295 migrations apply, all 16 `pl_` tables created.

**Milestones:** LIVE APPLICATION — REACHED. PRODUCTION ACCOUNTING — NOT REACHED (official rate verification and the real-data pilot). AUTOMATED FILING — NOT REACHED, deliberately disabled. Ships enabled: login, accounting data, documents, bank statement import (CSV, MT940, camt.053), monthly reports, payment checklist, audit trail, backup/restore. Ships disabled and stays disabled: KSeF submission, JPK submission, government submission, automatic payments, AI override of engine figures.

## Production audit 2026-09-07 (docs/PRODUCTION_AUDIT_2026-09-07.md)

Auditor's verdict: the design behaves like a serious accounting system; the strongest decisions are fail-closed behaviour, no fake KSeF, no fake OCR, no empty-result interpretation, database-level dedup, cursor advancing only after complete sync, immutable source documents, versioned reports, an AI that cannot write engine-owned figures, disagreement becoming MANUAL REVIEW, worst-case certainty, and automated filing disabled. Standing instruction: do not weaken these to make the feature list look bigger; every one is covered by a test.

Twenty-three sections were dispositioned. Confirmed kept (now pinned by tests): §1 KSeF architecture (13 named properties), §2 cursor validate → persist → commit → advance, §5 OCR fails closed, §6 fingerprint not loosened, §7 duplicates flagged never deleted, §9 AI boundary, §11 disagreement favours neither side, §12 worst-case certainty, §14 month close reports why certainty is not higher, §15 report immutability, §17 original PDF retained, §19 legally significant actions behind approval, §21 rate verification remains the production gate, §23 no capability claimed that is not live. Added: §3 `ParsedInvoice::MISSING` and `unknownElements`; §4 `CredentialSecurityTest` (one test per token-security property); §8 `ValueComparisonTest` (19 tests). §18 interpretation provenance is partly present (page number and model version noted as open).

**Four real gaps closed:** §13 BLOCKED and FAILED did not exist (added, ranked above NOT ENOUGH DATA; unverified rates and unavailable KSeF reclassified to BLOCKED; `CertaintyReport` separates user-actionable from operator items). §10 three engine-owned fields were unprotected — `vat_surplus`, `payment_deadline`, `due_date` — added along with `pit_liability`, `vat_payable`, `amount_due`, `tax_rate`, `filing_deadline`, `advance_due_date`, plus an explicit `EVIDENCE_FIELDS` list; `EngineBoundaryTest` now 46 tests. §16 statement completeness was unknown ("3 transactions imported" read as "all of August") — COMPLETE / PARTIAL / UNKNOWN / OUTSIDE_PERIOD added; a month without COMPLETE coverage raises BANK DATA INCOMPLETE. §20 nothing stopped production selecting a fake transport — `TransportGate` throws; `reportFailure()` wraps every transport error. §22 the UI did not label unavailable integrations — status panel added.

**Not claimed anywhere (per §23):** automatic KSeF download (no HTTP transport), automatic OCR (no extractor), automatic government filing, automatic tax payment, "fully autonomous accountant", "filing-ready".

**Audit test coverage table (289 tests, 790 assertions at audit time, green on PHP 8.2–8.5):** EngineBoundaryTest 46, CertaintyTest 20, ValueComparisonTest 19, RateTableTest 17, ZusCalculatorTest 17, ReconciliationTest 16, GovernmentInboxTest 15, FilingLifecycleTest 14, KasaFiskalnaReportTest 14, SyncSafetyTest 13, PitCalculatorTest 13, HistoricalReproducibilityTest 12, AccountantReportTest 12, IntegrationStatusTest 12, CredentialSecurityTest 11, VatCalculatorTest 10, FaInvoiceParserTest 7, MoneyTest 7, PeriodTest 7, TaxProfileTest 7. The later release gate added `ReleaseGateTest` (20 tests) bringing the suite to 309.

**Verified by execution on PHP 8.5.0 / Laravel 13.29.0 (296 migrations at audit time):** token ciphertext and redaction; InvoiceWrite refused even when the DB row is edited; unconfigured KSeF client refuses with the honest message; two invoices imported, correction flagged, second sync detected both as duplicates, XML immutable; new invoice after a report raised REQUIRES REVIEW with the report at v1; three statement formats imported, cross-format duplicate flagged and excluded; month close reported BLOCKED with four named caveats; `GET /poland` renders the integration panel.

## Release checklist (docs/RELEASE_CHECKLIST.md, state on 2026-09-07)

Ticked (executed): PHP 8.5 runtime; Liberu boots (Laravel 13.29.0, Filament v5.7.6, 674 packages); migrations (289 incl. seven `pl_` at that time); Laravel layer executed (3 commands, 9 routes, `GET /poland` 200, `GET /poland/raport/{m}` 200, POST flows 302); lint and `config:cache`/`route:cache`/`view:cache`; historical rate versions stored (2024/2025, 2025/2026, 2026/2027 health years; 2025 and 2026 social, PIT, VAT — all 24 months of 2025–2026 settleable); missing-rate refusal (2028 refused; no table open-ended); ZUS 17 tests; PIT 13; VAT 10; historical reproducibility 12; incomplete-data warnings; monthly report eight sections; payment checklist; PDF/print (`@page` A4); month close and versioning; duplicate-report prevention by unique indexes; isolation four checks; no automatic submission.

Not ticked at checklist time: official rates verified (BLOCKED — zus.pl, gov.pl, isap.sejm.gov.pl, stat.gov.pl, api.nbp.pl refused by the build environment's network policy, 403 on CONNECT); 2025 and 2026 rates verified (same blocker); backup tested and restore tested (no MariaDB in that environment — later performed for real in the release record §10). Verdict then: not production-ready for real tax payment; ready to deploy and use for orientation; every screen carries "NOT VERIFIED — DO NOT USE FOR REAL TAX PAYMENT".

## Definition of done (docs/DEFINITION_OF_DONE.md)

The heading says seventeen conditions; the table lists 18 (README says eighteen). DONE: 1 PHP 8.5, 2 Liberu boots, 3 migrations (288 at that time incl. 5 `pl_`), 4 Laravel layer executed, 5 tax engine tests (106/268 at that time), 7 historical rate versions stored, 8 missing-rate refusal (`test_it_refuses_to_extrapolate_into_an_unconfigured_year`, `test_a_month_with_no_rate_version_is_refused`), 9 ZUS edge cases (17 tests), 10 VAT limitations displayed, 11 skala/liniowy limitation displayed (`test_income_regimes_flag_a_missing_cost_register_as_an_upper_bound`), 13–16 isolation, 17 Accounts runs without SignalMesh, 18 SignalMesh runs without Accounts. PARTIAL: 12 KSeF/JPK/PIT/ZUS architecture versioned (mechanism built; no KSeF/JPK schema registered). BLOCKED: 6 official Polish rate sources verified. "Not production-ready until condition 6 is closed, and then re-verify 5, 9, 10 and 11 — verification may change figures, and the tests pin figures."

## Rate verification results (docs/RATE_VERIFICATION.md, config/rates)

Every rate version is `status => 'secondary'` (`checked_on: 2026-09-07`, `checked_by: claude-code — kontrola arytmetyczna`). What was verified: each figure cross-checked arithmetically against its own stated formula — full ZUS base = 60% of the stated forecast wage; each ryczałt health band = 9% of its stated percentage of the reference wage; published headline totals 1 926,76 / 1 773,96 / 456,18 / 442,90 / 420,86 zł reproduce exactly (`test_published_social_bases_match_their_stated_derivation`, `test_published_lump_sum_amounts_match_their_stated_formula`, `test_full_social_contributions_2025_match_the_published_total`, `test_full_social_contributions_2026_match_the_published_total`, `test_preferential_contributions_2026_match_the_published_total`, `test_minimum_health_contribution_matches_nine_percent_of_the_minimum_wage`). What was NOT verified: nobody has read the issuing authority's own publication. Three mechanisms keep this visible: every report warns and lists it as a blocker; production refuses (`UnverifiedRateException`); preparation refuses. `test_the_shipped_tables_are_honest_about_not_being_officially_verified` is designed to fail once every version is official — the signal to delete it and update OPEN_ITEMS. The CI job `laravel-integration` likewise fails if `poland:rate-provenance --todo` exits 0.

Items to confirm, from the RATE_VERIFICATION table: `zus_social` 2025.1/2026.1 bases and minimum wage; `zus_health` 2025-02.1/2026-02.1 GUS Q4 wage, that the 2026 reform really did not take effect, the flat-tax deduction cap; `pit` that scale parameters were unchanged for 2026; `vat` the 240 000 zł limit, its Dz.U. position and transitional rules; `deadlines` the ZUS day for this taxpayer (20th without employees, 15th with).

## Bugs found by execution (docs/CHANGELOG.md, docs/OPEN_ITEMS.md)

From the P0 validation (commit c6f79ea): `RateProvenance` constructor parameter order vs positional `fromArray()` (fixed with named arguments; `test_provenance_fields_are_read_in_the_right_order`); a sales correction inserted the new report before superseding the old one, violating the unique index; the dashboard view assumed `$errors` is bound (only true in the `web` middleware group); `bin/install-foundation.sh` used `--no-scripts` so `package:discover` never ran. From the automation phase (da390fc): the same transaction from two formats did not dedup (optional fields differ); the duplicate query compared a decimal column as a string and a date column against a date-only value, so it silently never matched. None of these were visible to `php -l` or the engine's own suite — the stated argument for the `laravel-integration` CI job.

## Supported versions (docs/SUPPORTED_VERSIONS.md)

Executed on 2026-09-07: PHP 8.5.0; Laravel 13.29.0; Filament v5.7.6; Livewire v4.4.3; Liberu `3a23437a432c74637aca56bb0daed27430d481ee`; 674 packages; 288 migrations (at that time); Poland module PHP ≥ 8.2, suite green on 8.2–8.5. The ERP fails to parse on PHP 8.4 with `PHP Fatal error: Attribute "Override" cannot target property (allowed targets: method) in app/Providers/AuthServiceProvider.php on line 18`. `POST /poland/sprzedaz` parses `31 250,50` correctly.

## Shop Intelligence evidence

Measured 2026-09-07 on PHP 8.4.19: 60 tests, 469 assertions, 0 failures, 0 errors, 0 skipped, `failOnWarning` and `failOnRisky` on (`docs/FABLE_BRIEFING_2026-09-08.md`, `docs/CHANGELOG.md`). Isolation: `bin/check-shop-isolation.sh` → "ISOLATION PROVEN — 10 checks, 0 violations" (`shop-intelligence/docs/ISOLATION.md`). 27 numbered regression tests R01–R27 mapped in `shop-intelligence/docs/REGRESSION_MAP.md`, plus `IsolationTest` (six checks over every source file) and unnumbered tests (comparison never corrects; notes not ranked as losses; monitor silent without enough history; cash ledger running balance). Caveat recorded in the map: the 27 were derived from the specification body, not transcribed from its §29 list; §29 reconciliation is the first task in the briefing. Not built: UI, database, auth, importers, month-close storage, deployment.

## Where the counts changed over the day (for reading old documents)

Test counts per phase (`docs/CHANGELOG.md`): Phase 1 — 85 tests; P0 validation — 106 tests / 268 assertions; pre-live — 130 / 346; automation — 182 / 543; audit response — 289 / 790; release gate — 309 / 874. Migrations applied: 288 → 289 → 295/296 as `pl_` migrations grew from 5 to 12. `docs/POLAND_TAX_ENGINE.md` still says 85 tests / 189 assertions and is stale on that point.
