"""Create local development settings once; never overwrite an existing .env."""

import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
target = ROOT / ".env"
if target.exists():
    # Add infrastructure keys on upgrade without replacing existing values/secrets.
    existing = target.read_text(encoding="utf-8")
    defaults = {
        "STORAGE_DRIVER": "minio",
        "MINIO_ENDPOINT": "localhost:9000",
        "MINIO_ACCESS_KEY": "sqe-dev",
        "MINIO_SECRET_KEY": secrets.token_urlsafe(32),
        "MINIO_BUCKET": "sqe-documents",
        "MINIO_SECURE": "false",
        "MINIO_REGION": "us-east-1",
    }
    present = {
        line.split("=", 1)[0].strip() for line in existing.splitlines() if "=" in line
    }
    additions = [k + "=" + v for k, v in defaults.items() if k not in present]
    if additions:
        target.write_text(
            existing.rstrip() + "\n" + "\n".join(additions) + "\n", encoding="utf-8"
        )
    print("Existing settings retained; missing MinIO settings added.")
else:
    values = [
        "APP_ENV=development",
        "STORAGE_DRIVER=minio",
        "MINIO_ENDPOINT=localhost:9000",
        "MINIO_ACCESS_KEY=sqe-dev",
        "MINIO_SECRET_KEY=" + secrets.token_urlsafe(32),
        "MINIO_BUCKET=sqe-documents",
        "MINIO_SECURE=false",
        "MINIO_REGION=us-east-1",
        "APP_SECRET=" + secrets.token_urlsafe(48),
        "DEV_ORGANIZATION=sqe",
        "DEV_EMAIL=sqe@bic.local",
        "DEV_PASSWORD=P@ssw0rd2026",
        "POSTGRES_PASSWORD=" + secrets.token_urlsafe(32),
        "SECURE_COOKIE=false",
        "WORKFLOW_DRIVER=local",
        "WORKER_CONCURRENCY=4",
        "TEMPORAL_ADDRESS=localhost:7233",
        "ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000",
    ]
    target.write_text("\n".join(values) + "\n", encoding="utf-8")
    target.chmod(0o600)
    print("Development settings created. Organization sqe; account sqe@bic.local.")
