"""Pinned configuration reads with an explicit, fail-closed storage rollout."""
from collections import OrderedDict
import copy
from dataclasses import dataclass
import json

from sqlalchemy import select

from .store import Publication, compile_publication, fingerprint

_MAX_CACHE_ENTRIES = 128


class ConfigurationIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True)
class ConfigurationSnapshot:
    id: str
    org: str
    version: int
    created_at: float
    published_by: str
    payload: dict


def _session_is_clean(session) -> bool:
    return not (session.new or session.dirty or session.deleted)


def _engine_cache(session) -> OrderedDict | None:
    if not _session_is_clean(session):
        return None
    bind = session.get_bind()
    if getattr(getattr(bind, "dialect", None), "name", None) != "postgresql":
        return None
    cache = getattr(bind, "_sqe_revision_cache", None)
    if cache is None:
        cache = OrderedDict()
        setattr(bind, "_sqe_revision_cache", cache)
    return cache


def _session_cache(session) -> dict | None:
    if not _session_is_clean(session):
        return None
    return session.info.setdefault("_sqe_revision_cache", {})


def _build_snapshot(entry, *, copy_payload: bool) -> ConfigurationSnapshot:
    config_id, org, version, created_at, published_by, payload_json, readonly_payload = entry
    payload = json.loads(payload_json) if copy_payload else readonly_payload
    return ConfigurationSnapshot(
        config_id, org, version, created_at, published_by, payload
    )


def resolve_revision(session, record, *, read_mode=None, copy_payload: bool = True):
    from app.settings import settings
    mode = settings.configuration_read_mode if read_mode is None else read_mode
    if mode not in {"legacy", "verify", "normalized"}:
        raise ValueError("Unknown configuration read mode.")
    if record is None:
        return None
    cache_key = (record.id, mode)
    scache = _session_cache(session)
    if scache is not None and cache_key in scache:
        return _build_snapshot(scache[cache_key], copy_payload=copy_payload)
    ecache = _engine_cache(session)
    if ecache is not None and cache_key in ecache:
        ecache.move_to_end(cache_key)
        entry = ecache[cache_key]
        if scache is not None:
            scache[cache_key] = entry
        return _build_snapshot(entry, copy_payload=copy_payload)

    payload = copy.deepcopy(record.payload)
    if mode != "legacy":
        publication = session.scalar(select(Publication).where(
            Publication.organization == record.org, Publication.revision == record.version))
        if publication is None or publication.source_config_id != record.id:
            raise ConfigurationIntegrityError("Pinned configuration publication is missing or incorrectly linked.")
        try:
            compiled = compile_publication(session, publication)
        except ValueError as exc:
            raise ConfigurationIntegrityError("Normalized configuration integrity check failed.") from exc
        if fingerprint(compiled) != fingerprint(payload):
            raise ConfigurationIntegrityError("Legacy and normalized configuration differ.")
        if mode == "normalized":
            payload = compiled

    if scache is not None or ecache is not None:
        payload_json = json.dumps(payload)
        readonly_payload = json.loads(payload_json)
        entry = (
            record.id,
            record.org,
            record.version,
            record.created_at,
            record.published_by,
            payload_json,
            readonly_payload,
        )
        if scache is not None:
            scache[cache_key] = entry
        if ecache is not None:
            ecache[cache_key] = entry
            ecache.move_to_end(cache_key)
            while len(ecache) > _MAX_CACHE_ENTRIES:
                ecache.popitem(last=False)
        return _build_snapshot(entry, copy_payload=copy_payload)

    return ConfigurationSnapshot(record.id, record.org, record.version, record.created_at,
                                 record.published_by, payload)


def get_revision(session, config_id, *, read_mode=None, copy_payload: bool = True):
    from app.db import Config
    from app.settings import settings
    mode = settings.configuration_read_mode if read_mode is None else read_mode
    if mode not in {"legacy", "verify", "normalized"}:
        raise ValueError("Unknown configuration read mode.")
    if not config_id:
        return None
    cache_key = (config_id, mode)
    scache = _session_cache(session)
    if scache is not None and cache_key in scache:
        return _build_snapshot(scache[cache_key], copy_payload=copy_payload)
    ecache = _engine_cache(session)
    if ecache is not None and cache_key in ecache:
        ecache.move_to_end(cache_key)
        entry = ecache[cache_key]
        if scache is not None:
            scache[cache_key] = entry
        return _build_snapshot(entry, copy_payload=copy_payload)
    return resolve_revision(
        session,
        session.get(Config, config_id),
        read_mode=mode,
        copy_payload=copy_payload,
    )
