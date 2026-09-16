---
title: Accounting open items
domain: accounting
repo: sabuj14eu/Accounting-
sources: docs/OPEN_ITEMS.md
verified_on: 2026-09-16
commit: 1e3e897
classification: INTERNAL
---

# Open items

Deferred work for the accounting application. An item deferred in conversation
is an item forgotten — if it is not here, it does not exist. Delete an entry
only when it is done and verified, and say where the proof is.

---

## P0 — must be settled before real accounting use

### The rate tables have not been verified against official sources
Every version in `modules/poland/config/rates/` is marked `secondary`: taken
from competent Polish accounting publications and cross-checked arithmetically
against its own stated formula. That catches transcription errors. It cannot
catch a wrong source.

Attempting the verification from the build environment is **impossible**, not
merely undone: zus.pl, gov.pl, isap.sejm.gov.pl, stat.gov.pl and api.nbp.pl are
all refused by the network egress policy (403 on CONNECT). It needs a human with
network access.

The software now refuses to hide this. Every report names the unverified tables
and lists them as a blocker to filing; `POLAND_REQUIRE_OFFICIAL_RATES=true`
makes the engine throw rather than settle; and preparation refuses to build a
document from a settlement that is not fit for filing.

Run `php artisan poland:rate-provenance --todo` for the worklist with the exact
URL for each figure. Procedure in `docs/RATE_VERIFICATION.md`.

Most critical single item: **whether the 2026 health-contribution reform (9% of
75% of the minimum wage) really did not take effect.** The secondary sources say
it was vetoed. If they are wrong, every 2026 health figure in the system is
wrong.

**Owner: the taxpayer's accountant. Proof required: `status => 'official'` with
a source URL on every version, plus the note here deleted.**

### Which ryczałt rate applies has not been determined
`examples/profile.json` ships 3% (trade in goods) as an example, not as advice.
The rate depends on what the business actually does under art. 12, a shop
selling goods and providing services may fall under two rates at once, and
choosing wrong changes the tax by multiples. The engine supports several rates
per taxpayer; the profile currently carries one.
**Blocked on: the taxpayer confirming their PKD activity and rate(s).**

### No cost register, so only ryczałt is exact
For the scale and the flat tax the engine can only bound PIT from above. This is
reported, not hidden, but it means those two regimes are not yet usable for a
real filing from cash-register data alone. Phase 2 (KPiR) closes it.

---

## P1 — needed for a complete Phase 1

### Polish chart of accounts and company defaults not configured
The Liberu foundation ships its own chart of accounts. Polish account numbering,
VAT registers and document types have not been configured. The foundation itself
now boots and migrates — see `docs/SUPPORTED_VERSIONS.md` — so this is
configuration work, not a runtime unknown.

### KSeF HTTP transport is not implemented
`ksef.mf.gov.pl`, `ksef-test.mf.gov.pl` and every variant are refused by the
build environment's network policy, so no client could be written against the
real API or tested against it. Writing one from remembered documentation would
produce something that looks finished and fails on first contact.

Everything around it IS built and executed: the FA parser, dedup, incremental
cursor, immutable XML, encrypted InvoiceRead-only tokens, REQUIRES REVIEW
propagation. `UnconfiguredKsefClient` refuses until a transport exists.
**Next step: implement `KsefClient` against the current official API, verified
at source, and test against the KSeF test environment.** See `docs/AUTOMATION.md`.

### No OCR or PDF text extraction
No `tesseract`, no `pdftotext` in the environment. `UnavailableTextExtractor`
refuses, and `PdfStatementParser` refuses with a route forward (CSV/MT940/camt).
Government PDFs are stored and marked for manual review rather than silently
classified as "information only".
**Next step: install a text-extraction toolchain on the server and implement the
`TextExtractor` port.**

### No KSeF or JPK schema version is registered
`SchemaRegistry` selects a schema by the period being filed and refuses periods
it has no version for, and `PreparedDocument` treats "could not be validated" as
distinct from "valid". No actual XSD is registered, so no document can be
prepared yet. Phase 3/4.

### Filing is not implemented for any channel
`UnconfiguredSubmitter` is bound for every channel and throws. That is
deliberate: the filing stage exists in the model, and the honest state of it is
that nothing is sent anywhere. A taxpayer files themselves and records the
reference through `markFiled()`.

### No exchange-rate adapter
`UnavailableExchangeRateProvider` refuses rather than defaulting. A missing rate
is not 1.0 and is not yesterday's rate. NBP adapter is Phase 2.

### Backup and restore have not been drilled on a real database
`bin/data-safety-drill.sh` and `deploy/backup.sh` are written and
syntax-checked, but this environment has no MariaDB server, so neither has ever
restored anything. **Run the drill on the Contabo box before going live** — it
must exit 0.

### Multi-rate ryczałt is supported by the engine but not by data entry
`FiscalSalesReport` lines carry an optional per-line ryczałt rate and
`PitCalculator` apportions deductions proportionally (tested). The dashboard and
the CLI only accept one rate. Fine for a single-activity business; wrong for a
mixed one.

### Quarterly VAT (JPK_V7K) is modelled but not settled quarterly
The profile carries the frequency and the report names the right structure, but
settlement is monthly throughout. A quarterly taxpayer would need the VAT part
aggregated over the quarter.

---

## P2 — known limitations, acceptable for now

### Suspension and sickness do not shorten a month
Only an incomplete FIRST month prorates social contributions. A business
suspension or a sickness period also reduces the base, but the engine is not
told about them, so it computes a full month and the report states that
assumption rather than pretending to know.

### Mały ZUS Plus base is supplied, not derived
The base depends on the previous year's income and the 36-in-60-months
entitlement limit depends on the taxpayer's own history. Both are configured and
validated against the statutory bounds; neither is computed.

### The public holiday calendar ends in 2027
`config/rates/deadlines.php` carries 2025–2027. Beyond that the report returns
the statutory date and says the working-day shift could not be applied. Add years
before then.

### Annual reconciliation of the health contribution is warned about, not computed
Crossing a ryczałt revenue band mid-year creates a top-up at year end. The report
warns; it does not calculate the annual settlement. That belongs with the annual
return (PIT-28), which is not built.

---

### Three bugs were found by executing the Laravel layer, and fixed
Recorded because they are the argument for the integration job in CI:
1. `RateProvenance` constructor parameters were declared in a different order
   than `fromArray()` passed them positionally. Fixed, and the call now uses
   named arguments so it cannot recur; pinned by
   `test_provenance_fields_are_read_in_the_right_order`.
2. A sales correction inserted the new report before superseding the old one,
   violating the unique index that makes duplicate months impossible. Order was
   load-bearing and is now commented as such.
3. The dashboard view assumed `$errors` is always bound, which is only true
   inside the `web` middleware group. Guarded.

None of these were visible to `php -l`, and none were visible to the engine's
own test suite.

## Shop Profit Intelligence — not built yet

The analysis core in `shop-intelligence/` is built and tested (60 tests, 469
assertions, 0 failures). Everything around it is not, and the list is short
enough to be honest about:

1. No user interface — the three pages exist as a design in
   `shop-intelligence/docs/BANKING_UX.md` and as a text renderer, nothing else.
2. No database, no migrations, nothing persists.
3. No authentication, no users, no sessions. `.env.example` describes them.
4. No importers: bank statement, card terminal, Glovo, Uber Eats, supplier
   invoices, OCR — all currently a human typing figures into a constructor.
5. No month close and no immutable snapshot. The rule is written down; there is
   no table to enforce it in.
6. Not deployed: no database created, no vhost, no systemd unit, no backup.
7. **The 27 regression tests were derived from the specification body, not
   transcribed from its §29 list.** Somebody must read §29 line by line against
   `shop-intelligence/docs/REGRESSION_MAP.md` and report what is missing.
   Overlap is not coverage.

Every threshold in it is invented — target margin, stock tolerance, revenue and
cost alert levels, the payout tolerance, the three-period baseline minimum. None
came from this shop's data. `shop-intelligence/docs/` and
`docs/FABLE_BRIEFING_2026-09-08.md` §5 list where I am most likely wrong.

**Owner: whoever picks up the briefing. Proof required: a deployed application
with its own database and its own login, and the §29 reconciliation written
down.**

## Deliberately not done

### The SignalMesh navigation link (Phase 6)
Not applied. The instruction was to start with Phase 1, and the trading platform
is not modified without a reason and a deliberate decision.
`docs/SIGNALMESH_NAV_LINK.md` has the exact change.

### Single sign-on with the trading platform
Phase 1 has its own login by design. SSO would be a deliberate OAuth/OIDC
integration between two applications that stay separate — never a shared session
store, which would turn an outage of either into an outage of both.
