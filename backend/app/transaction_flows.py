"""User-managed transaction flows reuse registered extraction document profiles."""
from .configuration.publication import persist_revision


import copy
import re

RELEASE = "transaction-flows-v1"


def validate_flows(cfg):
    from .document_families import validate_families, families
    validate_families(cfg)
    catalog=families(cfg)
    flows = cfg.get("templates")
    if not isinstance(flows, dict) or not 1 <= len(flows) <= 100:
        raise ValueError("Configure between 1 and 100 transaction flows.")
    rule_ids = {r["id"] for r in cfg.get("sop_rules", []) + cfg.get("generic_sop_rules", [])}
    labels = set()
    for key, flow in flows.items():
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", key):
            raise ValueError(
                "Flow IDs must start with a letter and contain at most 40 lowercase letters, digits, underscores or hyphens."
            )
        if (
            not isinstance(flow, dict)
            or not isinstance(flow.get("label"), str)
            or not 1 <= len(flow["label"].strip()) <= 120
        ):
            raise ValueError("Flow names require 1–120 characters.")
        label = flow["label"].strip().casefold()
        if label in labels:
            raise ValueError("Transaction flow names must be unique.")
        labels.add(label)
        if not isinstance(flow.get("enabled", True), bool):
            raise ValueError("Flow enabled status must be boolean.")
        if (
            not isinstance(flow.get("description", ""), str)
            or len(flow.get("description", "")) > 2000
        ):
            raise ValueError("Flow descriptions must be at most 2000 characters.")
        if flow.get("document_family", "forex") not in catalog:
            raise ValueError("Unknown document family.")
        dataset_id = flow.get("dataset_id")
        if dataset_id is not None and (not isinstance(dataset_id, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,119}', dataset_id)):
            raise ValueError("Invalid reference dataset ID.")
        if flow.get("report_layout", "forex") not in {"forex", "account_opening"}:
            raise ValueError("Unknown report layout.")
        context = flow.get("report_context", {})
        if not isinstance(context, dict) or any(
            k
            not in {"region_name", "category", "activity", "inspection_type", "period"}
            or not isinstance(v, str)
            or len(v) > 500
            for k, v in context.items()
        ):
            raise ValueError("Invalid flow report context.")
        required = flow.get("required", [])
        if (
            not isinstance(required, list)
            or any(not isinstance(v, str) or v not in cfg["profiles"] for v in required)
            or len(required) != len(set(required))
        ):
            raise ValueError(
                "Required documents must be distinct registered document profiles."
            )
        family=flow.get('document_family','forex')
        if family not in {'forex','account_opening'} and not set(required)<=set(catalog[family]['profiles']):
            raise ValueError(f'{key}: required documents must belong to its document family.')
        rules = flow.get("sop_rule_ids")
        if rules is not None and (
            not isinstance(rules, list)
            or any(not isinstance(v, str) or v not in rule_ids for v in rules)
            or len(rules) != len(set(rules))
        ):
            raise ValueError("Flow SOP checks must be distinct registered rule IDs.")
    if not any(flow.get("enabled", True) and catalog[flow.get('document_family','forex')].get('enabled',True) for flow in flows.values()):
        raise ValueError("At least one transaction flow must remain active.")


def scope_configuration(cfg, flow_id):
    result = copy.deepcopy(cfg)
    flow = result["templates"][flow_id]
    from .document_families import families
    family_id=flow.get('document_family','forex')
    family=families(result)[family_id]
    generic_rules = []
    if "generic_sop_rules" in cfg:
        from .configuration.generic_sop import runtime_rule, validate_generic_rules

        generic_rules = [runtime_rule(rule) for rule in validate_generic_rules(cfg) if family_id in rule.families]
    selected = flow.get("sop_rule_ids")
    if selected is None and "rule_scope" in cfg:
        from .configuration.rule_scope import validate_rule_scope

        selected = validate_rule_scope(cfg).family_rule_ids[family_id]
    if selected is None:
        result["sop_rules"] = [
            r
            for r in result.get("sop_rules", [])
            if r.get("source_ref", "").startswith("AO:")
            == (flow.get("document_family") == "account_opening")
        ]
        if family_id not in {'forex','account_opening'}:
            result['sop_rules']=[r for r in cfg.get('sop_rules',[]) if r['id'] in family.get('sop_rule_ids',[])]
    if selected is not None:
        result["sop_rules"] += generic_rules
        result["sop_rules"] = [
            r for r in result.get("sop_rules", []) if r["id"] in selected
        ]
    else:
        result["sop_rules"] += generic_rules
    from .forex_sop import effective_rule, policy_for
    result["sop_rules"] = [effective_rule(r) if r.get("operator") != "configured_compare" and r.get("source_ref", "").startswith("SOP3:") else r for r in result.get("sop_rules", [])]
    result["forex_sop_policy"] = policy_for(result)
    if "rule_order" in cfg:
        ranks = {rule_id: position for position, rule_id in enumerate(cfg["rule_order"])}
        result["sop_rules"].sort(key=lambda rule: ranks[rule["id"]])
    result["report_context"] = {
        **result.get("report_context", {}),
        **family.get('report_context',{}),
        "category": flow["label"],
        **flow.get("report_context", {}),
    }
    return result


def score_configuration(cfg, flow_id, findings):
    if cfg["templates"][flow_id].get("report_layout") == "account_opening":
        from .account_opening_sop import score
    else:
        from .sop import score
    return score(findings)


def seed_transaction_flows():
    from sqlalchemy import select, text
    from .db import Config, SessionLocal
    from .domain import latest_config, audit

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
            for flow in payload["templates"].values():
                flow.setdefault("enabled", True)
                flow.setdefault("description", "")
                # Legacy flows preserve all existing SOP checks.
                flow.setdefault("sop_rule_ids", None)
            if "account_opening" not in payload["templates"] and not any(
                f["label"].strip().casefold() == "account opening"
                for f in payload["templates"].values()
            ):
                payload["templates"]["account_opening"] = {
                    "label": "Account Opening",
                    "description": "Starter flow. Configure required documents and applicable SOP checks before operational use.",
                    "enabled": True,
                    "required": [],
                    "sop_rule_ids": [],
                }
            payload.setdefault("seed_releases", []).append(RELEASE)
            validate_flows(payload)
            persist_revision(db, Config(
                    org=org,
                    version=old.version + 1,
                    payload=payload,
                    published_by="system.transaction-flows-v1",
                )
            )
            audit(
                db,
                org,
                "system",
                "configuration.transaction_flows_seeded",
                None,
                previous_version=old.version,
            )
