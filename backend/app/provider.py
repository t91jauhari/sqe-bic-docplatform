"""Checkpoint external side effects before submission; never blindly recreate jobs."""

import copy
import json


from .configuration.profiles import profile_schema, schema_report
from .db import SessionLocal
from app.native_profiles import LABELS, get_profile
from app.auditing import serial
from .settings import ROOT, settings


from .extraction.contracts import ProcessingIssue


def checkpoint(doc_id, status=None, **state):
    from .extraction.state_repository import SqlProviderState

    SqlProviderState(SessionLocal).checkpoint(doc_id, status, **state)


def state_of(doc_id):
    from .extraction.state_repository import SqlProviderState

    return SqlProviderState(SessionLocal).read(doc_id)


def fixture_response(doc_type):
    """Explicit synthetic fixtures, never claimed to be OCR of the uploaded PDF."""
    if doc_type not in LABELS:
        raise ProcessingIssue("Fixture mode requires a supported document type.")
    return json.loads(
        (ROOT / "backend/fixtures" / (doc_type + ".json")).read_text(encoding="utf-8")
    )


def run_provider(doc, cfg, heartbeat):
    """Compatibility facade; callers transition through the application service."""
    from .extraction.service import extract_document

    result = extract_document(doc, cfg, heartbeat)
    return result.response, result.classification


def run_fixture(doc, cfg, heartbeat):
    if settings.environment != "development":
        raise ProcessingIssue("Fixture processing is disabled outside development.")
    if doc.doc_type == "unknown":
        raise ProcessingIssue(
            "Fixture mode requires a recognized filename or manually assigned document type."
        )
    checkpoint(doc.id, "EXTRACTING", fixture=True)
    heartbeat()
    return fixture_response(doc.doc_type), {
        "method": "fixture",
        "type": doc.doc_type,
        "reason": "Synthetic development fixture. No document content was classified or extracted.",
        "confirmed": False,
    }


def run_llama(doc, cfg, heartbeat):
    """Reject historical integrations without submitting another paid job."""
    raise ProcessingIssue(
        "Llama provider has been removed. Publish a Spider-AI configuration and explicitly upgrade the case before retrying."
    )


def validate_extraction(doc, cfg, response, authoritative=None):
    from .configuration.field_checks import apply_field_checks

    if cfg["profiles"][doc.doc_type].get("validation_adapter") == "schema":
        return apply_field_checks(
            schema_report(doc, cfg, response), cfg["profiles"][doc.doc_type]
        )
    if cfg.get("provider") == "spider-ai":
        from .spider_result import extraction_report

        return extraction_report(doc, cfg, response)
    from datetime import datetime
    from zoneinfo import ZoneInfo

    profile = get_profile(doc.doc_type)
    raw = response["extract_result"]
    effective = copy.deepcopy(raw)
    effective.pop("_visual_evidence", None)
    effective.update(doc.overrides)
    kwargs = {"validation_context": {}} if doc.doc_type != "application" else {}
    if doc.doc_type == "application" and authoritative:
        kwargs["validation_context"] = {"authoritative": authoritative}
    if doc.doc_type in {"ektp", "valas_declaration_1", "valas_declaration_2", "riplay"}:
        kwargs["extract_job_id"] = response.get("id")
    if doc.doc_type == "riplay":
        kwargs["validation_context"] = {"defer_identity_to_case": True}
    policy = copy.deepcopy(cfg["profiles"][doc.doc_type]["policy"])
    if doc.doc_type == "ektp" and "normalization_enum_aliases" in getattr(
        doc, "provider_state", {}
    ):
        policy["enum_aliases"] = copy.deepcopy(
            doc.provider_state["normalization_enum_aliases"]
        )
        policy["enum_raw_fallback_fields"] = copy.deepcopy(
            doc.provider_state.get(
                "normalization_enum_raw_fallback_fields", ["religion"]
            )
        )
    native_fields = set(profile["schema"]["properties"])
    report = profile["validate"](
        {k: v for k, v in effective.items() if k in native_fields},
        response.get("extract_metadata"),
        policy,
        datetime.now(ZoneInfo("Asia/Jakarta")).date(),
        cfg["name_directory"],
        **kwargs,
    )
    report["document_type"] = doc.doc_type
    report["original_raw"] = raw
    report["review_overrides"] = doc.overrides
    # Registered native validators do not know optional profile extension fields.
    core = set(profile["schema"]["properties"])
    for key in (
        set(
            cfg["profiles"][doc.doc_type].get("schema", profile["schema"])["properties"]
        )
        - core
    ):
        value = effective.get(key)
        if key in effective:
            from .schema_descriptions import validate_extension_value

            validate_extension_value(
                value, cfg["profiles"][doc.doc_type]["schema"]["properties"][key], key
            )
        report["normalized"][key] = value
        report.setdefault("fields", {})[key] = {
            "raw_value": raw.get(key),
            "normalized_value": value,
            "status": "REVIEW" if value is None else "PASS",
            "issues": [],
        }
    return serial(apply_field_checks(report, cfg["profiles"][doc.doc_type]))
