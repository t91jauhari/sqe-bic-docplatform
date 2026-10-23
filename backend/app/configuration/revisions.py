"""Configuration Revisions operations."""

from sqlalchemy import select
from app.db import Config


def latest_config(db, org):
    from app.configuration.repository import resolve_revision

    record = db.scalar(
        select(Config).where(Config.org == org).order_by(Config.version.desc()).limit(1)
    )
    return resolve_revision(db, record)
