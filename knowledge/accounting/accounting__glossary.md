---
title: Accounting application glossary
domain: accounting
repo: sabuj14eu/Accounting-
sources: CLAUDE.md, README.md, docs/POLAND_TAX_ENGINE.md, docs/ARCHITECTURE.md, docs/AUTOMATION.md, docs/RATE_VERIFICATION.md, docs/PRODUCTION_AUDIT_2026-09-07.md, modules/poland/config/rates/*.php, modules/poland/src/Domain/Enums/*.php, modules/poland/src/Domain/TaxProfile.php, modules/poland/src/Rates/*.php, modules/poland/src/Certainty/*.php, modules/poland/src/Ksef/KsefScope.php, modules/poland/src/Reporting/*.php, shop-intelligence/src/Truth/*.php, shop-intelligence/src/Ai/AiAction.php, shop-intelligence/src/Comparison/AccountsSnapshot.php, shop-intelligence/docs/BANKING_UX.md
verified_on: 2026-09-16
classification: INTERNAL
---

# Accounting application glossary

Terms as used in the accounting app (`modules/poland`, namespace `Poland\`) and Shop Profit Intelligence (`shop-intelligence`, namespace `Shop\`). Polish statutory terms are explained as the repository uses them; where the repo gives no definition, only the repo's usage is stated.

## Polish tax and business terms

**JDG (jednoosobowa działalność gospodarcza)** — a Polish sole-trader business; the accounting app is built for one JDG with a fiscal cash register (`README.md`, `docs/POLAND_TAX_ENGINE.md`).

**ZUS (Zakład Ubezpieczeń Społecznych)** — the Polish social insurance institution. In the app "ZUS" covers social contributions (`zus_social`: pension 19.52%, disability 8%, voluntary sickness 2.45%, accident 1.67%, labour fund 2.45%) plus the health contribution (`zus_health`); settled by the 20th of the following month for a sole trader with no employees.

**Składka zdrowotna (health contribution)** — the ZUS health insurance contribution. Its contribution year runs 1 February–31 January; ryczałt pays a band amount by revenue since 1 January, skala pays 9% and liniowy 4.9% of the previous month's income, never below the statutory minimum (`zus_health.php`).

**Składki społeczne (social contributions)** — pension, disability, sickness, accident and labour-fund contributions on a base set by the ZUS scheme (`zus_social.php`).

**Fundusz Pracy (FP)** — the Labour Fund contribution (2.45%, combined with the Solidarity Fund in the table), due only from a base at or above the minimum wage — which is why preferential contributions pay none.

**PIT (podatek dochodowy od osób fizycznych)** — personal income tax. The app computes monthly advances (zaliczki) cumulatively from 1 January under one of three regimes; deadline day 20 of the following month (`pit.php`).

**Skala (skala podatkowa)** — the progressive PIT scale: 12% up to the first threshold, 32% above, with a tax-free allowance and tax-reducing amount; taxes income (revenue less costs less social ZUS); no health deduction since 2022. `PitRegime::Scale`.

**Liniowy (podatek liniowy)** — flat 19% PIT on income; paid health contributions deductible up to an annual cap. `PitRegime::Flat`.

**Ryczałt (ryczałt od przychodów ewidencjonowanych)** — lump-sum PIT as a rate on REVENUE, costs not deductible; half of paid health contributions reduces revenue. `PitRegime::LumpSum`. The applicable rate depends on the activity (art. 12) and is the taxpayer's declaration; the repo lists 17%, 15%, 14%, 12.5%, 12%, 10%, 8.5%, 5.5%, 3%, 2% as UI hints.

**Zaliczka (advance)** — a monthly PIT advance; `PitSettlement::advanceDue` is what the month adds on top of advances already due.

**Kwota wolna / kwota zmniejszająca podatek** — tax-free allowance (30 000 zł in the tables) and the tax-reducing amount (3 600 zł) on the scale.

**Danina solidarnościowa (solidarity levy)** — 4% above a 1 000 000 zł threshold; annual (PIT-DSF), never part of a monthly advance; the engine flags the threshold.

**VAT** — value added tax; rates 23% (A), 8% (B), 5% (C), 0% (D) plus `zw` (exempt, art. 43) and `np` (outside scope). Output VAT is extracted from gross takings; VAT payable = output − input; deadline and JPK by the 25th.

**Zwolnienie podmiotowe (art. 113)** — the size-based VAT exemption below an annual turnover limit (200 000 zł in 2025, 240 000 zł in 2026 per the tables); `VatStatus::ExemptBySize`; the report warns at 80% of the limit.

**Zwolnienie przedmiotowe (art. 43)** — activity-based VAT exemption; `VatStatus::ExemptByActivity`.

**Czynny podatnik VAT** — a VAT-registered taxpayer; `VatStatus::Registered`; revenue for income tax is net.

**Kasa fiskalna / raport z kasy** — the fiscal cash register and its monthly report (gross total per VAT letter); the one number the workflow starts from. Letters A and B are fixed by regulation, C–G taxpayer-assigned.

**KPiR (księga przychodów i rozchodów)** — the revenue-and-expense book for skala/liniowy; Phase 2, not built; its absence is why those regimes are upper bounds.

**Ewidencja przychodów** — the revenue register for ryczałt; Phase 2 as a proper book.

**JPK (Jednolity Plik Kontrolny)** — the standard audit file; JPK_V7M (monthly) / JPK_V7K (quarterly) VAT files, JPK_FA, JPK_KR; Phase 4, not built; `FilingChannel::JpkV7`.

**KSeF (Krajowy System e-Faktur)** — the national e-invoice system. The app's KSeF layer is InvoiceRead-only, uses a revocable token (never the KSeF password), parses FA(1)/(2)/(3) XML, and has no HTTP transport yet.

**FA(1)/FA(2)/FA(3)** — KSeF structured invoice XML schema versions; the parser is namespace-agnostic.

**NIP (Numer Identyfikacji Podatkowej)** — the tax identification number; validated by checksum (weights 6,5,7,2,3,4,5,6,7 mod 11) in `TaxProfile`; used to identify invoice direction.

**PESEL** — the Polish personal identification number. The repository does not use or define it (UNKNOWN in this codebase; only NIP is handled).

**PKD** — Polish activity classification; the ryczałt rate depends on it and the taxpayer must confirm theirs (`docs/OPEN_ITEMS.md`).

**PKWiU** — Polish product/service classification referenced in the ryczałt rate hints.

**WIS** — binding rate information for VAT; the repo notes which VAT rate applies to a product comes from the annexes and a WIS, not from the rate list.

**Dz.U. (Dziennik Ustaw)** — the Journal of Laws; the official source rates must be confirmed against.

**GUS** — the statistics office whose Q4 average-wage communiqué sets the ryczałt health reference wage.

**ISAP** — the Sejm's legal acts database; `official_source_url` for statutes.

**NBP** — the National Bank of Poland; table A exchange rates, Phase 2; `UnavailableExchangeRateProvider` refuses meanwhile.

**Ordynacja podatkowa** — the Tax Ordinance; art. 63 § 1 (rounding to złoty), art. 12 § 5 (deadline shift).

**Ulga na start** — first 6 months of business: health contribution only, no social. `ZusScheme::UlgaNaStart`.

**Preferencyjne składki (preferential ZUS)** — 24 months on a base of 30% of the minimum wage. `ZusScheme::Preferential`.

**Mały ZUS Plus** — a scheme whose base derives from the previous year's income, bounded by the preferential and full bases, capped at 36 months in any 60; the base is supplied, not derived. `ZusScheme::MalyZusPlus`.

**Pełne składki (full ZUS)** — contributions on 60% of the forecast average wage. `ZusScheme::Full`.

**Chorobowe** — sickness insurance, voluntary for an entrepreneur (`TaxProfile::sicknessInsurance`).

**Wypadkowe** — accident insurance; 1.67% for a payer with ≤9 insured, overridable (`accidentRate`).

**Memoriałowo / kasowo** — accrual vs cash basis for deducting ZUS contributions from PIT: `ContributionDeductionBasis::AccruedForMonth` (default) vs `PaidInMonth`.

**Grosz (pl. grosze)** — 1/100 of a złoty; all money in both applications is an integer number of grosze.

**Złoty (zł, PLN)** — the currency; tax amounts and bases round to full złoty.

**DRA** — the ZUS monthly settlement declaration referenced in the deadline label "Składki ZUS (DRA / opłata za miesiąc)".

**PIT-28 / PIT-36 / PIT-36L** — annual returns (ryczałt / scale / flat) named in `FilingChannel::PitReturn`; not built.

**e-Deklaracje** — the government e-filing gateway; named only in the shop isolation guard as a forbidden path.

## Accounting-app code terms

**Money** — `Poland\Domain\Money`, integer grosze, strict `parse()`, half-up `times()`, `roundedToZloty()`.

**Period** — `Poland\Domain\Period`, a settlement month "YYYY-MM" with year-to-date and quarter helpers.

**TaxProfile** — everything about the taxpayer that changes the arithmetic; no defaults for regime, ryczałt rate or ZUS scheme.

**Ledger** — the in-memory collection of `FiscalSalesReport`s and `PurchaseRegister`s by period; `missingMonths()`, `hasAnyPurchases()`.

**FiscalSalesReport / SalesLine** — the cash-register report and its per-rate lines (optional per-line ryczałt rate).

**PurchaseRegister** — deductible net costs and input VAT for a month.

**SettlementEngine / replayYear** — the orchestrator that refuses missing or unverified rates, replays January forward, and produces a `MonthlyTaxReport`.

**MonthlyTaxReport** — "how much do I have to pay for this month?" in one object; carries `DISCLAIMER`, `isEstimate`, `rateProvenance`, `ratesFitForFiling`.

**DISCLAIMER** — `MonthlyTaxReport::DISCLAIMER`: "To jest WYLICZENIE, nie deklaracja..." — never removed from a view (rule 2).

**isEstimate** — true when the result is an upper bound rather than exact (income regime without costs, or VAT payer without a purchase register); blocks filing.

**MissingRateException** — thrown when a period has no rate version for a table; names the table and the month (rule 4).

**UnverifiedRateException** — thrown by the engine under `POLAND_REQUIRE_OFFICIAL_RATES=true` when any table used is not `official`.

**VerificationStatus** — `Official` (confirmed at the issuing authority), `Secondary` (competent publication, arithmetically cross-checked; all shipped versions), `Unverified` (never usable).

**RateProvenance** — the per-version record of source document, source URL, official URL, publication date, check date, checker and notes.

**RateRepository / coverage()** — loads the tables; `coverage($period)` reports which tables are missing for a month.

**SettlementStage** — Calculated → Prepared → Filed; one step at a time; only Filed means submitted.

**FilingChannel** — JpkV7, Ksef, Zus, PitReturn, Manual; `automated()` is false for all.

**FilingResult::accepted()** — requires a non-empty reference and no error; the only thing that sets `filed_at`.

**filed_at** — the only field meaning "submitted"; set by a successful submission with a reference and nothing else.

**pl_ tables** — every table the module owns is prefixed `pl_` so it never collides with upstream.

**pl_audit_events** — append-only audit trail; updates and deletes refused at the model level.

**pl_report_versions** — immutable numbered report snapshots with checksums; recompute writes n+1.

**DataCertainty** — Verified, Calculated, RequiresReview, NotEnoughData, Blocked, Failed; combined by worst case.

**Caveat / ResolvedBy** — a reason code (e.g. OFFICIAL_RATES_NOT_VERIFIED) with who clears it: User (taxpayer), Operator, Accountant.

**IntegrationStatus** — the dashboard panel states NOT CONNECTED / AVAILABLE / NOT AVAILABLE / NOT VERIFIED / DISABLED.

**InterpretationBoundary / RESERVED_FOR_ENGINE / EVIDENCE_FIELDS** — the AI boundary: engine-owned fields an interpretation may never set vs statements about a document it may.

**stated_amount vs zus_total** — "the letter says 2 757,34" (evidence, allowed) vs "you owe 2 757,34" (tax conclusion, forbidden).

**KsefScope** — InvoiceRead is the only allowed scope; InvoiceWrite and CredentialsManage exist only to be named in refusals.

**TransportGate** — throws when production is configured with a fake KSeF transport; wraps transport errors so they never read as empty results.

**SyncCursor** — the KSeF high-water mark rule: advances only after a complete run.

**TransactionLifecycle** — Imported, Unmatched, PossibleMatch, Matched, PossibleDuplicate, ExcludedFromReconciliation, ConfirmedDistinct, ConfirmedDuplicate; nothing deletes.

**MatchQuality** — Matched (amount + reference), Possible (needs approval), Unmatched (never booked).

**Completeness** — a bank statement's COMPLETE / PARTIAL / UNKNOWN / OUTSIDE_PERIOD coverage of the month.

**DocumentAction** — government-letter classes: PaymentRequired, ResponseRequired, InformationOnly, PossibleIssue, Unknown.

**PaymentStatus / ObligationKind** — Unpaid, Paid, NothingToPay for Zus, Pit, Vat checklist lines.

**DeadlineCalendar** — shifts statutory deadlines later over weekends/holidays; `verified=false` when the year has no holiday list.

**pl-tax** — the framework-free CLI `modules/poland/bin/pl-tax`.

**poland:report / poland:verify-rates / poland:rate-provenance** — the three artisan commands.

**POLAND_REQUIRE_OFFICIAL_RATES** — env flag; true in production makes the engine refuse secondary rates.

**Foundation** — the installed, pinned Liberu ERP (`FOUNDATION_REF`), not vendored.

**Release gate / REQUIRES HUMAN** — `bin/release-gate.sh`; gate 12 (real-data pilot) is never auto-passed.

**Data-safety drill** — `bin/data-safety-drill.sh`; backup, restore to `<db>_drill`, compare; must exit 0 before going live.

**LIVE APPLICATION / PRODUCTION ACCOUNTING / AUTOMATED FILING** — the three milestones; only the first is reached.

## Shop Profit Intelligence terms

**Shop Profit Intelligence** — the separate management analysis tool in `shop-intelligence/`; three pages (Money, Stock, Profit); not the accounting service.

**Provenance classes** — `Shop\Truth\Provenance`: OFFICIAL ACCOUNTING FACT (carried from the accounting side, never produced here), ANALYTICAL ESTIMATE (computed here), USER DECLARATION (typed by a human), AI SUGGESTION (never binding); combined by worst case.

**Certainty** — `Shop\Truth\Certainty`: ACTUAL (happened, with evidence), EXPECTED (scheduled, not yet happened), ESTIMATED (from a model or average), USER DECLARED (asserted, uncorroborated); Polish labels RZECZYWISTE / OCZEKIWANE / SZACOWANE / ZADEKLAROWANE; never summed without the split displayed.

**EvidenceType** — what stands behind a movement (BANK_CONFIRMED, CARD_TERMINAL, PLATFORM_STATEMENT, CASH_COUNTED, SUPPLIER_INVOICE, FISCAL_REPORT, USER_DECLARED, RECURRING_SCHEDULE, ESTIMATED, AI_SUGGESTED); it decides provenance, certainty and corroboration; callers cannot set them.

**Figure / Total** — a single amount with its source reference; the sum carrying its mix; `Total::of([])` is NO DATA, not ACTUAL zero.

**ReviewFlag** — a difference the system cannot explain; refuses accusatory words (EN/PL) and requires innocent explanations; severities INFO, REQUIRES_REVIEW, URGENT_REVIEW.

**REQUIRES REVIEW** — the status for any cash, stock or platform difference; never an accusation, never a name.

**NOT COUNTED / NO DATA** — nobody checked; explicitly not the same as zero.

**AllocationState** — UNALLOCATED, PARTIALLY_ALLOCATED, FULLY_ALLOCATED, OVER_ALLOCATED (same money booked twice).

**MatchHistory / MatchRevision** — append-only match corrections with who, when and why; no delete, no setter.

**PlatformSettlement** — Glovo/Uber Eats payout reconciliation: gross − commission − fees = expected vs received; NO_PAYOUT_RECORDED is never RECONCILED.

**StockReconciliation** — opening + purchases − theoretical = expected vs counted per ingredient; a product with no recipe consumes UNKNOWN.

**Contribution (ChannelResult::contribution())** — revenue less direct costs per channel; NOT profit (no rent, wages, electricity).

**Confirmed result / projected result** — page 3's two profit figures: ACTUAL-only vs including EXPECTED and ESTIMATED.

**PriceReview** — GREEN / AMBER / RED against a target margin; explains, never changes a price.

**AccountsSnapshot** — the only route in from the accounting app: figures imported by hand with period, revenue, costs, importedBy, importedAt, sourceDescription; provenance OFFICIAL_ACCOUNTING_FACT; computes nothing, connects to nothing.

**AccountsComparison** — compares the shop's figures with an AccountsSnapshot and reports differences; has no write-shaped method.

**AiAction / AiBoundary** — 7 permitted (read, extract, classify, suggest match, identify anomaly, explain, summarise) and 11 forbidden actions; `assertPermitted()` throws `AiBoundaryViolation`.

**Baseline** — median over at least `MINIMUM_PERIODS = 3` periods; three data points are not a trend.

**LossRanking** — "Where am I losing money?" ranked by money at stake; notes are listed separately, never ranked as losses.

**Banking-app promises** — the ten design promises in `docs/BANKING_UX.md` (ledger first, pending vs settled, corrections as new entries, closed periods, two dates, drill-down, fixed vocabulary, no unexplained red, idempotent imports, signed and logged actions) — minus a bank's certainty.

**§29 reconciliation** — the open task to check the specification's required regression list against `REGRESSION_MAP.md`'s 27 tests (R01–R27).

**check-shop-isolation.sh** — the 10-check §28 isolation audit; must print "ISOLATION PROVEN".
