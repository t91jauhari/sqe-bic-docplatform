"""Configured schema access and generic validation, beside native adapters."""

import copy
import json


def validate_schema_adapter(profile):
    """Reject constraints this structural adapter does not execute."""
    if set(profile.get("policy", {})) - {
        "extraction_sampling",
        "extraction_detail_regions",
        "case_address_reconciliation",
    }:
        raise ValueError(
            "Custom profiles support extraction controls only; configure business policy as SOP rules."
        )
    allowed = {
        "type",
        "description",
        "properties",
        "required",
        "items",
        "enum",
        "additionalProperties",
    }

    def visit(node):
        if set(node) - allowed:
            raise ValueError(
                "Custom structural schemas support type, properties, required, items, enum, description and additionalProperties only. Configure business checks as SOP rules."
            )
        if (
            "additionalProperties" in node
            and type(node["additionalProperties"]) is not bool
        ):
            raise ValueError("additionalProperties must be boolean.")
        if "enum" in node and (
            not isinstance(node["enum"], list) or not 1 <= len(node["enum"]) <= 100
        ):
            raise ValueError("Schema enums require 1–100 choices.")
        types = node.get("type", "object")
        if (
            "array" in (types if isinstance(types, list) else [types])
            and "items" not in node
        ):
            raise ValueError("Custom array fields require an items schema.")
        for child in node.get("properties", {}).values():
            visit(child)
        if "items" in node:
            visit(node["items"])

    visit(profile["schema"])


def profile_schema(payload, profile_id):
    profile = payload["profiles"][profile_id]
    if profile.get("schema"):
        return profile["schema"]
    from app.native_profiles import get_profile

    return get_profile(profile_id)["schema"]


def validate_shape(value, schema):
    from app.schema_descriptions import validate_extension_value

    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Configured extraction must contain finite JSON values."
        ) from exc
    validate_extension_value(value, schema, "$")

    def check_extras(value, node):
        if isinstance(value, dict):
            properties = node.get("properties", {})
            if not node.get("additionalProperties", False) and set(value) - set(
                properties
            ):
                raise ValueError("Configured extraction contains unexpected fields.")
            for key, child in properties.items():
                if key in value:
                    check_extras(value[key], child)
        elif isinstance(value, list):
            for child in value:
                check_extras(child, node.get("items", {}))

    check_extras(value, schema)


def schema_report(doc, payload, response):
    """Structural/data-presence validation only; no inferred business facts."""
    schema = profile_schema(payload, doc.doc_type)
    raw = copy.deepcopy(response["extract_result"])
    raw.pop("_visual_evidence", None)
    effective = {**raw, **copy.deepcopy(doc.overrides)}
    if "page_results" not in schema["properties"]:
        effective.pop("page_results", None)
    validate_shape(effective, schema)
    normalized, fields = {}, {}
    for key, node in schema["properties"].items():
        value = effective.get(key)
        wrapped = isinstance(value, dict) and set(node.get("properties", {})) == {
            "raw",
            "complete",
        }
        normalized[key] = value.get("raw") if wrapped else value
        missing = normalized[key] is None or normalized[key] == ""
        uncertain = wrapped and value.get("complete") is not True
        status = (
            "FAIL"
            if missing and key in schema.get("required", [])
            else "NOT_APPLICABLE" if missing else "REVIEW" if uncertain else "PASS"
        )
        fields[key] = {
            "raw_value": raw.get(key),
            "normalized_value": normalized[key],
            "status": status,
            "issues": (
                [{"code": "INCOMPLETE_EXTRACTION", "severity": "REVIEW"}]
                if uncertain
                else []
            ),
        }
    status = (
        "FAIL"
        if any(field["status"] == "FAIL" for field in fields.values())
        else (
            "REVIEW"
            if any(field["status"] == "REVIEW" for field in fields.values())
            else "PASS"
        )
    )
    return {
        "document_type": doc.doc_type,
        "status": status,
        "processing_mode": "configured_schema",
        "normalized": normalized,
        "original_raw": raw,
        "review_overrides": copy.deepcopy(doc.overrides),
        "fields": fields,
        "corrections": [],
        "normalization": {"status": "SCHEMA_PROJECTION"},
    }
