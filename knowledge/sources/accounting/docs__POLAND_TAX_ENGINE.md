---
title: Poland tax engine
domain: accounting
repo: sabuj14eu/Accounting-
sources: docs/POLAND_TAX_ENGINE.md
verified_on: 2026-09-16
commit: 1e3e897
classification: INTERNAL
---

# The Poland tax engine

How a cash-register total becomes a ZUS, VAT and PIT figure, and which parts of
that are exact rather than estimated.

## The one-number workflow

A JDG with a fiscal cash register knows one number a month: the gross total on
the monthly report. Everything below is derived from it plus the taxpayer's
profile.

```
FiscalSalesReport (gross, per VAT designation)
        │
        ├─ VAT:  gross × rate / (1 + rate)  →  output VAT
        │        − input VAT (from the purchase register, if any)
        │
        ├─ revenue for income tax = net if VAT-registered, gross if exempt
        │        │
        │        ├─ ZUS health band (ryczałt) ← revenue accumulated since 1 Jan
        │        └─ PIT base, cumulative since 1 January
        │
        └─ ZUS social ← scheme and base, independent of revenue
```

## Exact or estimated?

This is the honest core of the design.

| Regime | VAT status | Costs recorded | Result |
|---|---|---|---|
| Ryczałt | exempt | no | **exact** |
| Ryczałt | registered | no | PIT exact; VAT is an **upper bound** |
| Ryczałt | registered | yes | **exact** |
| Skala / liniowy | any | no | **upper bound** — these tax income, not revenue |
| Skala / liniowy | any | yes | **exact** |

Ryczałt taxes *revenue*, so sales data alone is a complete answer. The scale and
the flat tax tax *income*, so without a cost register the engine can only bound
the liability from above — and it says so, in `isEstimate`, in a warning, and in
the report header. It never presents a bound as a payment.

The same applies to VAT: output VAT is exact from the register, but VAT
*payable* is output minus input, and input VAT comes from purchase invoices.
Without them the figure is a ceiling.

## What the engine refuses to do

- **Extrapolate rates.** A month with no rate version throws
  `MissingRateException` naming the table and the month.
- **Treat an unrecorded month as zero.** Settling a month with no cash-register
  report is refused; a gap earlier in the year produces a warning, because PIT
  advances are cumulative and a missing March understates every month after it.
- **Assume a regime, a ryczałt rate or a ZUS scheme.** Each is required in the
  profile and validated.
- **Silently change an expired ZUS scheme.** Preferential contributions run out
  after 24 months; the engine reports that they have and keeps computing on the
  configured scheme, because switching is the taxpayer's decision.
- **Guess a cash-register letter.** Letters A and B are fixed by regulation;
  C–G are assigned by the taxpayer, so an unmapped letter is an error.

## Rate tables

`modules/poland/config/rates/`. Each file holds versions with `effective_from`,
`effective_to`, `source` and `verified_on`. Overlapping versions are rejected at
construction, so a lookup can never depend on array order.

Shipped: **2025** and **2026**.

| Table | What it holds |
|---|---|
| `zus_social` | contribution rates, bases (full, preferential, Mały ZUS Plus bounds), minimum wage |
| `zus_health` | ryczałt bands and reference wage, scale/flat rates, minimum, flat-tax deduction cap |
| `pit` | scale thresholds and the tax-reducing amount, flat rate, ryczałt rate list, solidarity levy |
| `vat` | rates, cash-register letter defaults, the art. 113 exemption limit |
| `deadlines` | statutory days, public holidays per year |

`php artisan poland:verify-rates` reports how far the tables reach. Run it from
the scheduler; when it fails, the fix is a data change and a test, never a code
change.

### Updating for a new tax year

1. Add a version to each table with `effective_from`, `effective_to`, `source`
   and `verified_on`. Never edit an existing version — a settled month must stay
   reproducible.
2. Run the suite. `RateTableTest` checks each published amount against its own
   stated formula (e.g. that a ryczałt health band really is 9% of its stated
   percentage of the reference wage), which catches transcription errors.
3. Add a case to `ZusCalculatorTest` asserting the published headline totals.

## Traps that are handled, and how

Each of these is a place where a plausible implementation is wrong.

**The health contribution year is 1 February – 31 January.** So January 2026 is
settled on the 2025/2026 figures (461,66 / 769,43 / 1 384,97 zł), and February
switches to 2026/2027 (498,35 / 830,58 / 1 495,04 zł). Handled by dating rate
versions in months rather than labelling them by year, so nobody has to
remember. `test_january_uses_the_previous_contribution_year_amounts`.

**The health contribution looks back one month.** Under the scale and the flat
tax the base is the income of the month *before* the settled one. The engine
passes the previous month's income explicitly and returns the statutory minimum
with a note when it is unknown — never the current month's income.

**PIT advances are cumulative.** `SettlementEngine::replayYear` walks January
forward and hands each month what the earlier months produced. A test asserts
that twelve monthly advances sum exactly to the year's cumulative tax.

**Revenue for a VAT payer is net.** Getting this backwards overstates a ryczałt
base by 23%.

**The ryczałt health band may be read from revenue net of social contributions
paid** (art. 81 ust. 2g). That is an election, so it is a profile flag and it is
printed on the report that used it. Crossing a band mid-year raises the
contribution for the rest of the year and creates an annual top-up — both are
warned about.

**Fundusz Pracy follows the base, not the scheme.** It is due from a base at or
above the minimum wage, which is why preferential contributions do not include
it. Encoded as that rule; a mid-month start prorates the base but is still tested
for FP against the full-month base.

**An incomplete first month prorates social contributions by calendar days; the
health contribution is indivisible** and is paid in full.

**Rounding.** Tax amounts and tax bases go to full złoty (Ordynacja podatkowa
art. 63 § 1); contributions stay in grosze. All money is integer grosze —
`Money` has no float constructor path that survives into a stored value, and
multiplication rounds half-up. The published preferential total of 442,90 zł for
2025 differs from a naive 442,89 zł by exactly one groszy of rounding, and the
suite pins it.

**Deadlines move later off weekends and holidays, never earlier.** When the
holiday calendar has no entry for a year the report says the shift could not be
applied instead of showing a date that might be a day early.

## Contribution deduction basis

Contributions reduce PIT when *paid*, and a JDG pays month M's contributions in
month M+1. The two readings differ by one month within a year and converge over
it, so the engine does not choose silently:

- `accrued_for_month` (default) — deduct the contributions accrued for the
  settled month.
- `paid_in_month` — deduct what was actually paid during it, which needs an
  opening balance for the previous December.

Whichever is configured is printed on every report that used it.

## Testing

```bash
cd modules/poland && vendor/bin/phpunit
```

85 tests, 189 assertions. The headline totals published by ZUS for 2025 and 2026
are pinned as fixtures (1 926,76 / 1 773,96 / 456,18 / 442,90 / 420,86 zł), so a
mistyped rate fails immediately rather than quietly changing what a taxpayer is
told to pay.
