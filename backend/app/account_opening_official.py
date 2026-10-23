"""Publish the confirmed official cross-document rules without mutating case pins."""

from .configuration.seed_catalog import seed_value
from .configuration.publication import persist_revision


import copy
import json
from pathlib import Path

RELEASE = "account-opening-official-cross-document-v2"
EXCLUDED = seed_value("account_opening_official.EXCLUDED")


def seed_official_account_rules():
    from sqlalchemy import select, text
    from .db import Config, SessionLocal
    from app.auditing import audit
    from app.configuration.revisions import latest_config
    from app.configuration.validation import validate_config

    official = {
        r["id"]: r
        for r in json.loads(
            (
                Path(__file__).parent / "config_data/account_opening_rules.json"
            ).read_text(encoding="utf-8")
        )
        if r["id"].startswith("AO_SYSTEM_")
    }
    with SessionLocal.begin() as db:
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(730309)"))
        for org in db.scalars(select(Config.org).distinct()).all():
            old = latest_config(db, org)
            if RELEASE in old.payload.get("seed_releases", []):
                continue
            payload = copy.deepcopy(old.payload)
            changed = []
            for index, rule in enumerate(payload.get("sop_rules", [])):
                replacement = official.get(rule["id"])
                if replacement is None:
                    continue
                # Retain the administrator's enabled state, but replace this official rule's definition.
                updated = {**rule, **replacement, "enabled": rule["enabled"]}
                payload["sop_rules"][index] = updated
                if updated != rule:
                    changed.append(rule["id"])
            if not any(r["id"] in official for r in payload.get("sop_rules", [])):
                continue
            payload.setdefault("seed_releases", []).append(RELEASE)
            validate_config(payload)
            persist_revision(
                db,
                Config(
                    org=org,
                    version=old.version + 1,
                    payload=payload,
                    published_by="system.account-official-v2",
                ),
            )
            audit(
                db,
                org,
                "system",
                "configuration.account_opening_official_rules_aligned",
                None,
                previous_version=old.version,
                changed_rule_ids=changed,
                excluded=EXCLUDED,
                external_cbs_verification=False,
            )
