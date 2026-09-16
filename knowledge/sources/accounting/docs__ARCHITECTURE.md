---
title: Accounting architecture
domain: accounting
repo: sabuj14eu/Accounting-
sources: docs/ARCHITECTURE.md
verified_on: 2026-09-16
commit: 1e3e897
classification: INTERNAL
---

# Architecture

```
                 ┌──────────────────────────┐
                 │  SignalMesh (trading)    │
                 │  app.signalmesh.dev      │
                 └────────────┬─────────────┘
                              │  one hyperlink, Phase 6
                              ▼
    ┌───────────────────────────────────────────────────┐
    │  Accounting — account.signalmesh.dev              │
    │                                                   │
    │  ┌─────────────────────────────────────────────┐  │
    │  │  Liberu accounting ERP (installed, pinned)  │  │
    │  │  ledger · invoicing · banking · reporting   │  │
    │  └────────────────────┬────────────────────────┘  │
    │                       │  Composer path repository │
    │  ┌────────────────────▼────────────────────────┐  │
    │  │  modules/poland                             │  │
    │  │                                             │  │
    │  │   Laravel layer   provider · models · HTTP  │  │
    │  │   ─────────────────────────────────────────  │ │
    │  │   Reporting       SettlementEngine          │  │
    │  │   Calculators     VAT · ZUS · PIT           │  │
    │  │   Rates           effective-dated tables    │  │
    │  │   Domain          Money · Period · Ledger   │  │
    │  └─────────────────────────────────────────────┘  │
    │                                                   │
    │  own DB · own queue · own storage · own login     │
    └───────────────────────────────────────────────────┘
```

## Why the foundation is installed rather than vendored

Upstream is 7 141 files and 45 MB across 466 modules. Forking it into this
repository would make every upstream upgrade a merge of that size and would bury
the Poland layer — the part that is actually ours — in noise.

So `bin/install-foundation.sh` pins upstream by commit and installs it, and the
Poland layer is mounted as a Composer path repository, which is exactly how
upstream composes its own 466 modules. Upgrading upstream is a one-line change
to `FOUNDATION_REF` plus a test run.

The trade-off is that this repository is not self-contained: a deploy needs
network access to GitHub and Packagist. That is already true of any Composer
project. If reproducibility without network access is ever required, the answer
is a Composer mirror, not a fork.

## The layering rule

Dependencies point one way only:

```
Laravel layer  →  Reporting  →  Calculators  →  Rates  →  Domain
```

`Domain`, `Rates`, `Calculators` and `Reporting` contain no Laravel. That is not
architectural taste: it is what makes `bin/pl-tax` work with nothing but PHP, so
a taxpayer can get a number when the application, the database or the queue is
down. `bin/check-isolation.sh` fails the build if a Laravel import appears in
those directories.

## Why the engine replays the year

Almost nothing about a Polish settlement month is local to that month:

- the PIT advance is cumulative from 1 January;
- the ryczałt health band is chosen by revenue accumulated since 1 January;
- the health contribution under the scale and the flat tax is based on the
  previous month's income;
- deductions depend on contributions from earlier months.

`SettlementEngine::replayYear` therefore walks January forward and hands each
month what the months before it produced. Settling a month in isolation would
drift, and the drift would be invisible.

## Data model

| Table | Holds |
|---|---|
| `pl_tax_profiles` | regime, ryczałt rate, VAT status, ZUS scheme, start date, elections |
| `pl_sales_reports` + `_lines` | cash-register reports as entered; corrections supersede, never overwrite |
| `pl_purchase_summaries` | deductible costs and input VAT per month |
| `pl_settlements` | computed settlements, the full report JSON, and the rate stamps used |
| `pl_audit_events` | append-only; updates and deletes refused at the model level |

Everything the module owns is prefixed `pl_`, so upstream tables and ours can
never collide and an upgrade never has to reconcile them.

`pl_settlements.report` stores the report verbatim, including which rate-table
versions produced it. Rates change; a settlement must stay reproducible as it
stood on the day it was made, and recomputing it later from current tables would
quietly rewrite history.

`filed_at` is the only field in the system that means "submitted". No
calculation sets it.


## Module boundaries and ports

The accounting core knows about interfaces, never about providers. Every
external system enters through a port in `modules/poland/src/Contracts/`, so no
single provider can be hard-wired into the ledger or the calculators.

| Concern | Port | Default binding |
|---|---|---|
| Building a filing document | `DocumentPreparer` | none registered |
| Submitting it | `DocumentSubmitter` | `UnconfiguredSubmitter` — throws |
| Exchange rates | `ExchangeRateProvider` | `UnavailableExchangeRateProvider` — throws |
| Schema selection | `SchemaRegistry` | empty; refuses unregistered periods |

The default bindings **refuse** rather than returning a plausible zero. A
missing exchange rate is not 1.0 and is not yesterday's rate; an unimplemented
KSeF channel is not a silent no-op. Binding a refusing adapter keeps the shape
of the application honest: the stage exists, and it is not implemented.

Concern-by-concern, the layout the specification asks for maps onto:

```
Accounting core        the Liberu ERP (ledger, invoicing, banking, reporting)
Polish invoicing       Phase 2 — not built
KSeF adapter           Contracts\DocumentPreparer + DocumentSubmitter (Phase 3)
VAT/JPK adapter        same ports, different channel (Phase 4)
PIT calculation        Calculators\PitCalculator
ZUS calculation        Calculators\ZusCalculator
NBP adapter            Contracts\ExchangeRateProvider (Phase 2)
filing/export layer    Reporting\SettlementStage + PreparedDocument
audit trail            Laravel\Support\AuditRecorder → pl_audit_events
```

## Three stages, three different claims

```
CALCULATION            an amount derived from available data
   │                   truth condition: the arithmetic is right
   │                   sets: computed_at
   ▼
PREPARATION            a document built and validated against a schema version
   │                   truth condition: it exists and validates
   │                   sets: prepared_at, a pl_prepared_documents row
   │                   REFUSED when the settlement is an estimate or the rates
   │                   are unverified
   ▼
FILING                 submitted, and the authority returned a reference
                       truth condition: FilingResult::accepted()
                       sets: filed_at, filing_reference
```

A stage is reached by satisfying its own truth condition, never by the previous
one completing. `SettlementModel::stage()` derives the stage from `filed_at` and
`prepared_at` rather than trusting a column, because a stage field that can
disagree with the facts eventually will.

`FilingResult::accepted()` requires a non-empty reference as well as an absent
error. "We got a 200" is the exact failure mode that lets software report
something as filed when it was not.

## Versioning, so history stays reproducible

Three independent axes, all effective-dated and all recorded on every
calculation:

- **Rates** — `config/rates/*.php`, versions with `effective_from`/`_to`.
  Selected by the settled period. A period with no version is refused.
- **Rules** — calculators branch on the rate version's contents, not on
  hard-coded constants, so a rule change is a data change.
- **Schemas** — `SchemaRegistry`, selected by the period being filed, so a
  correction to a 2025 month is prepared under the schema current in 2025.

Each stored settlement keeps the version identifier, the source and the
verification status of every table it used (`pl_settlements.rate_provenance`).
Recomputing an old month from today's tables would quietly rewrite history, so
the stored report is the record and the recomputation is not.
