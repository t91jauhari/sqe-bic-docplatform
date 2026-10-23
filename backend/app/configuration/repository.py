"""Pinned configuration reads with an explicit, fail-closed storage rollout."""
import copy
from dataclasses import dataclass

from sqlalchemy import select

from .store import Publication, compile_publication, fingerprint


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


def resolve_revision(session, record, *, read_mode=None):
    from app.settings import settings
    mode = settings.configuration_read_mode if read_mode is None else read_mode
    if mode not in {"legacy", "verify", "normalized"}:
        raise ValueError("Unknown configuration read mode.")
    if record is None:
        return None
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
    return ConfigurationSnapshot(record.id, record.org, record.version, record.created_at,
                                 record.published_by, payload)


def get_revision(session, config_id, *, read_mode=None):
    from app.db import Config
    return resolve_revision(session, session.get(Config, config_id), read_mode=read_mode)
