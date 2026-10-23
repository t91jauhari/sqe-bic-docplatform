"""Evidence-led prompt refinements and optional schema extensions for Forex profiles."""

from .configuration.seed_catalog import seed_value
from .configuration.publication import persist_revision

import copy
import hashlib
import json
from pathlib import Path

RELEASE = "field-quality-v8-profile-rules"
INVOICE_FIELDS = seed_value("extraction_quality.INVOICE_FIELDS")
COMMON = seed_value("extraction_quality.COMMON")
RULES = seed_value("extraction_quality.RULES")


def guidance(key):
    if key == "ship_to_address":
        return (
            COMMON
            + " Treat an explicit shipment destination, including SHIPMENT FROM ... TO ..., as the shipping address. Do not require the literal Ship To label. Do not substitute a billing address or seller address."
            + RULES["address"]
        )
    rule = (
        "items"
        if key in ["item_name", "quantity"]
        else (
            "date"
            if "date" in key
            else (
                "swift"
                if "swift" in key
                else (
                    "account"
                    if any(x in key for x in ["number", "nik", "npwp"])
                    else (
                        "address"
                        if "address" in key
                        else (
                            "visual"
                            if any(
                                x in key
                                for x in ["signature", "stamp", "approval", "initials"]
                            )
                            else (
                                "money"
                                if any(
                                    x in key
                                    for x in [
                                        "amount",
                                        "charges",
                                        "currency",
                                        "price",
                                        "total",
                                        "words",
                                    ]
                                )
                                else (
                                    "items"
                                    if key in ["item_name", "quantity"]
                                    else (
                                        "name"
                                        if any(
                                            x in key
                                            for x in [
                                                "name",
                                                "signatory",
                                                "remitter",
                                                "beneficiary",
                                            ]
                                        )
                                        else "selection"
                                    )
                                )
                            )
                        )
                    )
                )
            )
        )
    )
    return COMMON + RULES[rule]


def apply_quality(payload, targets=None):
    result = copy.deepcopy(payload)
    catalog = Path(__file__).parent / "config_data/validation_targets.json"
    targets = (
        targets
        if targets is not None
        else (
            json.loads(catalog.read_text(encoding="utf-8")) if catalog.exists() else []
        )
    )
    profiles = result["profiles"]
    from app.native_profiles import get_profile

    for name, profile in profiles.items():
        if "schema" not in profile:
            profile["schema"] = copy.deepcopy(get_profile(name)["schema"])
    for key, (label, instruction) in INVOICE_FIELDS.items():
        profile = profiles["invoice"]
        profile["schema"]["properties"].setdefault(
            key, {"type": ["string", "null"], "description": instruction}
        )
        if key not in dict(profile["columns"]):
            profile["columns"].append([key, label])
    p = profiles["valas_declaration_1"]
    p["schema"]["properties"].setdefault(
        "stamp_verification",
        {
            "type": "object",
            "description": "Bank signature verification/specimen stamp, distinct from meterai and handwritten signature.",
            "properties": {
                "present": {
                    "type": ["boolean", "null"],
                    "description": "True only if verification stamp visibly present; false if region inspected and blank; null if unclear.",
                },
                "evidence": {
                    "type": ["string", "null"],
                    "description": "Visible stamp wording and its location.",
                },
            },
            "required": ["present", "evidence"],
        },
    )
    if "stamp_verification" not in dict(p["columns"]):
        p["columns"].append(["stamp_verification", "Stamp verification"])
    for target in targets:
        profile = profiles[target["profile"]]
        key = target["field"]
        node = profile["schema"]["properties"][key]
        addition = guidance(key)
        if addition not in node.get("description", ""):
            node["description"] = node.get("description", "") + addition
    from .reviewer_quality import apply_reviewer_rules

    result = apply_reviewer_rules(result)
    profiles = result["profiles"]
    for profile in profiles.values():
        profile["schema_version"] = hashlib.sha256(
            json.dumps(profile["schema"], sort_keys=True).encode()
        ).hexdigest()
    result["extraction_quality_release"] = RELEASE
    return result


def seed_quality():
    from sqlalchemy import select, text
    from .db import Config, SessionLocal
    from app.configuration.revisions import latest_config
    from app.auditing import audit

    with SessionLocal.begin() as db:
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(730620)"))
        for org in db.scalars(select(Config.org).distinct()):
            old = latest_config(db, org)
            if old.payload.get("extraction_quality_release") == RELEASE:
                continue
            payload = apply_quality(old.payload)
            persist_revision(
                db,
                Config(
                    org=org,
                    version=old.version + 1,
                    payload=payload,
                    published_by="system.field-quality",
                ),
            )
            audit(
                db,
                org,
                "system",
                "configuration.field_quality_seeded",
                release=RELEASE,
                previous_version=old.version,
            )
