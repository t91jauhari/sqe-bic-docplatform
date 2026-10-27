"""Explicit profile policy for same-case near-identical address and name reconciliation."""

import copy, re
from difflib import SequenceMatcher
from sqlalchemy import select
from .db import Document


def address_text(value):
    return (
        value.get("raw")
        if isinstance(value, dict)
        else value if isinstance(value, str) else None
    )


def address_numbers(value):
    return re.findall(r"\d+[a-z]*", value.casefold())


def name_text(value):
    if isinstance(value, dict):
        if "name" in value and value["name"]:
            return str(value["name"])
        if "raw" in value and value["raw"]:
            return str(value["raw"])
        return None
    return value if isinstance(value, str) else None


def apply_context(db, doc, cfg, report, selected=None, effective_overrides=None):
    report = apply_address_context(
        db, doc, cfg, report, selected=selected, effective_overrides=effective_overrides
    )
    report = apply_name_context(
        db, doc, cfg, report, selected=selected, effective_overrides=effective_overrides
    )
    return report


def apply_address_context(db, doc, cfg, report, selected=None, effective_overrides=None):
    rule = (
        cfg["profiles"][doc.doc_type]
        .get("policy", {})
        .get("case_address_reconciliation", {})
    )
    if not rule.get("enabled"):
        return report
    field = rule["target_field"]
    overrides = doc.overrides if effective_overrides is None else effective_overrides
    if field in overrides or (selected is not None and field not in selected):
        return report
    before = report["normalized"].get(field)
    text = address_text(before)
    if not isinstance(text, str) or not re.findall(r"\d+", text):
        return report
    sources = list(
        db.scalars(
            select(Document).where(
                Document.case_id == doc.case_id,
                Document.org == doc.org,
                Document.branch_id == doc.branch_id,
                Document.doc_type == rule["source_profile"],
                Document.status == "COMPLETED",
                Document.id != doc.id,
            )
        )
    )
    observations = []
    for source in sources:
        if rule["source_field"] in source.overrides:
            continue
        value = address_text(source.normalized.get(rule["source_field"]))
        if not isinstance(value, str) or address_numbers(value) != address_numbers(
            text
        ):
            continue
        a, b = [re.sub(r"\W", "", v.casefold()) for v in (text, value)]
        similarity = SequenceMatcher(None, a, b).ratio()
        if similarity >= rule.get("minimum_similarity", 0.85):
            observations.append((source, value, similarity))
    if not observations:
        return report
    values = {re.sub(r"\W", "", v.casefold()) for _, v, _ in observations}
    if len(values) != 1:
        report["automatic_context"] = {
            "status": "CONFLICT",
            "field": field,
            "source_document_ids": [s.id for s, _, _ in observations],
        }
        return report
    source, value, similarity = observations[0]
    replacement = (
        {**copy.deepcopy(before), "raw": value, "complete": True}
        if isinstance(before, dict)
        else value
    )
    if replacement == before:
        return report
    report["normalized"][field] = replacement
    if field in report.get("fields", {}):
        report["fields"][field]["normalized_value"] = copy.deepcopy(replacement)
    report["automatic_context"] = {
        "status": "APPLIED",
        "field": field,
        "before": copy.deepcopy(before),
        "after": copy.deepcopy(replacement),
        "source_document_id": source.id,
        "source_field": rule["source_field"],
        "similarity": round(similarity, 5),
        "policy": "same_case_near_match_matching_address_numbers",
    }
    report.setdefault("corrections", []).append(
        {
            "field": field,
            "kind": "automatic_case_address",
            "source_document_id": source.id,
        }
    )
    report["normalization"] = {
        "status": "PROFILE_CONTEXT_APPLIED",
        "handled_by": "published_case_address_policy",
    }
    return report


def apply_name_context(db, doc, cfg, report, selected=None, effective_overrides=None):
    rule = (
        cfg["profiles"]
        .get(doc.doc_type, {})
        .get("policy", {})
        .get("case_name_reconciliation", {})
    )
    if not rule.get("enabled"):
        if doc.doc_type == "application" and "remitter" in report.get("normalized", {}):
            rule = {
                "enabled": True,
                "target_field": "remitter",
                "source_profile": "ektp",
                "source_field": "name",
                "minimum_similarity": 0.80,
            }
        elif doc.doc_type in {"valas_declaration_1", "valas_declaration_2", "riplay"} and "customer_name" in report.get("normalized", {}):
            rule = {
                "enabled": True,
                "target_field": "customer_name",
                "source_profile": "ektp",
                "source_field": "name",
                "minimum_similarity": 0.80,
            }
        elif doc.doc_type == "lld" and "payer_name" in report.get("normalized", {}):
            rule = {
                "enabled": True,
                "target_field": "payer_name",
                "source_profile": "ektp",
                "source_field": "name",
                "minimum_similarity": 0.80,
            }
        else:
            return report

    field = rule.get("target_field")
    if not field:
        return report
    overrides = doc.overrides if effective_overrides is None else effective_overrides
    if field in overrides or (selected is not None and field not in selected):
        return report

    before = report["normalized"].get(field)
    target_str = name_text(before)
    if not isinstance(target_str, str) or not target_str.strip():
        return report

    source_profile = rule.get("source_profile", "ektp")
    source_field = rule.get("source_field", "name")

    sources = list(
        db.scalars(
            select(Document).where(
                Document.case_id == doc.case_id,
                Document.org == doc.org,
                Document.branch_id == doc.branch_id,
                Document.doc_type == source_profile,
                Document.status == "COMPLETED",
                Document.id != doc.id,
            )
        )
    )
    if not sources:
        return report

    observations = []
    clean_target = re.sub(r"[^\w]", "", target_str.casefold())
    for source in sources:
        if source_field in source.overrides:
            source_value = source.overrides[source_field]
        else:
            source_value = name_text(source.normalized.get(source_field))
        if not isinstance(source_value, str) or not source_value.strip():
            continue

        clean_source = re.sub(r"[^\w]", "", source_value.casefold())
        similarity = SequenceMatcher(None, clean_target, clean_source).ratio()
        min_sim = rule.get("minimum_similarity", 0.80)
        if similarity >= min_sim:
            observations.append((source, source_value, similarity))

    if not observations:
        return report

    values = {v.casefold() for _, v, _ in observations}
    if len(values) != 1:
        report["automatic_name_context"] = {
            "status": "CONFLICT",
            "field": field,
            "source_document_ids": [s.id for s, _, _ in observations],
        }
        return report

    source, value, similarity = observations[0]

    # Build replacement
    if isinstance(before, dict):
        replacement = copy.deepcopy(before)
        if "name" in replacement:
            replacement["name"] = value
            if "full_text" in replacement and isinstance(replacement["full_text"], str):
                if re.sub(r"[^\w]", "", replacement["full_text"].casefold()) == clean_target:
                    replacement["full_text"] = value
        elif "raw" in replacement:
            replacement["raw"] = value
            replacement["complete"] = True
    else:
        replacement = value

    if replacement == before:
        return report

    report["normalized"][field] = replacement
    if field in report.get("fields", {}):
        report["fields"][field]["normalized_value"] = copy.deepcopy(replacement)

    report["automatic_name_context"] = {
        "status": "APPLIED",
        "field": field,
        "before": copy.deepcopy(before),
        "after": copy.deepcopy(replacement),
        "source_document_id": source.id,
        "source_field": source_field,
        "similarity": round(similarity, 5),
        "policy": "same_case_ektp_name_reconciliation",
    }
    report.setdefault("corrections", []).append(
        {
            "field": field,
            "kind": "automatic_case_name",
            "source_document_id": source.id,
        }
    )
    return report


def queue_dependents(db, source, cfg):
    from app.case_lifecycle import enqueue

    for doc in db.scalars(
        select(Document).where(
            Document.case_id == source.case_id,
            Document.org == source.org,
            Document.branch_id == source.branch_id,
            Document.status == "COMPLETED",
            Document.id != source.id,
        )
    ):
        if doc.doc_type == source.doc_type:
            continue
        addr_rule = (
            cfg["profiles"]
            .get(doc.doc_type, {})
            .get("policy", {})
            .get("case_address_reconciliation", {})
        )
        if addr_rule.get("enabled") and addr_rule.get("source_profile") == source.doc_type:
            enqueue(db, doc, "revalidate")
            continue

        if source.doc_type == "ektp":
            if doc.doc_type in {"application", "valas_declaration_1", "valas_declaration_2", "riplay", "lld"}:
                enqueue(db, doc, "revalidate")
