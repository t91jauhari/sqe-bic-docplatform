# Release and rollback procedure

The isolated refactor is not the running release. Record the accepted source commit,
backend/frontend image digests, environment settings, migration checksums, and test
results together before scheduling activation. `compose.production.yaml` uses
external PostgreSQL, object storage over TLS, and Temporal. It does not provision
or replace these services. Put an HTTPS reverse proxy in front of its loopback web
port. Keep secrets outside Git and retain the existing APP_SECRET so stored
connector credentials remain decryptable.

## Before activation

1. Complete the acceptance gates in PLAN.md, including browser checks. Prepare
   images from the clean public source export, not from the private Git history.
2. Record running image digests and the current runtime settings for rollback.
3. Pause new uploads, drain current work, then stop the old workers. Record any
   uncertain provider submissions and their receipts; do not resubmit them.
4. Capture a PostgreSQL archive and an object-storage snapshot from this same
   quiescent period. Record SHA-256 hashes, object counts, and timestamps.
5. Restore both into an isolated environment. Verify case counts, configuration
   pins, encrypted credentials, representative source objects, reports, and job
   receipts. The earlier baseline archives prove the restore procedure; their
   different capture times do not constitute a coordinated cutover backup.

## Configuration rollout

1. Set REFACTOR_DATABASE_URL explicitly and run
   `python -m app.configuration.migrate --expected-database <database>`.
   The command rejects a different target and changed migration checksums.
2. Use the explicit import/verification commands documented in MIGRATIONS.md.
   Import every historical configuration and authorized reference dataset before
   enabling normalized or registry reads. Preserve case pins and original JSON.
3. Start the API with legacy reads/writes first. API startup does not publish
   business settings or apply migrations. Check health and authenticated reads.
4. After import parity is verified, enable dual writes with verified reads in a
   separate release setting. Move to normalized reads only after parity passes.
   Enable dataset registry reads only after all required immutable IDs exist.
5. Start the new worker on its explicitly selected queue. Existing Llama cases
   remain historical: publish Spider settings and explicitly upgrade selected
   cases before requesting new extraction. Cached output may still be reviewed.
6. Verify one authorized synthetic case through upload, grouping, classification,
   extraction, field retry, SOP review, report view, and export. Record provider
   request IDs and outcomes. Then restore uploads and monitor failed jobs.

## Rollback

Stop new workers before starting old workers. Return traffic to the recorded old
images with legacy configuration reads/writes. The additive configuration tables
can remain; do not drop historical rows or migration records. Dual publication
writes retain legacy Config rows for this purpose. Verify the old API and pinned
case reads before restoring uploads. If operational data was corrupted rather
than merely a release defect, restore the coordinated database/object backups
together during downtime and reconcile post-backup provider receipts before any
retry. Never blindly replay paid submissions after a restore.

No activation is recorded until these steps have actually run against the chosen
deployment target. A generated compose file or a successful build is not a
completed cutover.
