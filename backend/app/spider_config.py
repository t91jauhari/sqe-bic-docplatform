"""Add independent Spider instructions without changing the active provider."""
from .configuration.publication import persist_revision


import copy
from sqlalchemy import select, text
from .db import Config, SessionLocal
from .domain import latest_config, audit
from .spider_provider import DEFAULT_INSTRUCTION


def seed_spider():
    with SessionLocal.begin() as db:
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(730600)"))
        elif db.bind.dialect.name == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))
        for org in db.scalars(select(Config.org).distinct()).all():
            previous = latest_config(db, org)
            payload = copy.deepcopy(previous.payload)
            for profile in payload["profiles"].values():
                profile.setdefault("system_instruction", DEFAULT_INSTRUCTION)
            if payload != previous.payload:
                persist_revision(db, Config(
                        org=org,
                        version=previous.version + 1,
                        payload=payload,
                        published_by="system.spider-ai",
                    )
                )
                audit(db, org, "system", "configuration.spider_instructions_seeded")
