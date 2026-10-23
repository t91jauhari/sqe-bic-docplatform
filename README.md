# SQE Document Platform

Python/FastAPI document processing, configurable document profiles, SOP controls,
audited review and Kertas Kerja reports, with a Next.js interface.

Refactoring is in progress. Native compatibility and remaining API services,
browser acceptance, and deployment activation are still tracked separately.
This snapshot is not a completed production release.

This source export deliberately omits customer documents, extraction fixtures,
reference workbook values, browser screenshots, secrets and previous Git history.
Included dataset examples are empty synthetic references. Import authorized
private reference JSON separately; never commit operational data or `.env`.
After migration, `app.configuration.import_datasets --expected-database NAME
--organization ORG --reference-file /private/reference.json` imports an authorized
reference without copying it into the source tree. Supply the database URL through
`REFACTOR_DATABASE_URL`. Existing IDs are immutable; replacements need a new ID.

## Local development

Run `python scripts/init_dev.py` once to generate local credentials. Build and
start the infrastructure/API with Docker Compose, then explicitly initialize
the development database using `python -m app.configuration.initialize
--expected-database sqe` inside the API container before starting workers.
Configure a real provider through Configuration; operational extraction fixtures
are not distributed in this repository.

## Controlled upgrade

Keep the existing application and verified database/object backups available.
Apply configuration migrations explicitly against an explicitly named database;
import configuration history and reference datasets before enabling verified or
normalized configuration reads. Business configuration is never published at
startup. `CONFIGURATION_STORAGE_MODE=legacy` and `DATASET_READ_MODE=bundled` are
compatibility defaults; activate new storage modes only after rehearsal.

Production deployment requires environment-specific secrets, TLS, PostgreSQL,
object storage and Temporal. This source export is not evidence of a completed
production cutover. Existing case configuration pins must be preserved.
Use compose.production.yaml and docs/refactor/ROLLOUT.md for release preparation.
