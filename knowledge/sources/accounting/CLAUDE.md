---
title: Accounting application constitution (CLAUDE.md)
domain: accounting
repo: sabuj14eu/Accounting-
sources: CLAUDE.md
verified_on: 2026-09-16
commit: 1e3e897
classification: INTERNAL
---

# CLAUDE.md — Accounting application constitution

Read this before touching anything. This repository is the **Polish JDG
accounting application** served at `account.signalmesh.dev`. It is built on the
Liberu accounting ERP and is a completely separate application from the
SignalMesh trading platform.

## IRON RULES — NEVER VIOLATE

1. **THIS APPLICATION NEVER TOUCHES TRADING.** No code here may import from,
   call, read, write to or authenticate against the trading platform, the bot,
   the brain, an executor, a broker or MT5. Not a shared database, not a shared
   queue, not a shared Redis index, not a shared session store, not a shared
   credential. The only permitted relationship is a hyperlink FROM SignalMesh
   TO this application. `bin/check-isolation.sh` enforces this mechanically and
   runs before every deploy — never weaken it to make a change pass.

2. **A CALCULATION IS NOT A FILING.** Nothing in this system may present a
   computed figure as a submitted return. `filed_at` is set by a successful
   submission that returned a reference, and by nothing else. Every report
   carries `MonthlyTaxReport::DISCLAIMER` and it is never removed from a view.

3. **RATES ARE DATA, NEVER CODE.** Every rate, threshold, base and limit lives
   in `modules/poland/config/rates/*.php`, effective-dated, with its source and
   the date it was verified. No calculator may contain a literal złoty amount or
   a statutory percentage. Updating for a new year is a data change plus a test.

4. **REFUSE RATHER THAN EXTRAPOLATE.** A month with no rate version throws
   `MissingRateException`. Carrying last year's ZUS base into a new January
   produces a number that is wrong, plausible and internally consistent — the
   worst kind of number. The engine does not guess and neither do we.

5. **ABSENCE IS NOT ZERO.** No costs recorded ≠ no costs incurred. No month
   recorded ≠ a month of zero sales. Unknown turnover ≠ safely under the limit.
   Each of these has a distinct representation in the domain, and a report that
   is bounded rather than exact says so through `isEstimate` and a warning.

6. **THE AUDIT TRAIL IS APPEND-ONLY.** `pl_audit_events` refuses updates and
   deletes at the model level. Every accounting action records who, what, when,
   old value, new value, period, source and result.

7. **AN ISSUED DOCUMENT IS NEVER SILENTLY REWRITTEN.** A changed cash-register
   month becomes a correction that supersedes the previous report and requires a
   reason; the superseded row stays. Corrections to invoices are correction
   documents, never edits.

8. **SECRETS ARE NEVER COMMITTED AND NEVER LOGGED.** KSeF tokens especially:
   they are bearer credentials for filing tax documents in someone's name.

9. **EVERY DISPLAYED NUMBER CARRIES ITS PROVENANCE.** Source → rate table
   version → period → formula → legal basis. A figure the taxpayer cannot
   re-derive is a figure they have to take on faith, and tax liabilities are not
   a good place for faith.

10. **THE TAX ENGINE STAYS FRAMEWORK-FREE.** `src/Domain`, `src/Calculators`,
    `src/Rates` and `src/Reporting` must not import Laravel. The engine has to
    keep working when the application does not — the isolation check enforces it.

## LAYOUT

- `modules/poland/` — the Poland layer, a standalone Composer package.
  - `config/rates/` — versioned rate tables (`zus_social`, `zus_health`, `pit`,
    `vat`, `deadlines`), each version with `source` and `verified_on`.
  - `src/Domain/` — `Money` (integer grosze, never floats), `Period`,
    `TaxProfile`, `FiscalSalesReport`, `PurchaseRegister`, `Ledger`.
  - `src/Calculators/` — `VatCalculator`, `ZusCalculator`, `PitCalculator`.
  - `src/Reporting/` — `SettlementEngine` (replays the year), `MonthlyTaxReport`,
    `TextReportRenderer`.
  - `src/Laravel/` — service provider, Eloquent models, controller, commands.
  - `bin/pl-tax` — standalone CLI, no framework required.
- `bin/install-foundation.sh` — installs the pinned Liberu ERP, mounts the module.
- `bin/check-isolation.sh` — the isolation guard. CI and pre-deploy.
- `deploy/` — nginx vhost, systemd units, verified backup script.

## THE RULES THE POLISH TAX CODE HIDES (each cost a bug to find)

- **The health contribution year runs 1 February – 31 January.** January is
  settled on the PREVIOUS year's figures. The rate table is dated by month so
  this comes out right without anybody remembering it. Tested.
- **The health contribution looks back.** Under the scale and the flat tax it is
  9% / 4.9% of the income of the month BEFORE the settled one.
- **PIT advances are cumulative from 1 January.** Never settle a month in
  isolation; `SettlementEngine::replayYear` walks January forward.
- **Ryczałt taxes revenue, the other regimes tax income.** This is why a
  cash-register-only workflow is exact on ryczałt and an upper bound elsewhere.
- **For a VAT payer, revenue is the NET amount.** Taxing the gross takings
  overstates a ryczałt base by 23%.
- **The Fundusz Pracy is due only from a base at or above the minimum wage** —
  which is why the preferential scheme does not pay it. Encoded as the rule, not
  as a per-scheme exception.
- **An incomplete first month prorates social contributions by days, but the
  health contribution is indivisible** and is paid whole.
- **Tax amounts and tax bases round to full złoty** (Ordynacja podatkowa
  art. 63 § 1); contributions stay in grosze.
- **Deadlines move off weekends and public holidays**, later only. When the
  holiday calendar has no entry for the year, the report says the shift could
  not be applied rather than showing a date that might be a day early.

## THE SECOND APPLICATION — SHOP PROFIT INTELLIGENCE

`shop-intelligence/` is a **separate application** living in this repository: a
management analysis tool for the shop (money reconciliation, stock and food
cost, real profit). It is NOT the accounting service and the two share nothing —
no database, no table, no session, no credential, no code, no network path.
Each keeps working when the other is offline.

Its own laws, which sit alongside the ten above rather than under them:
- It never calculates official tax, never files anything, never touches KSeF,
  and has no write path back to the accounting system. The only route between
  them is an `AccountsSnapshot` somebody imports by hand, recorded with who and
  from what; differences are compared and investigated, never auto-corrected.
- Four provenance classes travel with every number — OFFICIAL ACCOUNTING FACT ·
  ANALYTICAL ESTIMATE · USER DECLARATION · AI SUGGESTION — and ACTUAL, EXPECTED,
  ESTIMATED and USER DECLARED are never summed without the split displayed.
- A cash, stock or platform difference is REQUIRES REVIEW with innocent
  explanations listed. `ReviewFlag` refuses accusatory vocabulary outright:
  never assume theft, never name anyone.
- AI may read, extract, classify, suggest, identify anomalies, explain and
  summarise. The eleven forbidden actions are enumerated in `Shop\Ai\AiAction`
  and every one of them is tested.
- Three pages. Do not turn it into another ERP.

Before every commit there: `../modules/poland/vendor/bin/phpunit -c phpunit.xml`
and `./bin/check-shop-isolation.sh`. Read `shop-intelligence/README.md` and
`shop-intelligence/docs/BANKING_UX.md` before touching it.

## HOW TO WORK HERE

Findings first, then code. Small verified diffs over rewrites. Run
`modules/poland/vendor/bin/phpunit` and `bin/check-isolation.sh` before every
commit. Every rate change ships with the source it came from and a test that
checks the published amount against its own stated formula.

## OPEN ITEMS

`docs/OPEN_ITEMS.md` carries what is deferred. An item deferred in conversation
is an item forgotten — if it is not in that file, it does not exist. Delete an
entry only when it is done and verified, and say where the proof is.
