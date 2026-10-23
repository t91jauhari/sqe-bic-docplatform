"""Versioned seed/compatibility data. Active business settings live in revisions."""

import copy
from functools import lru_cache
import json
from pathlib import Path


def _decode(value):
    if isinstance(value, list):
        return [_decode(item) for item in value]
    if isinstance(value, dict):
        if set(value) == {"$tuple"}:
            return tuple(_decode(item) for item in value["$tuple"])
        if set(value) == {"$set"}:
            return set(_decode(item) for item in value["$set"])
        return {key: _decode(item) for key, item in value.items()}
    return value


@lru_cache(maxsize=1)
def _catalog():
    path = Path(__file__).parents[1] / "config_data/extraction_seed_catalog_v1.json"
    return _decode(json.loads(path.read_text(encoding="utf-8")))


def seed_value(key):
    return copy.deepcopy(_catalog()[key])
