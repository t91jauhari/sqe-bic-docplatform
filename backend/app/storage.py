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
    provider_state = getattr(doc, "provider_state", None) or {}
    if isinstance(provider_state, dict):
        key = provider_state.get("storage_key")
        if key:
            return key
    filename = getattr(doc, "filename", "") or ""
    ext = "pdf"
    if "." in filename:
        candidate = filename.lower().rsplit(".", 1)[-1]
        if candidate in {"pdf", "png", "jpg", "jpeg"}:
            ext = candidate
    return object_key(
        doc.org, doc.branch_id, "documents", doc.id, f"original.{ext}"
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
            try:
                return self._path(key).read_bytes()
            except FileNotFoundError:
                if "/original." in key:
                    base = key.rsplit("/original.", 1)[0]
                    for alt in ("png", "pdf", "jpg", "jpeg"):
                        alt_path = self._path(f"{base}/original.{alt}")
                        if alt_path.is_file():
                            return alt_path.read_bytes()
                raise
        try:
            response = self.client.get_object(settings.minio_bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchBucket"} and "/original." in key:
                base = key.rsplit("/original.", 1)[0]
                for alt in ("png", "pdf", "jpg", "jpeg"):
                    alt_key = f"{base}/original.{alt}"
                    if alt_key != key:
                        try:
                            resp = self.client.get_object(settings.minio_bucket, alt_key)
                            try:
                                return resp.read()
                            finally:
                                resp.close()
                                resp.release_conn()
                        except Exception:
                            continue
            raise

    def delete(self, key):
        self._initialize()
        if self.client:
            self.client.remove_object(settings.minio_bucket, key)
        else:
            self._path(key).unlink(missing_ok=True)


@lru_cache(maxsize=1)
def store():
    return ObjectStore()
