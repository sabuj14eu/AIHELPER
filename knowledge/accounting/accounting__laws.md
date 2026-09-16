---
title: Accounting application laws
domain: accounting
repo: sabuj14eu/Accounting-
sources: CLAUDE.md, docs/POLAND_TAX_ENGINE.md, docs/ARCHITECTURE.md, docs/ISOLATION.md, docs/RATE_VERIFICATION.md, docs/PRODUCTION_AUDIT_2026-09-07.md, docs/FABLE_BRIEFING_2026-09-08.md, modules/poland/config/rates/zus_health.php, modules/poland/config/rates/zus_social.php, modules/poland/src/Domain/Money.php, modules/poland/src/Support/DeadlineCalendar.php, modules/poland/src/Reporting/SettlementEngine.php, shop-intelligence/src/Ai/AiAction.php, shop-intelligence/src/Truth/ReviewFlag.php
verified_on: 2026-09-16
classification: INTERNAL
---

# Accounting application laws (the ten iron rules, the shop laws, the hidden tax-code rules)

## The ten iron rules of the accounting app (CLAUDE.md "IRON RULES — NEVER VIOLATE")

**Rule 1 — THIS APPLICATION NEVER TOUCHES TRADING.** No code in the accounting app may import from, call, read, write to or authenticate against the trading platform, the bot, the brain, an executor, a broker or MT5. Not a shared database, queue, Redis index, session store or credential. The only permitted relationship is a hyperlink FROM SignalMesh TO this application. `bin/check-isolation.sh` enforces it mechanically before every deploy — never weaken it to make a change pass. Rationale (`docs/ISOLATION.md`): a failure of accounting cannot stop the trading bot, and a failure of trading cannot corrupt accounting; isolation is violated by ADDING something, at any time, in any file, so it must be checked by a script rather than read once and trusted.

**Rule 2 — A CALCULATION IS NOT A FILING.** Nothing may present a computed figure as a submitted return. `filed_at` is set by a successful submission that returned a reference, and by nothing else. Every report carries `MonthlyTaxReport::DISCLAIMER` ("To jest WYLICZENIE, nie deklaracja...") and it is never removed from a view. Rationale (`docs/ARCHITECTURE.md`): conflating calculation, preparation and filing is how software tells somebody their taxes are "done" when nothing was sent; `FilingResult::accepted()` needs a non-empty reference because "we got a 200" is the exact failure mode.

**Rule 3 — RATES ARE DATA, NEVER CODE.** Every rate, threshold, base and limit lives in `modules/poland/config/rates/*.php`, effective-dated, with its source and the date it was verified. No calculator may contain a literal złoty amount or a statutory percentage. Updating for a new year is a data change plus a test. Rationale (`docs/POLAND_TAX_ENGINE.md`): a settled month must stay reproducible, and a rule change becomes a data change instead of a code change.

**Rule 4 — REFUSE RATHER THAN EXTRAPOLATE.** A month with no rate version throws `MissingRateException`. Carrying last year's ZUS base into a new January produces a number that is wrong, plausible and internally consistent — the worst kind of number. The engine does not guess. Rationale: `SettlementEngine::settle` checks `RateRepository::coverage($period)` first and throws naming the missing tables and the period.

**Rule 5 — ABSENCE IS NOT ZERO.** No costs recorded ≠ no costs incurred. No month recorded ≠ a month of zero sales. Unknown turnover ≠ safely under the limit. Each has a distinct representation, and a bounded report says so through `isEstimate` and a warning. Rationale (`docs/PRODUCTION_AUDIT_2026-09-07.md`): "Missing data is not zero data" — an empty KSeF result, empty OCR, a missing statement all throw.

**Rule 6 — THE AUDIT TRAIL IS APPEND-ONLY.** `pl_audit_events` refuses updates and deletes at the model level (`AuditEventModel` throws in `updating` and `deleting` hooks). Every accounting action records who, what, when, old value, new value, period, source and result.

**Rule 7 — AN ISSUED DOCUMENT IS NEVER SILENTLY REWRITTEN.** A changed cash-register month becomes a correction that supersedes the previous report and requires a reason; the superseded row stays. Corrections to invoices are correction documents, never edits. Rationale: report versions are immutable numbered snapshots with checksums (`pl_report_versions`), and recomputing writes version n+1.

**Rule 8 — SECRETS ARE NEVER COMMITTED AND NEVER LOGGED.** KSeF tokens especially: they are bearer credentials for filing tax documents in someone's name. Enforced by isolation check 3, the release gate security sweep, `.gitignore`, and `CredentialSecurityTest` (token absent from `toArray()`, JSON, debug, `__toString`, serialization; `reveal()` the only accessor).

**Rule 9 — EVERY DISPLAYED NUMBER CARRIES ITS PROVENANCE.** Source → rate table version → period → formula → legal basis. A figure the taxpayer cannot re-derive is a figure they have to take on faith, and tax liabilities are not a good place for faith. Every settlement stores `rate_provenance` and the version identifiers it used.

**Rule 10 — THE TAX ENGINE STAYS FRAMEWORK-FREE.** `src/Domain`, `src/Calculators`, `src/Rates` and `src/Reporting` must not import Laravel. The engine has to keep working when the application does not — isolation check 4 enforces it. Rationale (`docs/ARCHITECTURE.md`): this is what makes `bin/pl-tax` work with nothing but PHP.

## The Shop Profit Intelligence laws (CLAUDE.md "THE SECOND APPLICATION" and the Fable briefing §2)

Shop Intelligence's laws sit alongside the ten above rather than under them:

- **Analysis only, never the accounting service.** It never calculates official tax, never files anything, never touches KSeF, and has no write path back to the accounting system. The only route between them is an `AccountsSnapshot` somebody imports by hand, recorded with who and from what; differences are compared and investigated, never auto-corrected.
- **Never present an estimate as an official accounting result.** Four provenance classes travel with every number — OFFICIAL ACCOUNTING FACT · ANALYTICAL ESTIMATE · USER DECLARATION · AI SUGGESTION (`Shop\Truth\Provenance`).
- **Never mix ACTUAL / EXPECTED / ESTIMATED / USER DECLARED without displaying the split** (`Shop\Truth\Certainty`, enforced by `Total::describe()` which renders the split in the same method that computes the value).
- **The worked example that is the whole design:** a 5 000 zł invoice settled 3 000 by bank and 2 000 by declared cash is FULLY ALLOCATED — but the system must NOT pretend it found the 2 000 in the bank (`EvidenceType::isIndependentlyCorroborated()`).
- **Never assume theft.** A cash, stock or platform difference is REQUIRES REVIEW with innocent explanations listed. `ReviewFlag` refuses accusatory vocabulary outright (English and Polish word list: theft, thief, stole, fraud, embezzl, skimming, dishonest, pocketed, kradzież, złodziej, oszustwo, defraudacja, nieuczciw, …) and refuses to exist without at least one innocent explanation. Never name anyone.
- **Never silently overwrite history.** A correction is a new entry pointing at the original; both stay (`MatchHistory` has no delete and no setter).
- **AI may read, extract, classify, suggest matches, identify anomalies, explain and summarise.** The eleven forbidden actions are enumerated in `Shop\Ai\AiAction`: CHANGE_TRANSACTION, CHANGE_INVENTORY, CREATE_CASH_PAYMENT, CREATE_REVENUE, CREATE_EXPENSE, MARK_INVOICE_PAID, CHANGE_ACCOUNTING_RECORD, CALCULATE_OFFICIAL_TAX, SUBMIT_TO_GOVERNMENT, ACCESS_KSEF_CREDENTIALS, MODIFY_ACCOUNTS_SYSTEM. Every one is tested (`test_r27_every_forbidden_ai_action_throws` loops over the enum).
- **Three pages. Do not turn it into another ERP.** Money, Stock, Profit.
- **Fail-closed behaviour is a feature.** Do not replace refusing adapters with mocked or silent implementations to make the application appear complete (briefing §2 item 13).

Before every commit there: `../modules/poland/vendor/bin/phpunit -c phpunit.xml` and `./bin/check-shop-isolation.sh`.

## The rules the Polish tax code hides (CLAUDE.md, each cost a bug to find)

These are stated in `CLAUDE.md` and elaborated in `docs/POLAND_TAX_ENGINE.md` under "Traps that are handled, and how".

**The health contribution year runs 1 February – 31 January.** January is settled on the PREVIOUS year's figures (ustawa o świadczeniach opieki zdrowotnej, art. 81 ust. 2 per `zus_health.php`). The rate table is dated by month so this comes out right without anybody remembering it: `zus_health.php` versions are `2024-02.1` (2024/2025, effective 2024-02..2025-01), `2025-02.1` (2025/2026, 2025-02..2026-01) and `2026-02.1` (2026/2027, 2026-02..2027-01). Tests: `test_the_health_contribution_year_runs_february_to_january`, `test_january_uses_the_previous_contribution_year_amounts`, `test_january_2026_uses_the_2025_2026_contribution_year`, `test_february_2026_switches_to_the_new_contribution_year`.

**The health contribution looks back one month.** Under the scale and the flat tax it is 9% / 4.9% of the income of the month BEFORE the settled one. `SettlementEngine::replayYear` passes `previousMonthIncome(...)` explicitly; when unknown the engine returns the statutory minimum with a note, never the current month's income. Tests: `test_scale_health_is_nine_percent_of_the_previous_months_income`, `test_flat_health_is_four_point_nine_percent_of_the_previous_months_income`, `test_unknown_previous_income_yields_the_minimum_and_says_so`.

**PIT advances are cumulative from 1 January.** Never settle a month in isolation; `SettlementEngine::replayYear` walks January forward and hands each month what the earlier months produced (revenue YTD, costs YTD, advances YTD, social paid so far). A test asserts twelve monthly advances sum exactly to the year's cumulative tax: `test_pit_advances_accumulate_correctly_across_the_year`. A missing earlier month produces the warning "BRAK DANYCH ZA MIESIĄCE ... Wynik jest niepełny, a nie zerowy."

**Ryczałt taxes revenue, the other regimes tax income.** This is why a cash-register-only workflow is exact on ryczałt and an upper bound elsewhere (`PitRegime::deductsCosts()` is false only for LumpSum). Without a cost register the scale/flat result is `isEstimate = true` with the warning that the PIT figure is an upper bound, and filing is blocked. Tests: `test_income_regimes_flag_a_missing_cost_register_as_an_upper_bound`, `test_lump_sum_from_a_cash_register_alone_is_not_an_estimate`.

**For a VAT payer, revenue is the NET amount.** Taxing the gross takings overstates a ryczałt base by 23%. `FiscalSalesReport::revenueForIncomeTax($vatStatus)` returns net if VAT-registered, gross if exempt. Tests: `test_a_vat_registered_taxpayer_pays_pit_on_the_net_amount`, `test_a_vat_payer_is_taxed_on_net_revenue_in_every_year`.

**The Fundusz Pracy is due only from a base at or above the minimum wage** (ustawa o promocji zatrudnienia, art. 104b/104 per `zus_social.php`), which is why the preferential scheme (base 30% of minimum wage) does not pay it. Encoded as the rule `labour_fund_requires_base_at_least_minimum_wage => true`, not as a per-scheme exception; a mid-month start prorates the base but FP is still tested against the full-month base. Tests: `test_preferential_scheme_pays_no_labour_fund`, `test_a_prorated_full_base_still_owes_the_labour_fund`.

**An incomplete first month prorates social contributions by days, but the health contribution is indivisible** and is paid whole. `TaxProfile::businessStartedOnDay` drives it. Tests: `test_an_incomplete_first_month_prorates_social_but_not_health`, `test_the_health_contribution_is_not_prorated_in_an_incomplete_month`, `test_insured_days_are_counted_only_for_an_incomplete_first_month`.

**Tax amounts and tax bases round to full złoty** (Ordynacja podatkowa art. 63 § 1: below 50 gr down, 50 gr and above up — `Money::roundedToZloty()`); contributions stay in grosze. All money is integer grosze; `Money::times()` rounds half-up. The published preferential total of 442,90 zł for 2025 differs from a naive 442,89 zł by exactly one grosz of rounding and the suite pins it. Tests: `test_rounding_to_zloty_follows_ordynacja_podatkowa`, `test_multiplication_rounds_half_up_on_grosze`.

**Deadlines move off weekends and public holidays, later only** (Ordynacja podatkowa art. 12 § 5; kodeks cywilny art. 115 for ZUS). `DeadlineCalendar::for()` walks forward over Saturdays, Sundays and the `public_holidays` list in `deadlines.php` (years 2025–2027). When the holiday calendar has no entry for the year, it returns the statutory date with `verified => false` and the report warns that the working-day shift could not be applied rather than showing a date that might be a day early. Test: `test_deadlines_move_off_weekends_and_holidays`.

## Further engine refusals that function as laws (docs/POLAND_TAX_ENGINE.md "What the engine refuses to do")

- **Never assume a regime, a ryczałt rate or a ZUS scheme.** Each is required in `TaxProfile` and validated (`test_lump_sum_without_a_rate_is_rejected`, `test_maly_zus_plus_without_a_base_is_rejected`).
- **Never silently change an expired ZUS scheme.** Preferential runs out after 24 months, ulga na start after 6; the engine reports expiry and keeps computing on the configured scheme because switching is the taxpayer's decision (`test_an_expired_scheme_is_reported_and_not_silently_changed`).
- **Never guess a cash-register letter.** A and B are fixed by regulation; C–G are assigned by the taxpayer, so an unmapped letter is an error.
- **Never treat an unrecorded month as zero.** Settling a month with no cash-register report is refused (`test_an_unrecorded_month_is_refused_rather_than_treated_as_zero`).
- **The ryczałt health band reduction by social contributions paid (art. 81 ust. 2g) is an election**, so it is a profile flag (`reduce_health_band_by_social`) printed on the report.
- **The contribution deduction basis is never chosen silently** — `accrued_for_month` (default) or `paid_in_month`; whichever is configured is printed on every report.

## Automation-layer laws (docs/AUTOMATION.md, docs/PRODUCTION_AUDIT_2026-09-07.md)

- **Everything that cannot be done, refuses.** KSeF not configured → refuses; no OCR → refuses; PDF bank statement → refuses naming CSV/MT940/camt.053; no exchange rate → refuses (not 1.0, not yesterday's); unverified tax rates → refuses when `POLAND_REQUIRE_OFFICIAL_RATES=true`.
- **KSeF is InvoiceRead only.** `KsefScope::allowed()` returns exactly `[InvoiceRead]`; the write scopes exist only so a refusal can name them. The ordinary KSeF password is never stored.
- **The cursor advances only on a complete run**; duplicates are prevented by a database unique index on `(tax_profile_id, ksef_number)`, not application logic.
- **A new invoice never rewrites a finished report** — it marks the month REQUIRES REVIEW.
- **AI may never originate a tax liability.** `InterpretationBoundary::RESERVED_FOR_ENGINE` fields throw; `stated_amount` (a fact about the letter) is allowed, `zus_total` (a conclusion) is not. Disagreement → MANUAL REVIEW REQUIRED, favouring neither side.
- **Certainty combines by worst case, never average.** Six states: VERIFIED, CALCULATED, REQUIRES REVIEW, NOT ENOUGH DATA, BLOCKED, FAILED (`DataCertainty`).
- **Production may never select a fake KSeF transport** — `TransportGate` throws.
- **Do not weaken the fail-closed behaviours to make the feature list look bigger** (standing instruction of the audit). Every one is now covered by a test that fails if it is.

## Working laws of the repository (CLAUDE.md "HOW TO WORK HERE" and "OPEN ITEMS")

Findings first, then code. Small verified diffs over rewrites. Run `modules/poland/vendor/bin/phpunit` and `bin/check-isolation.sh` before every commit. Every rate change ships with the source it came from and a test that checks the published amount against its own stated formula. `docs/OPEN_ITEMS.md` carries what is deferred: an item deferred in conversation is an item forgotten — if it is not in that file, it does not exist. Delete an entry only when it is done and verified, and say where the proof is. Report measured numbers, never estimates (`docs/SUPPORTED_VERSIONS.md`: "Never update this table from a changelog").
