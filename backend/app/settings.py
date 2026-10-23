"""Infrastructure settings; business configuration lives in versioned DB records."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    dataset_read_mode: str = os.getenv("DATASET_READ_MODE", "bundled")
    configuration_storage_mode: str = os.getenv("CONFIGURATION_STORAGE_MODE", "legacy")
    configuration_read_mode: str = os.getenv("CONFIGURATION_READ_MODE", "legacy")
    environment: str = os.getenv("APP_ENV", "development")
    database_url: str = os.getenv(
        "DATABASE_URL", f"sqlite:///{ROOT / 'data/platform.db'}"
    )
    storage: Path = Path(os.getenv("STORAGE_PATH", str(ROOT / "data/files")))
    storage_driver: str = os.getenv("STORAGE_DRIVER", "minio")
    minio_endpoint: str = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    minio_access_key: str = os.getenv("MINIO_ACCESS_KEY", "")
    minio_secret_key: str = os.getenv("MINIO_SECRET_KEY", "")
    minio_bucket: str = os.getenv("MINIO_BUCKET", "sqe-documents")
    minio_secure: bool = os.getenv("MINIO_SECURE", "false").lower() == "true"
    minio_region: str = os.getenv("MINIO_REGION", "us-east-1")
    secret: str = os.getenv("APP_SECRET", "")
    secure_cookie: bool = os.getenv("SECURE_COOKIE", "false").lower() == "true"
    origins: tuple = tuple(
        os.getenv(
            "ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",")
    )
    temporal: str = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
    task_queue: str = os.getenv("TEMPORAL_TASK_QUEUE", "sqe-documents")
    workflow_driver: str = os.getenv("WORKFLOW_DRIVER", "temporal")
    concurrency: int = int(os.getenv("WORKER_CONCURRENCY", "50"))
    max_file_bytes: int = 30 * 1024 * 1024
    max_batch_files: int = 100


settings = Settings()
if settings.dataset_read_mode not in {"bundled", "verify", "registry"}:
    raise RuntimeError("DATASET_READ_MODE must be bundled, verify or registry.")
if settings.configuration_storage_mode not in {"legacy", "dual"}:
    raise RuntimeError("CONFIGURATION_STORAGE_MODE must be legacy or dual.")
if settings.configuration_read_mode not in {"legacy", "verify", "normalized"}:
    raise RuntimeError("CONFIGURATION_READ_MODE must be legacy, verify or normalized.")
if settings.configuration_read_mode != "legacy" and settings.configuration_storage_mode != "dual":
    raise RuntimeError("Verified/normalized configuration reads require dual writes.")
if not settings.secret:
    raise RuntimeError("APP_SECRET is required. Run python scripts/init_dev.py first.")
if settings.environment != "development" and (
    len(settings.secret) < 32
    or not settings.secure_cookie
    or settings.workflow_driver != "temporal"
):
    raise RuntimeError(
        "Production requires a strong secret, secure cookies and Temporal."
    )

if settings.storage_driver not in {"local", "minio"}:
    raise RuntimeError("STORAGE_DRIVER must be minio or local.")
if settings.storage_driver == "minio" and (
    not settings.minio_access_key or not settings.minio_secret_key
):
    raise RuntimeError(
        "MinIO credentials are required. Run scripts/init_dev.py or configure the environment."
    )
if settings.environment != "development" and (
    settings.storage_driver != "minio" or not settings.minio_secure
):
    raise RuntimeError("Production requires MinIO over TLS.")

if not 1 <= settings.concurrency <= 50:
    raise RuntimeError("WORKER_CONCURRENCY must be between 1 and 50.")
