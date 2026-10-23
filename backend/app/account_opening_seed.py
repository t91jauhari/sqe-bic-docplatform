"""Add Account Opening configuration immutably; preserve existing cases and Forex settings."""
from .configuration.publication import persist_revision


import copy
import json
from pathlib import Path

RELEASE = "account-opening-workbook-v1"


def seed_account_opening():
    from sqlalchemy import select, text
    from .db import Config, SessionLocal
    from .domain import latest_config, default_config, audit, validate_config

    rules = json.loads(
        (Path(__file__).parent / "config_data/account_opening_rules.json").read_text(
            encoding="utf-8"
        )
    )
    with SessionLocal.begin() as db:
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(730308)"))
        elif db.bind.dialect.name == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))
        for org in db.scalars(select(Config.org).distinct()).all():
            old = latest_config(db, org)
            if RELEASE in old.payload.get("seed_releases", []):
                continue
            payload = copy.deepcopy(old.payload)
            defaults = default_config()
            for name, profile in defaults["profiles"].items():
                payload["profiles"].setdefault(name, profile)
            for name in defaults["profiles"]:
                if name in {
                    "join_visit",
                    "edd",
                    "account_opening_form",
                    "signature_difference",
                    "company_reference",
                }:
                    payload.setdefault("profile_variants", {}).setdefault(
                        name, {}
                    ).setdefault(
                        "account-workbook-v1",
                        {
                            "name": "Account Opening workbook v1 · evidence focused",
                            "profile": copy.deepcopy(defaults["profiles"][name]),
                        },
                    )
            existing = {r["id"] for r in payload["sop_rules"]}
            payload["sop_rules"] += [r for r in rules if r["id"] not in existing]
            # Populate untouched starter only; preserve a bank-customized flow and offer a named reference flow.
            flow = payload["templates"].get("account_opening", {})
            untouched = (
                flow.get("required", []) == [] and flow.get("sop_rule_ids", []) == []
            )
            existing_labels = {
                f["label"].strip().casefold()
                for key, f in payload["templates"].items()
                if key != "account_opening"
            }
            if untouched and "account opening" not in existing_labels:
                target, label = "account_opening", "Account Opening"
            else:
                target, label = (
                    "account_opening_reference",
                    "Account Opening · workbook reference",
                )
                count = 2
                while (
                    target in payload["templates"]
                    or label.casefold() in existing_labels
                ):
                    target, label = (
                        f"account_opening_reference_{count}",
                        f"Account Opening · workbook reference {count}",
                    )
                    count += 1
            payload["templates"][target] = {
                **flow,
                "label": label,
                "enabled": True,
                "description": "Workbook-defined Account Opening: core eKTP, opening form and RIPLAY; conditional supporting documents and visual review.",
                "required": ["ektp", "account_opening_form", "riplay"],
                "sop_rule_ids": [r["id"] for r in rules],
                "dataset_id": "account-opening-sample-v1",
                "document_family": "account_opening",
                "report_layout": "account_opening",
                "report_context": {
                    "category": "Teller",
                    "activity": "Account Opening",
                    "inspection_type": "Documents",
                },
            }
            payload.setdefault("seed_releases", []).append(RELEASE)
            validate_config(payload)
            persist_revision(db, Config(
                    org=org,
                    version=old.version + 1,
                    payload=payload,
                    published_by="system.account-workbook-v1",
                )
            )
            audit(
                db,
                org,
                "system",
                "configuration.account_opening_seeded",
                None,
                previous_version=old.version,
                flow_id=target,
                dataset_id="account-opening-sample-v1",
            )
