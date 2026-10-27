"""Configuration Bootstrap operations."""

from app.native_profiles import (
    CLASSIFY_DESCRIPTIONS,
    ENGINE,
    GROUPING_PREFIXES,
    LABELS,
    PROFILE_NAMES,
    SOP_MESSAGE_TEMPLATES,
    SUFFIXES,
    SUFFIX_ALIASES,
    get_profile,
)
from app.configuration.publication import persist_revision
import copy
import hashlib
import json
from sqlalchemy import select
from app.db import Base, Branch, Config, Connector, SessionLocal, User, engine
from app.crypto import hash_password
from app.settings import settings


def default_config():
    from app.configuration.seed_catalog import seed_value
    from app.spider_provider import DEFAULT_INSTRUCTION
    from app.spatial_grounding import append_instruction
    from app.forex_sop import DEFAULT_POLICY
    from app.configuration.contexts import default_definitions

    profiles = {}
    for name in PROFILE_NAMES:
        p = get_profile(name)
        profiles[name] = {
            "label": LABELS[name],
            "classification_description": CLASSIFY_DESCRIPTIONS[name],
            "parse_prompt": p["parse_prompt"],
            "system_prompt": p["system_prompt"],
            "system_instruction": append_instruction(DEFAULT_INSTRUCTION),
            "policy": json.loads((ENGINE / p["policy"]).read_text(encoding="utf-8")),
            "suffixes": SUFFIXES[name],
            "columns": p["columns"],
            "schema": copy.deepcopy(p["schema"]),
            "schema_version": hashlib.sha256(
                json.dumps(p["schema"], sort_keys=True).encode()
            ).hexdigest(),
        }
    from app.sop import defaults

    return {
        **defaults(),
        **seed_value("bootstrap.configuration"),
        "profiles": profiles,
        "name_directory": json.loads(
            (ENGINE / "name_directory.json").read_text(encoding="utf-8")
        ),
        "grouping_prefixes": list(GROUPING_PREFIXES),
        "suffix_aliases": dict(SUFFIX_ALIASES),
        "sop_message_templates": dict(SOP_MESSAGE_TEMPLATES),
        "forex_sop_policy": copy.deepcopy(DEFAULT_POLICY),
        "context_definitions": default_definitions(),
    }


def seed():
    from app.auditing import audit
    import os

    if settings.environment != "development":
        return
    Base.metadata.create_all(engine)
    with SessionLocal.begin() as db:
        org = os.getenv("DEV_ORGANIZATION", "sqe")
        email = os.getenv("DEV_EMAIL", "sqe@bic.local").lower()
        if not db.scalar(select(User).where(User.org == org, User.email == email)):
            password = os.getenv("DEV_PASSWORD")
            if not password:
                raise RuntimeError(
                    "Set DEV_PASSWORD through the development initialization script."
                )
            branch = Branch(org=org, code="HQ", name="SQE · Development Branch")
            db.add(branch)
            db.flush()
            user = User(
                org=org,
                email=email,
                name="SQE Administrator",
                password_hash=hash_password(password),
                role="bank_admin",
                branches=[branch.id],
            )
            db.add(user)
            db.flush()
            cfg = Config(
                org=org, version=1, payload=default_config(), published_by=user.id
            )
            persist_revision(db, cfg)
            db.add(Connector(org=org, encrypted="", options={}))
            audit(db, org, user.id, "development.bootstrap", branch.id, email=email)
        upgrade_profiles(db, org)


def upgrade_profiles(db, org):
    """Publish additions as a new version; existing case configurations stay immutable."""
    from app.auditing import audit
    from app.configuration.revisions import latest_config

    previous = latest_config(db, org)
    if previous is None:
        return False
    defaults = default_config()
    missing = set(defaults["profiles"]) - set(previous.payload["profiles"])
    automation_missing = "workflow" not in previous.payload
    riplay_update = previous.payload.get("profiles", {}).get("riplay", {}).get(
        "policy", {}
    ).get("required_initial_pages") != [1, 2, 3]
    enhancement_missing = any(
        (
            key not in previous.payload
            for key in (
                "grouping_prefixes",
                "suffix_aliases",
                "sop_message_templates",
                "sop_review_bypass",
                "sop_review_bypass_result",
                "visual_evidence_review",
                "sequential_page_extraction",
                "cross_page_reference",
            )
        )
    )
    suffix_missing = any(
        (
            name in previous.payload.get("profiles", {})
            and (
                not set(defaults["profiles"][name]["suffixes"])
                <= set(previous.payload["profiles"][name].get("suffixes", []))
            )
            for name in defaults["profiles"]
        )
    )
    if (
        not missing
        and (not automation_missing)
        and (not riplay_update)
        and (not enhancement_missing)
        and (not suffix_missing)
    ):
        return False
    payload = copy.deepcopy(previous.payload)
    if automation_missing:
        from app.sop import defaults as automation_defaults

        payload.update(automation_defaults())
        for name in payload["profiles"]:
            payload["profiles"][name]["schema"] = defaults["profiles"][name]["schema"]
            payload["profiles"][name]["schema_version"] = defaults["profiles"][name][
                "schema_version"
            ]
    if riplay_update and "riplay" in payload["profiles"]:
        rp = payload["profiles"]["riplay"]
        rp["policy"] = {**rp["policy"], "required_initial_pages": [1, 2, 3]}
        rp["schema"] = defaults["profiles"]["riplay"]["schema"]
        rp["schema_version"] = defaults["profiles"]["riplay"]["schema_version"]
        clarification = "\nRIPLAY page-rule clarification overrides any older footer instruction: require bottom-right customer initials on pages 1, 2 and 3 only. Page 4 contains the main signing fields and needs no separate footer initial."
        rp["system_prompt"] += clarification
        rp["parse_prompt"] += clarification
    payload.setdefault("customer_aliases", {})
    for name in missing:
        payload["profiles"][name] = defaults["profiles"][name]
    for name, profile in payload["profiles"].items():
        if name in defaults["profiles"]:
            for suffix in defaults["profiles"][name]["suffixes"]:
                if suffix not in profile["suffixes"]:
                    profile["suffixes"] = list(profile["suffixes"]) + [suffix]
    payload.setdefault("grouping_prefixes", list(GROUPING_PREFIXES))
    payload.setdefault("suffix_aliases", dict(SUFFIX_ALIASES))
    payload.setdefault("sop_message_templates", dict(SOP_MESSAGE_TEMPLATES))
    payload.setdefault("sop_review_bypass", False)
    payload.setdefault("sop_review_bypass_result", "PASS")
    payload.setdefault("visual_evidence_review", True)
    payload.setdefault("sequential_page_extraction", True)
    payload.setdefault("cross_page_reference", True)
    persist_revision(
        db,
        Config(
            org=org,
            version=previous.version + 1,
            payload=payload,
            published_by="system.profile-upgrade",
        ),
    )
    audit(
        db,
        org,
        "system",
        "configuration.profiles_added",
        None,
        profiles=sorted(missing),
    )
    return True
