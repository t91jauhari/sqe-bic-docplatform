"""Canonical configuration hashing, independent of storage frameworks."""
import hashlib
import json


def fingerprint(payload: dict) -> str:
    return hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode()).hexdigest()
