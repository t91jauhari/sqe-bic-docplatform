# Operational local preview

This is a separate local development stack, not the original application or a
production deployment. It uses the accepted backend image, a persistent Docker
volume for SQLite, API8100 and the standalone frontend3100. Existing MinIO and
Temporal instances can be reused with a dedicated private bucket/IAM user and
Temporal namespace/task queue. The worker has an explicit `processing` profile.
It must never poll the original application namespace or queue.

Before first start, stop intake, back up the current preview SQLite database and
source files, and copy them into the new preview-state volume with ownership for
UID10001. Preserve APP_SECRET so connector encryption and sessions remain valid.
Verify configuration version, document count and source hashes after copying.
Startup does not initialize, migrate or publish business configuration.

The packaged image intentionally contains empty public dataset examples. Preserve
authorized private reference data by explicitly registering the existing bundled
datasets in the isolated database before enabling DATASET_READ_MODE=registry.
Never replace private references with those empty examples during cutover.
Private environment/backup/reference files stay outside the source checkout.

Supply these values outside Git: PREVIEW_APP_SECRET, REFACTOR_BACKEND_IMAGE,
SHARED_INFRA_NETWORK, PREVIEW_MINIO_ENDPOINT, PREVIEW_MINIO_ACCESS_KEY,
PREVIEW_MINIO_SECRET_KEY, PREVIEW_MINIO_BUCKET, PREVIEW_TEMPORAL_ADDRESS,
PREVIEW_TEMPORAL_NAMESPACE and PREVIEW_TEMPORAL_TASK_QUEUE. Provision the bucket
and namespace before starting. Grant bucket list/location and object read/write/
delete only for that bucket; verify the credential cannot access original storage.
Keep queue and namespace separate to prevent incompatible workers taking jobs.
The local shared services use HTTP; production requires appropriate TLS settings.

Before switching from local files, stop only preview workers/API, back up the
preview database and environment, copy each referenced object to the new bucket,
and verify SHA-256 after reading every object back. Retain local recovery files.
Preserve APP_SECRET, database, configuration pins and provider receipts. Restart
only the preview stack and verify both workflow types, object reads and exports.

Supply the private environment file and run:

```text
docker compose -f compose.preview.yaml up -d api
docker compose -f compose.preview.yaml --profile processing up -d
```

Use `--env-file /private/preview.env` before `-f` when reading the secret from a
private environment file. Keep the pre-cutover container stopped until acceptance; do not restart it while
the new API owns port8100. After acceptance it may be removed if verified database
and file backups are retained. The initial obsolete preview container was removed
after acceptance; rollback requires recreating an API from its retained backup.

Enable processing only after configuring the authorized provider connection and
checking its saved model ID. An upload otherwise creates a queued job without a
worker, or fails extraction without credentials. User uploads to the operational
preview will use that provider's limits and billing. Do not submit a real document
merely to test infrastructure without the user's processing authorization.

For acceptance, use an authorized document through the browser: upload/grouping,
classification, extraction, evidence crops, SOP results, required visual review
and report/export. Keep model extraction quality distinct from application job
completion. Record failures and actual paid request counts honestly.

Rollback: stop the new API/worker, preserve their volume, then restore the earlier
preview API on8100 with its retained state. Never run two workers against the
same preview database. Shared service instances are supported; original database,
bucket, namespace and queue remain outside this preview's scope.
SQLite is for this bounded local test; production continues to require PostgreSQL,
object storage and Temporal through compose.production.yaml.
