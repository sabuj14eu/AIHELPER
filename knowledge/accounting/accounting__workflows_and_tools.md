---
title: Accounting application workflows and tools
domain: accounting
repo: sabuj14eu/Accounting-
sources: CLAUDE.md, README.md, composer.json, .github/workflows/ci.yml, docs/DEPLOYMENT.md, docs/DEFINITION_OF_DONE.md, docs/RELEASE_CHECKLIST.md, docs/RATE_VERIFICATION.md, docs/POLAND_TAX_ENGINE.md, docs/AUTOMATION.md, docs/PRODUCTION_AUDIT_2026-09-07.md, docs/SUPPORTED_VERSIONS.md, bin/check-isolation.sh, bin/release-gate.sh, bin/data-safety-drill.sh, bin/install-foundation.sh, bin/deploy-contabo.sh, bin/patch-foundation-index-names.sh, bin/enable-email-verification.sh, deploy/backup.sh, modules/poland/bin/pl-tax, modules/poland/config/poland.php, shop-intelligence/README.md, shop-intelligence/bin/check-shop-isolation.sh
verified_on: 2026-09-16
classification: INTERNAL
---

# Accounting application workflows and tools

## Test and check commands (accounting app)

The accounting app's pre-commit rule (`CLAUDE.md`): run `modules/poland/vendor/bin/phpunit` and `bin/check-isolation.sh` before every commit.

```
# Tax engine only — works anywhere with PHP 8.2+
cd modules/poland && composer install && vendor/bin/phpunit

# From the repo root, via composer scripts (composer.json)
composer test        # cd modules/poland && composer install && vendor/bin/phpunit
composer isolation   # bin/check-isolation.sh
composer report      # modules/poland/bin/pl-tax
composer check       # isolation + test — everything that must pass before a commit

# Isolation guard (4 checks; exit non-zero = "Izolacja naruszona — nie wdrażaj")
bin/check-isolation.sh

# Standalone CLI smoke (also run in CI)
cd modules/poland && ./bin/pl-tax --profile=examples/profile.json --sales-file=examples/sales-2026.json --period=2026-08 --brief
```

`modules/poland/phpunit.xml`: bootstrap `autoload.php`, `failOnWarning="true"`, `failOnRisky="true"`, suite "Poland" over `tests/`. Requires `phpunit/phpunit ^10.5 || ^11.0`.

## Test and check commands (Shop Intelligence)

From `shop-intelligence/` before every commit (`CLAUDE.md`, `shop-intelligence/README.md`):

```
cd shop-intelligence
../modules/poland/vendor/bin/phpunit -c phpunit.xml     # 60 tests / 469 assertions measured 2026-09-07
./bin/check-shop-isolation.sh                            # 10 checks; "ISOLATION PROVEN" expected
php bin/shop-demo                                        # a complete worked month, no DB, no framework
../modules/poland/vendor/bin/phpunit -c phpunit.xml --filter IsolationTest
```

The shop suite borrows the phpunit binary from `modules/poland/vendor`; it has its own `composer.json` (`signalmesh/shop-intelligence`, PHP ^8.2, namespace `Shop\`) and `phpunit.xml`.

## CI (.github/workflows/ci.yml)

Runs on every push and pull request. Jobs: `isolation` (`bin/check-isolation.sh`); `tests` matrix PHP 8.2/8.3/8.4/8.5 (composer install, phpunit, `php -l` over src/config/bin/database, CLI run); `rate-coverage` on PHP 8.4 (`RateRepository::default()->coverage()` for six months ahead, fails on "BRAK"); `laravel-integration` on PHP 8.5 (installs the foundation, configures SQLite, `patch-foundation-index-names.sh --check`, `migrate --force`, asserts `pl_` tables exist, `poland:report`/`poland:verify-rates` registered and run, route `poland.dashboard` registered, and `poland:rate-provenance --todo` exits non-zero — "Unverified rates correctly reported"; if it exits 0 the job fails with "Every rate is marked official. Update docs/OPEN_ITEMS.md and this job").

## Definition of done and the release gate workflow

`docs/DEFINITION_OF_DONE.md` states the conditions with legend DONE / PARTIAL / NOT DONE / BLOCKED, each with proof; nothing is marked done unless it ran. `docs/RELEASE_CHECKLIST.md` is the executable ticklist. `bin/release-gate.sh [/srv/accounting/foundation]` (`PHP_BIN` overridable) runs the mechanical gates and prints PASS / FAIL / HUMAN per gate, exits 1 on any FAIL, and otherwise prints "Mechanical gates passed. Milestone reached: LIVE APPLICATION. NOT reached: PRODUCTION ACCOUNTING ... NOT reached: AUTOMATED FILING". The real-data pilot (gate 12) is always `REQUIRES HUMAN`. Results are recorded in `docs/RELEASE_RECORD_2026-09-07.md`.

To close the remaining open gates (`docs/RELEASE_CHECKLIST.md` "To close the remaining five"):

```
cd /srv/accounting/foundation
php artisan poland:rate-provenance --todo     # the verification worklist
# ... accountant confirms each figure, you set status => 'official' ...
php artisan poland:rate-provenance            # must exit 0
cd /srv/accounting/app && modules/poland/vendor/bin/phpunit
sudo bash bin/data-safety-drill.sh            # must exit 0
# then, and only then: POLAND_REQUIRE_OFFICIAL_RATES=true in .env (the installer already defaults it to true)
```

## Rate-update procedure (data change + test + source)

From `docs/POLAND_TAX_ENGINE.md` "Updating for a new tax year" and `docs/RATE_VERIFICATION.md`:

1. Add a new version to each table in `modules/poland/config/rates/` with `version`, `effective_from`, `effective_to`, the values, `meanings`, and full `provenance` (`status`, `source_document`, `source_url`, `official_source_url`, `published_on`, `checked_on`, `checked_by`, `notes`). Never edit an existing version — a settled month must stay reproducible. Close the previous open-ended version's `effective_to` (an open-ended version may not be followed by another).
2. Run the suite. `RateTableTest` checks each published amount against its own stated formula (e.g. a ryczałt health band is 9% of its stated percentage of the reference wage), catching transcription errors.
3. Add a case to `ZusCalculatorTest` asserting the published headline totals.
4. For official verification, edit the version's `provenance` to `status => 'official'` with `source_url` (where you actually read it), `official_source_url`, `published_on`, `checked_on`, `checked_by` (a person, not a process) and `notes`. `status => 'official'` requires a non-empty `source_url`, enforced in the constructor.
5. When every version is official, `test_the_shipped_tables_are_honest_about_not_being_officially_verified` fails by design — delete it, update `docs/OPEN_ITEMS.md`, and update the CI `laravel-integration` job.
6. Rates can also be published into the application (`php artisan vendor:publish --tag=poland-rates`) with `POLAND_RATES_PATH` pointing at the copy, so a rate update between releases never requires editing code.
7. `php artisan poland:verify-rates` reports how far the tables reach; run it from the scheduler. `config/rates/deadlines.php` public holidays end in 2027 — add years before then.

## Deploy workflow

**One-command install on a fresh Ubuntu/Debian server** (`README.md`, `bin/deploy-contabo.sh`): `curl -fsSL https://raw.githubusercontent.com/sabuj14eu/Accounting-/claude/poland-accounting-app-pijnfm/bin/deploy-contabo.sh | sudo DOMAIN=account.signalmesh.dev bash`. Installs PHP 8.5, MariaDB, Redis, nginx; creates the `accounting` user, database and DB user (plus the `<db>_drill` grant), its own PHP-FPM pool, systemd units, TLS via certbot; migrates; creates an admin account; prints the URL and password. Idempotent. Touches nothing belonging to the trading platform.

**Manual route** (`docs/DEPLOYMENT.md`): `useradd -r -m -d /srv/accounting accounting`; clone to `/srv/accounting/app`; `bin/install-foundation.sh /srv/accounting/foundation`; edit `.env` (DB, Redis indexes, APP_URL); `php artisan key:generate`; `php artisan migrate`; `php artisan poland:verify-rates`; `php artisan poland:rate-provenance --todo`. Create the DB with `GRANT ALL PRIVILEGES ON accounting.* ...` and nothing wider. Copy `deploy/nginx/account.signalmesh.dev.conf`, run certbot, copy `deploy/systemd/accounting-*.service|timer`, `systemctl enable --now accounting-queue.service accounting-scheduler.timer`. Give the app its own PHP-FPM pool (`php8.5-fpm-accounting.sock`).

**Deploy ceremony — backup → migrate → restart → verify, in that order, every time** (`docs/DEPLOYMENT.md`):

```
deploy/backup.sh                                  # backs up AND verifies the restore
cd /srv/accounting/app && git pull
bin/check-isolation.sh                            # must pass before anything else
(cd modules/poland && composer install --no-dev && vendor/bin/phpunit)
cd /srv/accounting/foundation && composer install --no-dev
php artisan migrate --force
php artisan config:cache && php artisan route:cache && php artisan view:cache
sudo systemctl restart php8.5-fpm@accounting accounting-queue.service
php artisan poland:verify-rates
php artisan poland:rate-provenance
tail -n 100 storage/logs/laravel.log
```

Every schema change ships with a note in `docs/CHANGELOG.md` (each phase's entry has a "Schema" table of migrations). Production must have `POLAND_REQUIRE_OFFICIAL_RATES=true`.

**Upgrading the foundation** (`docs/SUPPORTED_VERSIONS.md`): change `FOUNDATION_REF` in `bin/install-foundation.sh`, install into a scratch directory, migrate, run the `laravel-integration` checks, update the versions table with what actually ran and the date. The index-name patch is re-applied automatically by the installer. `bin/enable-email-verification.sh` must also be re-applied after an upgrade if it was used.

**Monitoring that means something** (`docs/DEPLOYMENT.md`): `poland:verify-rates` failing means tables are running out; `poland:rate-provenance` failing under `POLAND_REQUIRE_OFFICIAL_RATES=true` is an intended outage of settlement; growing queue depth means a dead/looping worker; `is_estimate = true` on a month the taxpayer believes complete means a purchase register is missing. An HTTP 200 says the web server is up, not that the numbers are right.

**Backups:** `deploy/backup.sh` (env `DB_DATABASE`, `DB_USERNAME`, `DB_PASSWORD`, optional `DB_HOST`, `BACKUP_DIR=/var/backups/accounting`, `STORAGE_DIR`, `KEEP_DAYS=30`) dumps, restores into `<db>_restore_check`, compares row counts, archives storage; schedule daily and alert on non-zero exit. `bin/data-safety-drill.sh` is the fuller pre-live and monthly drill.

## Month-close and reconciliation workflow (docs/AUTOMATION.md)

Sources KSeF invoices, bank statements (CSV, MT940, camt.053; PDF refused) and government PDFs feed one reconciliation, then the deterministic tax engine computes the report and payment checklist. `MonthCloseService` runs the steps ksef → bank → government → reconciliation → report; a failing step downgrades certainty (worst-case) rather than aborting. Matching is deterministic: MATCHED needs amount to the grosz plus a reference; POSSIBLE needs human approval; NEEDS REVIEW is never booked; a person's decision is never overwritten by a rerun. Nothing is submitted anywhere.

**Before turning KSeF on** (`docs/AUTOMATION.md`, `docs/PRODUCTION_AUDIT_2026-09-07.md` §1 twelve-step checklist): obtain the current official API specification; pin the API version; implement the transport (`KsefClient`) against the CURRENT official API, never from remembered documentation; test authentication, InvoiceRead authorization, retrieval, pagination/cursors, retries/timeouts, duplicate delivery, malformed responses, revoked/expired credentials, API version changes; test against the KSeF test environment first; generate a token with InvoiceRead only; set `KSEF_TRANSPORT=real` and `KSEF_TRANSPORT_ENABLED=true` (AUTOMATION.md's shorter list says `KSEF_ENABLED=true`; `config/poland.php` has both keys); never commit the token; run one sync over a closed month and compare against what the taxpayer knows they bought.

## Tools and technologies (no credentials)

- **PHP**: engine requires 8.2+ (`modules/poland/composer.json` `php: ^8.2`); ERP host requires 8.5 (`#[\Override]` on properties). PHP 8.5.0 was built from source for the release record.
- **Composer 2**: root `composer.json` mounts `modules/poland` as a path repository with symlink; module is `signalmesh/poland-accounting`, type library, MIT.
- **Laravel / Liberu ERP**: `liberusoftware/accounting-erp-laravel` pinned at `3a23437`; Laravel 13.29.0, Filament v5.7.6, Livewire v4.4.3. Provides the double-entry ledger, invoicing, banking, reporting and login (Fortify). Not vendored.
- **PHPUnit** 10.5/11 with fail-on-warning/risky.
- **MariaDB 10.11.14** (production; MySQL 8 or MariaDB 10.6+ per DEPLOYMENT), SQLite in CI. `mysqldump`/`mysql` used by backup and drill.
- **Redis** for queue, cache, session (own DB indexes 3 and 4 by default).
- **nginx** with a dedicated server block and dedicated PHP-FPM pool; **certbot** for TLS.
- **systemd** units `accounting-queue.service`, `accounting-scheduler.service`, `accounting-scheduler.timer`.
- **Node 20+** listed in DEPLOYMENT requirements for asset build.
- **PHP extensions**: ERP host mbstring, intl, dom, xml, xsl (JPK/KSeF schema validation), pdo_mysql, redis, zip, gd, bcmath, curl, openssl; engine alone mbstring.
- **KSeF (Krajowy System e-Faktur) concepts**: environments test/production (`KSEF_ENVIRONMENT`), base URL is configuration never a constant (`KSEF_BASE_URL`), NIP (`KSEF_NIP`), a token the taxpayer generates for this application and can revoke (never the KSeF password), scope InvoiceRead only, FA(1)/(2)/(3) invoice XML schemas, incremental sync with high-water mark and cursor, unique `ksef_number`. Transport is DISABLED until a client exists; `ksef.mf.gov.pl` was unreachable from the build environment. No token values exist in the repo; `.env.example` `KSEF_TOKEN=` is blank.
- **JPK** (JPK_V7M monthly / JPK_V7K quarterly) and **NBP** exchange rates (table A, `NBP_BASE_URL`) are Phase 4 / Phase 2 concepts with refusing adapters only.
- **OCR / text extraction**: no tesseract/pdftotext in the build environment; `TextExtractor` port refuses.
- **Git / GitHub**: repo `sabuj14eu/Accounting-`, working branch `claude/poland-accounting-app-pijnfm`.

## Everyday operator commands

```
php artisan poland:report 2026-08 --sales=22150        # settle a month from the CLI inside the ERP
php artisan poland:verify-rates [--months=3]           # how far the rate tables reach
php artisan poland:rate-provenance [--todo]            # verification worklist; exit 0 only when all official
php artisan vendor:publish --tag=poland-rates          # publish rate tables for out-of-release updates
sudo bash bin/data-safety-drill.sh [/srv/accounting/foundation]
bin/patch-foundation-index-names.sh [/srv/accounting/foundation] [--check]
sudo bash bin/enable-email-verification.sh [/srv/accounting/foundation]
systemctl restart php8.5-fpm@accounting accounting-queue.service   # accounting only; trading never notices
```

Web surface after deploy (`bin/deploy-contabo.sh` final output): `https://account.signalmesh.dev/poland` ("co muszę zapłacić" dashboard), `/login`, `/register`, `/forgot-password`.
