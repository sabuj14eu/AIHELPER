---
title: Accounting application validated solutions
domain: accounting
repo: sabuj14eu/Accounting-
sources: CLAUDE.md, docs/CHANGELOG.md, docs/RELEASE_RECORD_2026-09-07.md, docs/PRODUCTION_AUDIT_2026-09-07.md, docs/OPEN_ITEMS.md, docs/POLAND_TAX_ENGINE.md, docs/AUTOMATION.md, docs/DEPLOYMENT.md, docs/SUPPORTED_VERSIONS.md, docs/ARCHITECTURE.md, docs/RATE_VERIFICATION.md, docs/FABLE_BRIEFING_2026-09-08.md, bin/patch-foundation-index-names.sh, bin/data-safety-drill.sh, bin/install-foundation.sh, modules/poland/config/rates/zus_health.php, modules/poland/src/Domain/Money.php, modules/poland/src/Domain/TaxProfile.php, modules/poland/src/Support/DeadlineCalendar.php, modules/poland/src/Reporting/SettlementEngine.php, modules/poland/src/Certainty/DataCertainty.php, modules/poland/src/Interpretation/InterpretationBoundary.php, modules/poland/src/Ksef/TransportGate.php, modules/poland/tests, shop-intelligence/src/Truth/Total.php, shop-intelligence/src/Truth/ReviewFlag.php, shop-intelligence/docs/REGRESSION_MAP.md
verified_on: 2026-09-16
classification: INTERNAL
---

# Accounting application validated solutions

Each entry is a problem that was actually solved in the accounting app or Shop Intelligence, with the proof location. Dates are 2026-09-07 unless stated (all commits carry that date).

### Liberu ERP could not migrate on MySQL/MariaDB (index names too long)
question: Why did php artisan migrate fail partway on MariaDB for the accounting app, and how was it fixed?
answer: Laravel derives index and foreign-key names from the table plus every column, and MySQL/MariaDB cap identifiers at 64 characters; at the pinned Liberu commit many derived names exceeded it (the release record says 112, the patch script header says 92), so migrate failed midway and left a half-created schema. Development had used SQLite, so it only surfaced when the release gate insisted on the real database the installer provisions. The fix is `bin/patch-foundation-index-names.sh` (delegating to `bin/support/fix-index-names.php`), which gives each affected index a deterministic short name — lossless, idempotent, with a `--check` mode wired into CI; `bin/install-foundation.sh` runs it before migrating. It is an upstream bug and must be re-applied after every foundation upgrade. After the fix 295 of 295 migrations apply and all 16 pl_ tables exist.
evidence: docs/RELEASE_RECORD_2026-09-07.md "The blocker this gate found"; docs/CHANGELOG.md sixth entry; bin/patch-foundation-index-names.sh; commit df76342

### Installer defaulted POLAND_REQUIRE_OFFICIAL_RATES to false
question: Why does the installer now write POLAND_REQUIRE_OFFICIAL_RATES=true even though it makes the app refuse to settle?
answer: The installer previously wrote `false` so the app would be immediately usable, which was the wrong default: the safe value must be the default and relaxing it a conscious act. With `true`, `SettlementEngine` throws `UnverifiedRateException` on secondary rates; the installer prints how to relax it and what that costs. The release gate checks both the running `.env` and the installer's literal `set_env POLAND_REQUIRE_OFFICIAL_RATES true` line.
evidence: docs/RELEASE_RECORD_2026-09-07.md §2; bin/deploy-contabo.sh line "set_env POLAND_REQUIRE_OFFICIAL_RATES true"; bin/release-gate.sh gate 2

### Restore drill could not create its scratch database
question: Why does the deploy script grant the accounting DB user an extra `<db>_drill` database?
answer: The accounting DB user is deliberately scoped to its own schema, which prevented `bin/data-safety-drill.sh` from creating the scratch database it restores into. Rather than widening access, the installer grants a dedicated `${DB_NAME}_drill` namespace, keeping least privilege while letting the restore actually be proven; the drill now fails loudly with the exact GRANT needed if the grant is missing, rather than being quietly skipped.
evidence: docs/RELEASE_RECORD_2026-09-07.md §10; bin/deploy-contabo.sh GRANT on `${DB_NAME}_drill`; bin/data-safety-drill.sh step 2

### RateProvenance constructor argument order bug
question: What was the RateProvenance fromArray bug and how was it prevented from recurring?
answer: `RateProvenance`'s constructor parameters were declared in a different order than `fromArray()` passed them positionally, so fields were silently swapped. Not visible to `php -l` nor to the engine's own suite; found only by executing the Laravel layer. The call now uses named arguments so it cannot recur, pinned by `test_provenance_fields_are_read_in_the_right_order`.
evidence: docs/CHANGELOG.md "P0 validation — Fixed"; docs/OPEN_ITEMS.md "Three bugs were found by executing the Laravel layer"; RateTableTest::test_provenance_fields_are_read_in_the_right_order

### Sales correction violated the duplicate-month unique index
question: Why must a cash-register correction supersede the old report before inserting the new one?
answer: A sales correction inserted the new report before superseding the old one, violating the unique index on `(profile, period, status)` that makes duplicate months impossible. The order was load-bearing: supersede first, then insert. It is now commented as such and covered by the executed integration flow ("a correction supersedes without overwriting").
evidence: docs/CHANGELOG.md "P0 validation — Fixed"; docs/SUPPORTED_VERSIONS.md executed list; docs/RELEASE_CHECKLIST.md "Duplicate monthly report prevention"

### Dashboard view assumed $errors was always bound
question: Why did the /poland dashboard view error outside the web middleware group?
answer: The Blade view assumed `$errors` is always bound, which is only true inside Laravel's `web` middleware group. It was guarded. Found by executing `GET /poland`, not by lint.
evidence: docs/CHANGELOG.md "P0 validation — Fixed"; commit c6f79ea

### install-foundation.sh never ran package:discover
question: Why did the Poland module install without registering its service provider?
answer: `bin/install-foundation.sh` used `composer install --no-scripts`, so `package:discover` never ran and the module was installed but not registered. The script now runs `php artisan package:discover` and verifies the provider registered before migrating; CI's `laravel-integration` job asserts `poland:report` and `poland:verify-rates` appear in `artisan list`.
evidence: docs/CHANGELOG.md "P0 validation — Fixed"; bin/install-foundation.sh "package:discover" step; .github/workflows/ci.yml

### Liberu ERP requires PHP 8.5, failing to parse on 8.4
question: Why does the accounting ERP fail on PHP 8.4 with an error about the Override attribute?
answer: Upstream Liberu uses `#[\Override]` on class properties, which is PHP 8.5 syntax; on 8.4 the application fails to parse before any autoloader runs, and the fatal error names an attribute rather than a version ("Attribute "Override" cannot target property ... AuthServiceProvider.php line 18"). `composer install --ignore-platform-reqs` succeeds on 8.4, so the failure is misleading. `bin/install-foundation.sh` checks `PHP_VERSION_ID >= 80500` up front and prints a clear message; the tax engine itself stays at PHP 8.2 so `pl-tax` still works while the host waits.
evidence: docs/DEPLOYMENT.md "Prerequisite that will bite you first"; docs/SUPPORTED_VERSIONS.md; bin/install-foundation.sh prerequisite check

### January 2025 could not be settled (missing 2024/2025 health year)
question: Why does zus_health.php contain a 2024-02.1 version when the social table only starts in 2025?
answer: The health contribution year runs February–January, so January 2025 belongs to the year that began February 2024. Without that version the engine correctly refused January 2025 — which is how the gap was found. Version `2024-02.1` (contribution year 2024/2025, effective 2024-02..2025-01) was added solely so January 2025 settles; 2024 months remain unsettleable because `zus_social` starts 2025-01. All 24 months of 2025–2026 are now settleable.
evidence: modules/poland/config/rates/zus_health.php version 2024-02.1 notes; docs/CHANGELOG.md pre-live "2024/2025 health contribution year"; docs/RELEASE_CHECKLIST.md "Historical rate versions stored"

### Cross-format bank duplicate (MT940 vs camt.053) would double costs
question: How does the accounting app handle the same bank transaction imported from two statement formats?
answer: The same payment arriving as MT940 and as camt.053 did not dedup because optional fields differ between formats (MT940 supplies a counterparty account that camt omits), so the fingerprints differed and the month's costs would double. Loosening the fingerprint would be worse (two genuine same-day payments of the same amount would collapse). So the second row is imported, flagged `possible_duplicate`, excluded from reconciliation, and a person decides; rows are never deleted. The file checksum still catches an outright re-upload.
evidence: docs/AUTOMATION.md "Two kinds of duplicate"; docs/CHANGELOG.md automation "Fixed"; migration 2026_09_07_001100; TransactionLifecycle; ReconciliationTest

### Duplicate query compared decimal as string and date against datetime
question: Why did the bank duplicate detection silently never match at first?
answer: The duplicate query compared a decimal column as a string and a date column against a date-only value, so it never matched and no error surfaced. Fixed, and `ValueComparisonTest` (19 tests) now pins decimal scale, date vs datetime, timezone and equivalence comparisons (amounts compared in grosze, not floats; "a late evening Warsaw time stays on its own day"; NIP and IBAN compare the same however punctuated).
evidence: docs/CHANGELOG.md automation "Fixed"; docs/PRODUCTION_AUDIT_2026-09-07.md §8; tests/Unit/ValueComparisonTest.php

### BLOCKED and FAILED certainty states were missing
question: Why were BLOCKED and FAILED added to DataCertainty and how do they differ from NOT ENOUGH DATA?
answer: The system had four certainty states; the audit named six. NOT ENOUGH DATA means the taxpayer can fix it by uploading something; BLOCKED means a dependency is unavailable or unverified (unverified rates, disabled transport) and no upload changes it; FAILED means something ran and broke, so there is an error and a retry. Collapsing them sends somebody hunting for a missing document when the real problem is a timeout. Both were added, ranked above NOT ENOUGH DATA in the worst-case ordering; unverified rates and unavailable KSeF were reclassified to BLOCKED; `CertaintyReport` separates user-actionable from operator items; `ResolvedBy` names taxpayer/operator/accountant.
evidence: docs/PRODUCTION_AUDIT_2026-09-07.md §13; DataCertainty.php; docs/RELEASE_RECORD_2026-09-07.md §3; CertaintyTest, ReleaseGateTest::test_gate_3_*

### Three engine-owned fields were not protected from AI interpretation
question: Which fields did the AI boundary miss and why did it matter?
answer: `RESERVED_FOR_ENGINE` lacked `vat_surplus` (a surplus is a claim on the tax office — reading one off a letter would create a refund entitlement out of an interpretation), `payment_deadline` and `due_date` (a misread digit would become the date somebody pays by). All three were added, plus `pit_liability`, `vat_payable`, `amount_due`, `tax_rate`, `filing_deadline`, `advance_due_date`, and an explicit `EVIDENCE_FIELDS` list; a test asserts no field is on both lists, and `EngineBoundaryTest` runs one test per reserved field (46).
evidence: docs/PRODUCTION_AUDIT_2026-09-07.md §10; modules/poland/src/Interpretation/InterpretationBoundary.php; tests/Unit/EngineBoundaryTest.php

### Bank statement completeness was unknown
question: Why does a bank statement now carry a completeness state?
answer: "3 transactions imported" was silently readable as "all of August", and a statement covering 1–15 August understates costs exactly as much as importing none. Statements now record `completeness` (COMPLETE / PARTIAL / UNKNOWN / OUTSIDE_PERIOD), the covered range, and whether the format supplied balances; UNKNOWN is never treated as complete (`complete => null`), and a month without COMPLETE coverage raises BANK DATA INCOMPLETE.
evidence: docs/PRODUCTION_AUDIT_2026-09-07.md §16; migration 2026_09_07_001200; docs/RELEASE_RECORD_2026-09-07.md §6; ReleaseGateTest::test_gate_6_*

### Production could have selected a fake KSeF transport
question: What stops production from quietly using a fake or empty KSeF client?
answer: Nothing did, and a silent fallback would turn "no connection" into "no invoices found", a factual claim about the taxpayer's month. `TransportGate` now throws when a production environment is configured with `KSEF_TRANSPORT=fake` (from env, config, deployment default or database value), and `TransportGate::reportFailure()` wraps every transport error so it can never read as an empty result. Defaults are `KSEF_TRANSPORT_ENABLED=false`, `KSEF_TRANSPORT=disabled`; there is no admin UI for it.
evidence: docs/PRODUCTION_AUDIT_2026-09-07.md §20; modules/poland/src/Ksef/TransportGate.php; IntegrationStatusTest::test_production_may_not_use_a_fake_transport_at_all

### The UI did not label unavailable integrations
question: How does the accounting dashboard show that KSeF and OCR are not working?
answer: The dashboard carries a status panel: KSeF NOT CONNECTED, Import wyciągów bankowych AVAILABLE, OCR / odczyt tekstu NOT AVAILABLE, Stawki podatkowe NOT VERIFIED, Wysyłka do organów DISABLED — each non-operational row with what it means and the next step, and the KSeF row saying in as many words that this does not mean there are no invoices. No disabled dependency is shown green. Asserted in the live HTML by 12 tests.
evidence: docs/PRODUCTION_AUDIT_2026-09-07.md §22; docs/RELEASE_RECORD_2026-09-07.md §13; tests/Unit/IntegrationStatusTest.php

### Missing invoice net amount rendered as 0,00
question: How does the FA invoice parser represent a missing field?
answer: A missing net amount must read `MISSING_FIELD`, not `0.00`. `ParsedInvoice::MISSING` and `display()` were added so nothing renders a fabricated zero, and `unknownElements` records XML elements the mapping does not cover instead of discarding them. The parser is namespace-agnostic (FA(1)/(2)/(3) and an unreleased schema version) and unparseable XML throws rather than returning an empty invoice.
evidence: docs/PRODUCTION_AUDIT_2026-09-07.md §3; FaInvoiceParserTest::test_missing_fields_are_reported_never_defaulted, test_unparseable_xml_throws_rather_than_returning_an_empty_invoice

### Empty OCR text would classify a demand for payment as INFORMATION ONLY
question: Why does the text extractor throw instead of returning empty text?
answer: With no OCR toolchain, empty extracted text would classify a government letter as INFORMATION ONLY, and a demand for payment would sit in the inbox until the deadline passed. `UnavailableTextExtractor` throws; an unreadable document is classified UNKNOWN / MANUAL REVIEW with `textUnavailable = true`, `needsManualReview = true`, and the original filename retained. A test documents the counterfactual.
evidence: docs/AUTOMATION.md "Everything that cannot be done, refuses"; docs/RELEASE_RECORD_2026-09-07.md §8; ReleaseGateTest::test_gate_8_empty_text_would_have_classified_as_information_only

### An empty KSeF result must never mean "no invoices"
question: What happens when KSeF is not configured or unreachable?
answer: `UnconfiguredKsefClient` refuses rather than returning an empty page, because an empty invoice list is indistinguishable from "you had no purchases this month" and that reading understates costs. The refusal text states that not seeing invoices does not mean there are none; a test asserts "no invoices found"/"brak faktur" never appear. No HTTP client was written because `ksef.mf.gov.pl` was unreachable from the build environment, and writing one from remembered documentation was explicitly refused.
evidence: docs/AUTOMATION.md; docs/RELEASE_RECORD_2026-09-07.md §7; ReleaseGateTest::test_gate_7_*; docs/OPEN_ITEMS.md "KSeF HTTP transport is not implemented"

### Health contribution year runs February to January
question: How does the engine get January's ZUS health contribution right?
answer: January belongs to the contribution year that began the previous February, so January 2026 is settled on 2025/2026 figures (461,66 / 769,43 / 1 384,97) and February switches to 2026/2027 (498,35 / 830,58 / 1 495,04). Instead of remembering this, `zus_health.php` versions are dated by month (`effective_from` 2025-02, `effective_to` 2026-01, etc.) so lookup by period returns the right year automatically.
evidence: modules/poland/config/rates/zus_health.php; ZusCalculatorTest::test_january_uses_the_previous_contribution_year_amounts; HistoricalReproducibilityTest::test_january_2026_uses_the_2025_2026_contribution_year, test_february_2026_switches_to_the_new_contribution_year

### Health contribution under scale/flat looks back one month
question: Which month's income drives the health contribution on skala and liniowy?
answer: The base is the income of the month BEFORE the settled one (9% scale, 4.9% flat). `SettlementEngine::replayYear` passes `previousMonthIncome()` explicitly; when the previous month is unknown the calculator returns the statutory minimum with a note rather than using the current month's income. A loss month still pays the minimum.
evidence: docs/POLAND_TAX_ENGINE.md traps; ZusCalculatorTest::test_scale_health_is_nine_percent_of_the_previous_months_income, test_flat_health_is_four_point_nine_percent_of_the_previous_months_income, test_unknown_previous_income_yields_the_minimum_and_says_so, test_a_loss_month_still_pays_the_minimum_health_contribution

### PIT advances must be replayed from January
question: Why does the engine replay the whole year to settle one month?
answer: The PIT advance is cumulative from 1 January, the ryczałt health band is chosen by revenue accumulated since 1 January, the health contribution looks back a month, and deductions depend on earlier contributions. `SettlementEngine::replayYear` walks January forward and hands each month what earlier months produced; settling a month in isolation would drift invisibly. A test asserts twelve monthly advances sum exactly to the year's cumulative tax; a gap earlier in the year produces the warning "Wynik jest niepełny, a nie zerowy".
evidence: docs/ARCHITECTURE.md "Why the engine replays the year"; SettlementEngine.php; PitCalculatorTest::test_pit_advances_accumulate_correctly_across_the_year; KasaFiskalnaReportTest::test_a_gap_earlier_in_the_year_is_reported_as_incomplete

### VAT payer's income-tax revenue is net, not gross
question: Should ryczałt be computed on gross or net cash-register takings for a VAT-registered taxpayer?
answer: Net. Taxing the gross overstates a ryczałt base by 23%. `FiscalSalesReport::revenueForIncomeTax($vatStatus)` returns net for Registered and gross for exempt taxpayers, and output VAT is extracted as gross × rate / (1 + rate).
evidence: docs/POLAND_TAX_ENGINE.md; VatCalculatorTest::test_output_vat_is_extracted_from_a_gross_cash_register_total; KasaFiskalnaReportTest::test_a_vat_registered_taxpayer_pays_pit_on_the_net_amount; HistoricalReproducibilityTest::test_a_vat_payer_is_taxed_on_net_revenue_in_every_year

### Fundusz Pracy follows the base, not the scheme
question: Why does the preferential ZUS scheme pay no Fundusz Pracy, and how is that encoded?
answer: FP is due only from a base at or above the minimum wage; the preferential base is 30% of the minimum wage, so it never qualifies. Encoded as the rule `labour_fund_requires_base_at_least_minimum_wage => true` in `zus_social.php` rather than as a per-scheme total, so a prorated full base in an incomplete first month is still tested for FP against the full-month base and still owes it.
evidence: modules/poland/config/rates/zus_social.php; ZusCalculatorTest::test_preferential_scheme_pays_no_labour_fund, test_a_prorated_full_base_still_owes_the_labour_fund

### Incomplete first month: social prorated, health indivisible
question: How does the engine treat a business that started mid-month?
answer: Social contributions are prorated by calendar days using `TaxProfile::businessStartedOnDay`; the health contribution is indivisible and paid whole. Insured days are counted only for an incomplete first month; a first-of-month start needs no proration.
evidence: TaxProfile.php; ZusCalculatorTest::test_an_incomplete_first_month_prorates_social_but_not_health, test_the_health_contribution_is_not_prorated_in_an_incomplete_month, test_insured_days_are_counted_only_for_an_incomplete_first_month, test_a_first_of_the_month_start_needs_no_proration

### Money is integer grosze; tax rounds to złoty, contributions to grosze
question: How does the accounting engine avoid float rounding errors in Polish tax arithmetic?
answer: `Poland\Domain\Money` holds an integer number of grosze with no float path into a stored value; `times()` rounds half-up to whole grosze; `roundedToZloty()` applies Ordynacja podatkowa art. 63 § 1 (below 50 gr down, 50 gr and above up) for tax amounts and bases, while contributions stay in grosze. The published preferential total 442,90 zł (2025) differs from a naive 442,89 by one grosz of rounding and the suite pins it; a long run of additions does not drift.
evidence: modules/poland/src/Domain/Money.php; MoneyTest::test_rounding_to_zloty_follows_ordynacja_podatkowa, test_multiplication_rounds_half_up_on_grosze, test_a_long_run_of_additions_does_not_drift; ZusCalculatorTest published totals

### Deadlines shift later only; unknown holiday years are flagged
question: What does the engine do with a deadline when the public-holiday calendar has no entry for that year?
answer: `DeadlineCalendar::for()` moves a deadline forward over Saturdays, Sundays and listed holidays, never earlier. When `deadlines.php` has no holiday list for the year, it returns the statutory date with `verified => false` and the report warns "Kalendarz świąt nie obejmuje ... Sprawdź termin ręcznie" rather than showing a date that might be a day early. The calendar covers 2025–2027; add years before then.
evidence: modules/poland/src/Support/DeadlineCalendar.php; SettlementEngine warnings; KasaFiskalnaReportTest::test_deadlines_move_off_weekends_and_holidays; docs/OPEN_ITEMS.md "The public holiday calendar ends in 2027"

### Strict money parsing prevents factor-of-100 entry errors
question: How does Money::parse handle "31 250,50", "48,500.00" and "1,234"?
answer: Ambiguous separators are the most common way a cash-register total is entered wrong by a factor of 100, so the parser is strict: it strips currency markers and thousands spaces (including NBSP), treats the rightmost separator as decimal when both appear, reads a lone comma followed by exactly three digits in a thousands pattern as thousands, and rejects anything it cannot read one way only. `POST /poland/sprzedaz` was verified to parse "31 250,50" correctly.
evidence: modules/poland/src/Domain/Money.php parse(); MoneyTest::test_it_parses_polish_and_english_formats, test_it_reads_a_three_digit_group_after_a_comma_as_thousands, test_it_refuses_unreadable_amounts; docs/SUPPORTED_VERSIONS.md

### An unrecorded month is refused, not treated as zero
question: What happens if you settle a month with no cash-register report?
answer: `SettlementEngine::settle` throws "No sales recorded ... an unrecorded month is not a month of zero sales". A gap earlier in the year does not abort but produces a warning naming the months, because PIT advances are cumulative and a missing March understates every month after it.
evidence: SettlementEngine.php; KasaFiskalnaReportTest::test_an_unrecorded_month_is_refused_rather_than_treated_as_zero, test_a_gap_earlier_in_the_year_is_reported_as_incomplete

### Expired ZUS scheme is reported, never auto-switched
question: What does the engine do when preferential contributions run out after 24 months?
answer: `TaxProfile::zusSchemeExpiredAt()` reports that the configured scheme is no longer available (ulga na start 6 months, preferential 24), and the engine keeps computing on the configured scheme while saying so, because dropping a taxpayer off preferential contributions is a decision with a deadline attached.
evidence: TaxProfile.php; ZusCalculatorTest::test_an_expired_scheme_is_reported_and_not_silently_changed, test_time_limited_schemes_report_expiry_without_changing_themselves

### Amount-only bank matches never auto-book
question: When does the reconciliation matcher auto-book a bank transaction to an invoice?
answer: MATCHED requires the amount to the grosz AND an identifying reference in the payment title (separators stripped so "FV 2026 08 417" matches "FV/2026/08/417"); amount alone caps confidence at 0.75 and never auto-books, because two invoices for the same round sum in one month are ordinary. Direction must agree first; one document cannot be claimed by two transactions; a person's decision is never overwritten by a rerun. `POLAND_AUTO_BOOK_CONFIDENCE` defaults to 0.9.
evidence: docs/AUTOMATION.md "Matching"; config/poland.php reconciliation; ReconciliationTest::test_amount_to_the_grosz_plus_a_reference_is_a_match, test_the_right_amount_without_a_reference_is_only_possible, test_one_invoice_is_not_matched_by_two_transactions, test_a_payment_in_the_wrong_direction_never_matches

### KSeF cursor advances only on a complete run; dedup by unique index
question: How does the KSeF sync survive a timeout after the server accepted the request?
answer: The contract is request page → validate → persist all invoices → commit → advance cursor; on any failure rollback and the cursor does not advance. Invoice identity is protected by a database unique index on `(tax_profile_id, ksef_number)` rather than "have we imported this?" logic, because that logic is exactly what fails during a retry after a timeout. `SyncCursor` extracts the advance rule so it is testable without a database; an interrupted sync reports where to resume and is never reported as clean.
evidence: docs/PRODUCTION_AUDIT_2026-09-07.md "The cursor contract"; docs/AUTOMATION.md "KSeF"; SyncSafetyTest::test_a_failed_run_does_not_advance_the_mark, test_a_run_interrupted_twice_still_never_loses_ground, test_a_partial_sync_reports_where_to_resume_and_is_not_clean

### KSeF token never leaks and is InvoiceRead-only
question: How is the KSeF token protected in the accounting app?
answer: Encrypted at rest by the model cast (verified as ciphertext in the MariaDB column); excluded from `toArray()`, JSON, `__debugInfo()`, serialization; `KsefSession` redacts it in `__toString`/print_r; `reveal()` is the single greppable accessor (0 call sites in src today, bound ≤ 2 in the release gate). `KsefScope::allowed()` returns only InvoiceRead and `KsefCredentialModel::revealToken()` re-checks the scope, so a row edited to say InvoiceWrite still cannot be used. The ordinary KSeF password is never stored.
evidence: docs/RELEASE_RECORD_2026-09-07.md §9; tests/Unit/CredentialSecurityTest.php (properties 1–10); KsefScope.php

### A new invoice never rewrites a finished report
question: What happens when a KSeF invoice arrives after the month's report was generated?
answer: The report stays at its version; the month is marked REQUIRES REVIEW with `NEW_DOCUMENTS_AFTER_REPORT`, a `report.requires_review` audit event is recorded, and regeneration writes the next version with the previous retained. Verified end to end on MariaDB: v1 unchanged with checksum, v2 produced, both restored byte-identical.
evidence: docs/RELEASE_RECORD_2026-09-07.md §5; ReleaseGateTest::test_gate_5_a_new_document_never_rewrites_a_settled_report; ReportVersionModel refuses updates/deletes

### Payment checklist distinguishes NOTHING TO PAY from an unpaid zero
question: How does the payment checklist avoid showing a VAT surplus as an amount due?
answer: The checklist always has three lines (ZUS, PIT, VAT) with `PaymentStatus` Unpaid / Paid / NothingToPay; a VAT-exempt taxpayer gets NOTHING TO PAY rather than an unpaid zero, and a VAT surplus is stored in its own column so it can never render as an amount due. Payments record date, amount, reference and notes; a shortfall stays visible; a paid line survives recalculation.
evidence: docs/CHANGELOG.md pre-live "Payment checklist"; AccountantReportTest::test_a_vat_exempt_taxpayer_gets_nothing_to_pay_not_an_unpaid_zero, test_a_vat_surplus_is_never_shown_as_an_amount_to_pay, test_the_checklist_always_has_all_three_lines, test_a_shortfall_between_due_and_paid_is_visible

### Backup is verified by restoring in the same script
question: How does the accounting app know its backups are restorable?
answer: `deploy/backup.sh` dumps the database and immediately restores into `<db>_restore_check`, compares row counts on the accounting tables and exits non-zero on mismatch — "an unverified backup is a belief, not a backup", so verification is not a separate job somebody might skip. `bin/data-safety-drill.sh` goes further (17 tables, report checksums, KSeF XML SHA-256, decisions, amounts, orphans) and was run for real: 27 checks passed.
evidence: deploy/backup.sh; bin/data-safety-drill.sh; docs/RELEASE_RECORD_2026-09-07.md §10; docs/DEPLOYMENT.md "Backups"

### Calculation, preparation and filing are three stages with three truth conditions
question: How does the accounting app avoid telling somebody their taxes are "done"?
answer: `SettlementStage` {Calculated, Prepared, Filed} advances one step at a time and each stage is reached only by its own truth condition: computed_at for arithmetic; prepared_at plus a validated `pl_prepared_documents` row (refused for estimates and unverified rates); filed_at only when `FilingResult::accepted()` returns a non-empty reference. `SettlementModel::stage()` derives the stage from the timestamps rather than trusting a column. Every `FilingChannel::automated()` is false and a test keeps it so.
evidence: docs/ARCHITECTURE.md "Three stages, three different claims"; FilingLifecycleTest::test_a_filing_result_without_a_reference_is_not_an_acceptance, test_stages_advance_only_one_step_at_a_time, test_only_the_filed_stage_counts_as_submitted, test_no_filing_channel_is_automated_yet_and_says_so

### Rate provenance is a first-class property, with a test that must eventually fail
question: How does the codebase force the transition from secondary to official rates to be deliberate?
answer: Every rate version carries `VerificationStatus` and full provenance; a version missing any field fails to load and `official` requires a `source_url`. `test_the_shipped_tables_are_honest_about_not_being_officially_verified` is designed to fail once every version is official — that failure is the signal to delete it and update OPEN_ITEMS. CI's `laravel-integration` job fails likewise if `poland:rate-provenance --todo` exits 0, so the change cannot happen quietly.
evidence: docs/RATE_VERIFICATION.md; RateTableTest::test_provenance_marked_official_must_carry_the_official_url, test_every_shipped_version_carries_complete_provenance; .github/workflows/ci.yml

### Historical settlements stay reproducible when rates change
question: Why does each settlement store the rate versions it used?
answer: Rates change; recomputing an old month from today's tables would quietly rewrite history. `pl_settlements.report` stores the report verbatim and `rate_provenance` stores the version identifier, source and verification status of every table used; a 2025 month uses the 2025 social base (5 203,80 → 1 773,96), never 2026's; settling the same month twice yields identical figures and sources.
evidence: docs/ARCHITECTURE.md "Versioning"; HistoricalReproducibilityTest (12 tests) incl. test_a_2025_month_uses_2025_social_bases_not_2026, test_settling_the_same_historical_month_twice_gives_the_same_answer, test_every_settlement_records_which_rate_versions_produced_it

### Ryczałt health band reduction by social contributions is an election
question: Does the engine automatically subtract social contributions when choosing the ryczałt health band?
answer: No — art. 81 ust. 2g allows reading the band from revenue net of social contributions paid, but that is an election, so it is a profile flag (`reduce_health_band_by_social`, default true in `TaxProfile`) and is printed on the report that used it. `replayYear` sums social paid so far for this purpose. Crossing a band mid-year raises the contribution for the rest of the year and creates an annual top-up; both are warned about, the annual settlement is not computed.
evidence: docs/POLAND_TAX_ENGINE.md; TaxProfile.php; ZusCalculatorTest::test_social_contributions_paid_lower_the_band_reference, test_the_health_band_step_raises_zus_for_the_rest_of_the_year; docs/OPEN_ITEMS.md P2

### NIP checksum validated at construction
question: Does the accounting app validate a NIP?
answer: `TaxProfile::isValidNip()` strips non-digits, requires 10 digits, and applies weights 6,5,7,2,3,4,5,6,7 mod 11; a remainder of 10 can never be a check digit. A bad NIP is refused when the profile is constructed; NIPs compare the same however punctuated.
evidence: modules/poland/src/Domain/TaxProfile.php; TaxProfileTest::test_nip_checksum_is_validated, test_a_bad_nip_is_refused_at_construction; ValueComparisonTest::test_a_nip_compares_the_same_however_it_is_punctuated

### Shop: an empty set of figures is NO DATA, not ACTUAL zero
question: In Shop Intelligence, what does a total over zero figures mean?
answer: `Total::of([])` returns zero with certainty ESTIMATED and provenance ANALYTICAL_ESTIMATE and figure count 0 — i.e. NO DATA — never ACTUAL zero, because absence is not evidence ("no count taken ≠ nothing missing"). A mixed total cannot be described without its split because `describe()` builds the split in the same method as the value.
evidence: shop-intelligence/src/Truth/Total.php; MoneyAndTruthTest::test_r12_an_empty_set_of_figures_is_not_actual_zero, test_r11_a_mixed_total_cannot_be_described_without_its_split; docs/FABLE_BRIEFING_2026-09-08.md §2 item 12

### Shop: ReviewFlag cannot accuse and cannot exist without innocent explanations
question: How does Shop Intelligence guarantee "never assume theft"?
answer: `Shop\Truth\ReviewFlag`'s constructor rejects any explanation containing accusatory vocabulary (English and Polish: theft, stole, fraud, embezzl, skimming, pocketed, kradzież, złodziej, oszustwo, defraudacja, nieuczciw, …) and rejects an empty list of `possibleExplanations`, so every red item on screen opens into "here is the difference, here is what usually causes it". The briefing warns the word list is incomplete and will not catch phrasing that accuses without a keyword.
evidence: shop-intelligence/src/Truth/ReviewFlag.php; tests test_r13_a_review_flag_cannot_accuse_anyone, test_r13_the_accusation_guard_reads_polish, test_r14_a_review_flag_must_offer_innocent_explanations; docs/FABLE_BRIEFING_2026-09-08.md §5

### Shop: forbidden AI actions are tested by looping over the enum
question: How does Shop Intelligence keep the AI prohibition list and its tests in sync?
answer: `AiAction` enumerates 7 permitted and 11 forbidden actions; `AiBoundary::assertPermitted()` throws `AiBoundaryViolation` for any forbidden one. `test_r27_every_forbidden_ai_action_throws` iterates `AiBoundary::forbiddenActions()` instead of listing cases, so a twelfth prohibition is enforced automatically, and a companion test checks the enum against the specification's own list by name so one cannot be quietly deleted.
evidence: shop-intelligence/src/Ai/AiAction.php, AiBoundary.php; shop-intelligence/tests/AiBoundaryTest.php; shop-intelligence/docs/REGRESSION_MAP.md "Why R27 is written as a loop"

### Shop: declared cash and bank-confirmed cash stay distinguishable
question: How does Shop Intelligence show an invoice settled partly by bank and partly by declared cash?
answer: A 5 000 invoice settled 3 000 by bank and 2 000 by declared cash is FULLY ALLOCATED, but `EvidenceType::isIndependentlyCorroborated()` keeps the two halves apart forever (BANK_CONFIRMED true, USER_DECLARED false), so no rendering can read as "5 000 found in the bank". Importing the same transfer twice makes the invoice OVER_ALLOCATED rather than double-settled; an AI suggestion cannot settle a document.
evidence: shop-intelligence/src/Truth/EvidenceType.php, src/Money/AllocationSet.php; tests test_r01_r02_a_fully_allocated_invoice_keeps_bank_and_declared_apart, test_r03_over_allocation_is_detected_and_explained, test_r04_an_ai_suggestion_cannot_settle_a_document

### Shop: notes are never ranked as losses; three data points are not a trend
question: Why does the loss ranking exclude explanatory notes, and when does the monitor stay silent?
answer: `LossRanking` ranks the worklist by money at stake and lists reading notes separately, because a 9 000 zł note must not head a worklist above a 500 zł real problem — inflating the worklist is its own dishonesty. `Baseline` requires `MINIMUM_PERIODS = 3` and uses a median; the monitor stays silent without enough history. The briefing flags the median baseline as possibly wrong for a seasonal shop.
evidence: shop-intelligence/src/Reporting/LossRanking.php, src/Monitoring/Baseline.php; tests test_notes_about_how_to_read_a_figure_are_not_ranked_as_losses, test_the_monitor_stays_silent_without_enough_history; docs/FABLE_BRIEFING_2026-09-08.md §5

### Isolation guard excludes files that name forbidden things in order to forbid them
question: Why does check-isolation.sh exclude AiAction.php, IsolationTest.php and whole-line comments?
answer: Those files and comments name the trading system, KSeF or the accounting DB precisely to prohibit them; a guard that cannot tell a prohibition from a violation gets switched off within a week. So both isolation scripts strip whole-line comments, exclude `*.md`, and exclude the guard scripts and boundary enums/tests by name. The accounting guard was tested in both directions: it passes on a clean tree and fails when a trading reference is introduced.
evidence: bin/check-isolation.sh; shop-intelligence/bin/check-shop-isolation.sh; docs/ISOLATION.md "How it is enforced"; docs/DEFINITION_OF_DONE.md condition 13
