---
title: Accounting application overview
domain: accounting
repo: sabuj14eu/Accounting-
sources: CLAUDE.md, README.md, docs/ARCHITECTURE.md, docs/ISOLATION.md, docs/SIGNALMESH_NAV_LINK.md, docs/FABLE_BRIEFING_2026-09-08.md, shop-intelligence/README.md, shop-intelligence/docs/ISOLATION.md, composer.json, .env.example, bin/deploy-contabo.sh
verified_on: 2026-09-16
classification: INTERNAL
---

# Accounting application (sabuj14eu/Accounting-) — overview

## What the Accounting- repository is

The Accounting- repository (GitHub `sabuj14eu/Accounting-`) is Shyam's **Polish JDG accounting application**, served at `account.signalmesh.dev`. JDG means "jednoosobowa działalność gospodarcza", a Polish sole-trader business. The application is built on the Liberu accounting ERP (`liberusoftware/accounting-erp-laravel`, a Laravel application) and extended with a standalone **Poland tax and compliance layer** in `modules/poland/` that computes VAT, ZUS and PIT for one sole trader from a monthly cash-register total. It is a completely separate application from the SignalMesh trading platform (`Sniper-System`, `brother-brain-v2`, `brother_sniper_v7`). Source: `CLAUDE.md`, `README.md`.

The repository also carries a **second, separate application**, `shop-intelligence/` ("Shop Profit Intelligence"): a management analysis tool for a food shop covering money reconciliation, stock and food cost, and real profit. It is NOT the accounting service and the two share nothing — no database, no table, no session, no credential, no code, no network path. Source: `CLAUDE.md` section "THE SECOND APPLICATION", `shop-intelligence/README.md`.

All eight commits in the repository are dated 2026-09-07 and live on branch `claude/poland-accounting-app-pijnfm` (per `docs/RELEASE_RECORD_2026-09-07.md` and `bin/deploy-contabo.sh` `BRANCH` default). Source: `git log`.

## The one-number workflow the accounting app was built for

The Accounting app answers the owner's question quoted in `README.md`: "I only give my sales report amount — the kasa fiskalna amount. Then give me a report of how much I need to pay: ZUS, VAT, PIT." The standalone CLI demonstrates it:

```
cd modules/poland
./bin/pl-tax --profile=examples/profile.json --sales=2026-08:22150
```

which prints a Polish monthly settlement ("ROZLICZENIE MIESIĘCZNE") listing ZUS, VAT, ryczałt PIT, the total, the deadlines (shifted off weekends/holidays) and what remains of the sales. The tax engine needs only PHP 8.2+, no database, no framework, no queue, so an answer is available even when the web application is down. Inside the ERP the same engine backs a web dashboard at `/poland` and `php artisan poland:report 2026-08 --sales=22150`. Source: `README.md`.

## Hostnames and the SignalMesh relationship (hyperlink only)

The Accounting app is served at **`account.signalmesh.dev`**. The trading platform is at `app.signalmesh.dev`. The ONLY permitted relationship is a hyperlink FROM SignalMesh TO the accounting app: a navigation item labelled "Accounts" pointing at `https://account.signalmesh.dev` with `target="_blank" rel="noopener noreferrer"`. That link belongs to Phase 6 and has deliberately NOT been applied; `docs/SIGNALMESH_NAV_LINK.md` records the exact change and forbids adding any accounting table to the trading DB, any cross-database read, any session/token/user id in the URL, any cross-side health check, and any import of accounting code into the trading platform. `bin/check-isolation.sh` enforces isolation mechanically before every deploy and in CI. Source: `docs/ISOLATION.md`, `docs/SIGNALMESH_NAV_LINK.md`.

Shop Intelligence's own `.env.example` names `APP_URL=https://shop.signalmesh.dev` with its own session cookie `shop_intelligence_session` and database `shop_intelligence`; that deployment is NOT yet executed (no vhost, no unit, no database created). Source: `shop-intelligence/.env.example`, `shop-intelligence/docs/ISOLATION.md`.

## What the accounting app shares with trading: nothing

Per `docs/ISOLATION.md`, the accounting app has its own host (`account.signalmesh.dev`), codebase (this repo), application root (`/srv/accounting/foundation`), database (`accounting`, own user), queue and cache (own Redis DB indexes, `.env.example` suggests `REDIS_DB=3`, `REDIS_CACHE_DB=4`), PHP-FPM pool (`php8.5-fpm-accounting.sock`), systemd workers (`accounting-queue.service`), storage tree, user accounts and `.env`. The two applications share only the operating system and optionally the database server process. The accounting app must never receive MT5 logins, broker credentials, bot API secrets or executor tokens, trading risk configuration, trading DB credentials, or signal payloads/dispatches/decisions. There is no code path that would consume any of them.

## What Shop Intelligence shares with the accounting app: nothing

Shop Intelligence (`shop-intelligence/`, PHP namespace `Shop\`) has its own database `shop_intelligence`, tables `shop_*`, migrations, users/login, session cookie on `shop.signalmesh.dev`, storage root `SHOP_STORAGE_ROOT`, queues, and audit records. It holds no KSeF token or filing credential at all. The only route between them is `Shop\Comparison\AccountsSnapshot`, a container somebody fills by hand with figures exported from the accounting app, recorded with who imported it, when, and from what; `AccountsComparison` compares and reports differences and has no write-shaped method (asserted by a test). Isolation is proven by `shop-intelligence/bin/check-shop-isolation.sh` (10 checks, 0 violations measured 2026-09-07) and by `IsolationTest`. Source: `shop-intelligence/docs/ISOLATION.md`.

## Repository layout of Accounting-

From `README.md` and directory listing:

- `CLAUDE.md` — the constitution: ten iron rules, hidden tax-code rules, shop-intelligence laws.
- `README.md` — what works, deploy one-liner, release gate, audit, layout, status.
- `composer.json` — root project `signalmesh/accounting`; scripts `test`, `isolation`, `report`, `check` (isolation + test).
- `.env.example` — accounting app environment template; explicitly must never contain a trading credential. Values are blank.
- `.github/workflows/ci.yml` — jobs: `isolation`, `tests` (PHP 8.2–8.5 matrix), `rate-coverage` (six months ahead), `laravel-integration` (installs the ERP on PHP 8.5, migrates on SQLite, checks tables/commands/routes, asserts unverified rates are reported).
- `modules/poland/` — the Poland tax layer, a standalone Composer package `signalmesh/poland-accounting` (PHP ^8.2, namespace `Poland\`).
  - `config/rates/` — versioned, effective-dated rate tables with sources (`zus_social.php`, `zus_health.php`, `pit.php`, `vat.php`, `deadlines.php`).
  - `config/poland.php` — module config (rates path, `require_official_rates`, routes, KSeF gate, reconciliation).
  - `src/Domain/`, `src/Rates/`, `src/Calculators/`, `src/Reporting/` — framework-free engine.
  - `src/Laravel/` — service provider, Eloquent models, controllers, artisan commands, services.
  - `src/Ksef/`, `src/Banking/`, `src/Government/`, `src/Reconciliation/`, `src/Interpretation/`, `src/Certainty/`, `src/Contracts/`, `src/Adapters/Null/` — automation layer and refusing adapters.
  - `bin/pl-tax` — standalone CLI; `examples/profile.json`, `examples/sales-2026.json`.
  - `database/migrations/` — 12 migrations, all tables prefixed `pl_`.
  - `resources/views/` — `dashboard.blade.php`, `report.blade.php`, `history.blade.php`; `routes/web.php`.
  - `tests/Unit`, `tests/Feature`, `tests/Fixtures` (FA XML, MT940, camt.053, mBank CSV).
- `bin/` — `deploy-contabo.sh` (one-shot install), `install-foundation.sh` (installs pinned Liberu, mounts module), `check-isolation.sh`, `release-gate.sh`, `data-safety-drill.sh`, `enable-email-verification.sh`, `patch-foundation-index-names.sh` (+ `bin/support/fix-index-names.php`).
- `deploy/` — `nginx/account.signalmesh.dev.conf`, `systemd/accounting-queue.service`, `accounting-scheduler.service`, `accounting-scheduler.timer`, `backup.sh`.
- `docs/` — ARCHITECTURE, POLAND_TAX_ENGINE, ISOLATION, RATE_VERIFICATION, AUTOMATION, DEFINITION_OF_DONE, RELEASE_CHECKLIST, RELEASE_RECORD_2026-09-07, PRODUCTION_AUDIT_2026-09-07, FABLE_BRIEFING_2026-09-08, ROADMAP, OPEN_ITEMS, CHANGELOG, DEPLOYMENT, SUPPORTED_VERSIONS, SIGNALMESH_NAV_LINK.
- `shop-intelligence/` — the second application (namespace `Shop\`): `src/` (Ai, Cash, Comparison, Costs, Inventory, Money, Monitoring, Platforms, Pricing, Profit, Reporting, Truth), `tests/` (7 files), `bin/check-shop-isolation.sh`, `bin/shop-demo`, `docs/BANKING_UX.md`, `docs/ISOLATION.md`, `docs/REGRESSION_MAP.md`, own `composer.json`, `phpunit.xml`, `.env.example`.

## Why the Liberu foundation is installed, not vendored

The accounting app installs the Liberu ERP rather than forking it: upstream is 7 141 files and 45 MB across 466 modules. `bin/install-foundation.sh` pins upstream by commit (`FOUNDATION_REF=3a23437a432c74637aca56bb0daed27430d481ee`, verified installable 2026-09-07) and mounts `modules/poland` as a Composer path repository — the same mechanism upstream uses for its own modules. Upgrading is a one-line change to `FOUNDATION_REF` plus a test run. The trade-off: a deploy needs network access to GitHub and Packagist. The installed foundation lives in `/foundation/` (gitignored) or `/srv/accounting/foundation` in production. Source: `docs/ARCHITECTURE.md`, `bin/install-foundation.sh`.

## Status and milestones (as of the 2026-09-07 release record)

Three milestones are kept separate in `docs/RELEASE_RECORD_2026-09-07.md`:
- **LIVE APPLICATION** — REACHED (deployed and usable: login, accounting data, documents, bank statement import in CSV/MT940/camt.053, monthly reports, payment checklist, audit trail, backup and restore).
- **PRODUCTION ACCOUNTING** — NOT REACHED: needs official rate verification (the P0) and the real-data pilot (release gate 12, `REQUIRES HUMAN`).
- **AUTOMATED FILING** — NOT REACHED and deliberately disabled: every filing channel is bound to `UnconfiguredSubmitter`, which throws, and `FilingChannel::automated()` is false for all channels by test.

Shop Intelligence is at none of these: its analysis core is built and tested (60 tests, 469 assertions, 0 failures, PHP 8.4.19) but it has no UI, no database, no authentication, no importers and is not deployed. Source: `docs/FABLE_BRIEFING_2026-09-08.md`, `docs/OPEN_ITEMS.md`.

The accounting suite measured at the release gate: 309 tests, 874 assertions, 0 failures, on PHP 8.4.19 and 8.5.0; Laravel 13.29.0; MariaDB 10.11.14; 295 migrations. Source: `docs/RELEASE_RECORD_2026-09-07.md`.

## The governing principle

`docs/PRODUCTION_AUDIT_2026-09-07.md` states the governing principle of the accounting app: **"Missing data is not zero data."** An empty KSeF result, an empty OCR result, a missing bank statement and unavailable government document text all throw; none is read as evidence that nothing exists. `CLAUDE.md` rule 5 says the same as "ABSENCE IS NOT ZERO", and the shop app encodes it as `Total::of([])` being NO DATA rather than ACTUAL zero.

## Where to read next

Reading order recommended by `docs/FABLE_BRIEFING_2026-09-08.md`: `CLAUDE.md` → `docs/FABLE_BRIEFING_2026-09-08.md` → `shop-intelligence/README.md` → `shop-intelligence/docs/BANKING_UX.md` → `shop-intelligence/docs/ISOLATION.md` → `shop-intelligence/docs/REGRESSION_MAP.md` → `docs/OPEN_ITEMS.md`. For the accounting engine itself: `docs/POLAND_TAX_ENGINE.md`, `docs/ARCHITECTURE.md`, `docs/RATE_VERIFICATION.md`.
