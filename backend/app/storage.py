"""Private object storage. Authorization belongs to API callers, never public buckets."""

import io
import re
from functools import lru_cache
from threading import Lock

from minio import Minio
from minio.error import S3Error
from urllib3 import PoolManager, Timeout

from .settings import settings


def object_key(org, branch_id, kind, object_id, filename):
    parts = (org, branch_id, kind, object_id, filename)
    if any(not re.fullmatch(r"[A-Za-z0-9_.@-]+", p) or p in {".", ".."} for p in parts):
        raise ValueError("Invalid storage key component.")
    return "/".join(parts)


def original_key(doc):
    return getattr(doc, "provider_state", {}).get("storage_key") or object_key(
        doc.org, doc.branch_id, "documents", doc.id, "original.pdf"
    )


def sniff_mime(data: bytes) -> str:
    """Magic-byte media type for stored originals: PDF, PNG or JPEG."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return "application/octet-stream"


def fitz_open_original(data: bytes):
    """Open a stored original with PyMuPDF regardless of PDF or image format."""
    import fitz

    filetype = (
        "pdf" if sniff_mime(data) == "application/pdf" else "jpg"
    )
    return fitz.open(stream=data, filetype=filetype)


class ObjectStore:
    def __init__(self, client=None):
        self.client = client
        self.ready = False
        self.lock = Lock()
        if settings.storage_driver == "minio" and client is None:
            self.client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
                region=settings.minio_region,
                http_client=PoolManager(
                    timeout=Timeout(connect=5, read=60), retries=False
                ),
            )

    def _initialize(self):
        if not self.client or self.ready:
            return
        with self.lock:
            if not self.ready:
                if settings.environment == "development":
                    if not self.client.bucket_exists(settings.minio_bucket):
                        try:
                            self.client.make_bucket(settings.minio_bucket)
                        except S3Error as exc:
                            if exc.code not in {
                                "BucketAlreadyOwnedByYou",
                                "BucketAlreadyExists",
                            }:
                                raise
                # Production buckets and permissions are provisioned by infrastructure.
                self.ready = True

    def _path(self, key):
        path = (settings.storage / key).resolve()
        if not path.is_relative_to(settings.storage.resolve()):
            raise ValueError("Invalid storage path.")
        return path

    def put(self, key, data, content_type):
        self._initialize()
        if self.client:
            self.client.put_object(
                settings.minio_bucket,
                key,
                io.BytesIO(data),
                len(data),
                content_type=content_type,
            )
        else:
            path = self._path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def read(self, key):
        self._initialize()
        if not self.client:
            return self._path(key).read_bytes()
        response = self.client.get_object(settings.minio_bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def delete(self, key):
        self._initialize()
        if self.client:
            self.client.remove_object(settings.minio_bucket, key)
        else:
            self._path(key).unlink(missing_ok=True)


@lru_cache(maxsize=1)
def store():
    return ObjectStore()
