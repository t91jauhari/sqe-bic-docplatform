"""Configuration Revisions operations."""

from sqlalchemy import select
from app.db import Config


def latest_config(db, org, *, copy_payload: bool = True):
    from app.configuration.repository import (
        _engine_cache,
        get_revision,
        resolve_revision,
    )

    if _engine_cache(db) is not None:
        config_id = db.scalar(
            select(Config.id)
            .where(Config.org == org)
            .order_by(Config.version.desc())
            .limit(1)
        )
        return (
            get_revision(db, config_id, copy_payload=copy_payload)
            if config_id
            else None
        )
    record = db.scalar(
        select(Config).where(Config.org == org).order_by(Config.version.desc()).limit(1)
    )
    return resolve_revision(db, record, copy_payload=copy_payload)
