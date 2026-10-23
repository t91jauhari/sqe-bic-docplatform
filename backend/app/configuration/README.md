# Configuration storage — first implementation slice

`store.py` introduces separate publication and entry tables. It does not modify
the live Config model, startup, API, extraction, or case pins. The first migration
has been rehearsed only on the isolated restored database. Schema-specific entity tables and typed business policies remain
future work; this lossless layer is their compatibility foundation.

The caller owns transactions. Imports are organization/revision scoped and
idempotent, reject changed content for an existing revision, and verify a
deterministic digest on reconstruction. Unknown top-level properties remain in
extensions. Do not treat this API-level protection as database-enforced
immutability: database constraints/triggers and publication authorization are
required before runtime activation.

Tests use isolated SQLite and synthetic values, plus application default payload
round trips. All 40 restored historical configurations also passed PostgreSQL
import and reconstruction. Next gate: typed section contracts and configurable
identity bindings, followed by read-only shadow evaluation.

## Explicit schema migration

Set `REFACTOR_DATABASE_URL` through the process environment. Run:

```text
python -m app.configuration.migrate --expected-database sqe_refactor
```

The command requires the actual database name to match the explicit target,
serializes migration execution, checks applied file checksums and runs DDL plus
the journal update in one transaction. It is never called by application startup.
Migration checksums normalize line endings across Windows and Linux.

The isolated rehearsal uses `app.configuration.verify_postgres` with the same
target argument. It imports history twice and fingerprints original configuration
and case rows before/after. No report or extraction is activated.

Rollback at this additive stage means retaining the old application and leaving
the unused new tables in place. No destructive downgrade command is provided.
Trusted migration files execute as parameter-free PostgreSQL scripts in the same
transaction; PostgreSQL parses procedural bodies and quoted semicolons.

Migration 0002 adds dedicated identity policy/binding tables. New imports validate
identity paths before writing. Compatibility reconstruction preserves explicit
empty bindings and detects tampering through the publication digest. The read-only
shadow command verified 67 restored cases with no changes in findings. Dedicated
UI editing, remaining business-policy tables and activation are still pending.

Migration 0003 adds family rule scopes and ordered memberships. New imports remove
`rule_scope` from extension JSON and reconstruct it from those rows. Imports
validate registered families and rule IDs first; publication integrity checks
detect deleted memberships. Historical imports without scope remain untouched.

`shadow_comparisons` verifies the supported plain-text match subset against the
existing evaluator on restored extraction values. It reports skipped cases/rules
explicitly; zero differences in that subset does not certify complex SOP logic.

Migration0004 prevents UPDATE, DELETE and TRUNCATE on normalized revision tables,
and on the legacy configurations table when present in the target schema.
Child rows may be inserted only in the same transaction that created their
publication. A transaction-ID column enforces that boundary. Existing revisions
remain readable and repeated imports do not rewrite them. SQLite test metadata
does not install these PostgreSQL triggers. A database owner can disable schema
protections; deployment must restrict schema-changing privileges to migrations.
Rollback to the legacy application remains possible because new legacy Config
inserts are allowed. Before returning from legacy-only writes to verified reads,
import any additional legacy revisions explicitly and verify parity again.

Migration0005 adds ordered context definitions. The contexts module validates typed enum/text/digits/document-reference fields and family/profile scope. Missing definitions use context_defaults_v1 compatibility input without persisting it; explicit empty disables contexts. New bootstrap snapshots include definitions explicitly. Settings edits stay in a draft until publication. The case catalog and annotation API use the pinned configuration. Native profile catalog, remaining complex SOP policies and report/dataset contracts remain migration work.

Custom profiles use validation_adapter=schema and an explicit inline schema. Supported structural keywords are type/properties/required/items/enum/description/additionalProperties; arrays require item schemas. Business constraints belong in SOP policies. Native profiles retain packaged validation adapters and existing compatibility definitions. Custom profiles do not use built-in fixture files. Profile/schema/prompt definitions persist in existing per-profile publication entries.
