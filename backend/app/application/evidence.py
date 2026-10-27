"""Evidence application operations.

Transactions, authorization, audit and pinned configuration remain one unit.
"""

from app.errors import ApplicationError
from app.configuration.repository import get_revision
from app.configuration.profiles import profile_schema
import copy
from sqlalchemy import select
from app.db import Case, Document, SessionLocal
from app.auditing import audit
from app.case_lifecycle import refresh_case
from app.access import authorized
from app.contracts import VisualBoxReview


def location_learning_history(*, document_type: str, user):
    from app.db import LocationFeedback

    with SessionLocal() as db:
        query = select(LocationFeedback).where(LocationFeedback.org == user.org)
        if user.role != "bank_admin":
            query = query.where(LocationFeedback.branch_id.in_(user.branches))
        if document_type:
            query = query.where(LocationFeedback.document_type == document_type)
        return [
            {
                "id": s.id,
                "document_type": s.document_type,
                "field": s.field,
                "page_number": s.page_number,
                "bbox": s.bbox,
                "enabled": s.enabled,
                "layout_available": bool(s.layout),
                "created_at": s.created_at,
                "reviewer_id": s.reviewer_id,
                "reason": s.reason,
            }
            for s in db.scalars(
                query.order_by(LocationFeedback.created_at.desc()).limit(200)
            )
        ]


def disable_location_learning(*, sample_id: str, user):
    from app.db import LocationFeedback

    with SessionLocal.begin() as db:
        item = authorized(db, LocationFeedback, sample_id, user)
        item.enabled = False
        audit(
            db,
            user.org,
            user.id,
            "location_feedback.disabled",
            item.branch_id,
            document_id=item.document_id,
            sample_id=item.id,
        )
    return {"disabled": True}


def review_visual_box(*, doc_id: str, data: VisualBoxReview, user):
    from app.evidence import build_evidence, apply_evidence_review, visual_fields
    from app.provider import validate_extraction
    from app.field_evidence import (
        build_field_evidence,
        populated_fields,
        attach_field_evidence,
    )

    with SessionLocal.begin() as db:
        d = authorized(db, Document, doc_id, user)
        if d.status != "COMPLETED":
            raise ApplicationError(
                "conflict", "Wait for document processing to complete."
            )
        visual_map = dict(visual_fields(d.raw))
        visual_names = set(visual_map)
        visual_roots = {key.split(".")[0] for key in visual_names}
        ordinary_names = {
            key
            for (key, _) in populated_fields(d.raw, include_empty=True)
            if key.split(".")[0] not in visual_roots
        }
        target_field = data.field
        if target_field not in visual_names | ordinary_names:
            if target_field == "page_initials" and isinstance(
                d.raw.get("page_initials"), dict
            ):
                pages = d.raw["page_initials"].get("pages") or []
                for idx, page in enumerate(pages):
                    if (
                        isinstance(page, dict)
                        and page.get("page_number") == data.page_number
                    ):
                        target_field = f"page_initials.pages.{idx}"
                        break
                else:
                    candidate = f"page_initials.pages.{max(data.page_number - 1, 0)}"
                    if candidate in visual_names:
                        target_field = candidate
            elif f"{target_field}.raw" in ordinary_names:
                target_field = f"{target_field}.raw"
            else:
                sub_matches = [
                    k for k in sorted(ordinary_names) if k.startswith(f"{target_field}.")
                ]
                if sub_matches:
                    target_field = sub_matches[0]
        if target_field not in visual_names | ordinary_names:
            raise ApplicationError("invalid_input", "Unknown extracted field.")
        cfg = get_revision(db, db.get(Case, d.case_id).config_id).payload
        metadata = {
            **d.metadata_json,
            "visual_evidence": {
                **d.metadata_json.get("visual_evidence", {}),
                target_field: {
                    "page_number": data.page_number,
                    "bbox": data.bbox,
                    "units": "normalized",
                    "reviewed_by": user.id,
                    "reason": data.reason,
                },
            },
        }
        response = {
            "extract_result": d.raw,
            "extract_metadata": metadata,
            "id": d.provider_state.get("extract_job_id"),
        }
        evidence = build_evidence(d, response)
        field_evidence = build_field_evidence(d, response)
        item = next(
            (e for e in evidence + field_evidence if e["field"] == target_field)
        )
        if not item["available"]:
            raise ApplicationError(
                "invalid_input", item.get("error", "Invalid visual region.")
            )
        item["review_status"] = "REVIEWED"
        item["reviewed_by"] = user.id
        item["review_reason"] = data.reason
        report = validate_extraction(d, cfg, response)
        if cfg.get("provider") == "spider-ai":
            report["visual_evidence"] = evidence
        else:
            apply_evidence_review(report, evidence)
        attach_field_evidence(report, field_evidence)
        from app.location_learning import record_feedback

        profile = cfg["profiles"][d.doc_type]
        sample = record_feedback(
            db,
            d,
            {
                **profile,
                "schema": profile.get("schema") or profile_schema(cfg, d.doc_type),
            },
            data,
            user,
        )
        metadata["location_feedback_revision"] = sample.id
        d.metadata_json = metadata
        d.validation = report
        d.validation_status = report["status"]
        audit(
            db,
            d.org,
            user.id,
            "document.visual_box_reviewed",
            d.branch_id,
            d.case_id,
            document_id=d.id,
            field=data.field,
            location_feedback_id=sample.id,
            future_guidance_enabled=sample.enabled,
            page=data.page_number,
            reason=data.reason,
        )
        refresh_case(db, d.case_id)
    return {
        "queued": True,
        "location_feedback_id": sample.id,
        "future_guidance_enabled": sample.enabled,
    }


def refresh_field_evidence(*, doc_id: str, user):
    from app.field_evidence import build_field_evidence, attach_field_evidence
    from app.spatial_grounding import normalize_response

    with SessionLocal.begin() as db:
        d = authorized(db, Document, doc_id, user)
        if d.status != "COMPLETED":
            raise ApplicationError(
                "conflict", "Wait for document processing to complete."
            )
        response = normalize_response(
            {
                "extract_result": d.raw,
                "extract_metadata": d.metadata_json,
                "id": d.provider_state.get("extract_job_id"),
            }
        )
        d.raw = response["extract_result"]
        d.metadata_json = response.get("extract_metadata") or {}
        from app.evidence import build_evidence

        evidence = build_field_evidence(d, response)
        report = copy.deepcopy(d.validation)
        if d.metadata_json.get("spatial_evidence") or d.metadata_json.get(
            "visual_evidence"
        ):
            previous = {
                item["field"]: item for item in report.get("visual_evidence", [])
            }
            visual = build_evidence(d, response)
            for item in visual:
                old = previous.get(item["field"], {})
                if (
                    item.get("available")
                    and item.get("revision") == old.get("revision")
                    and (item.get("image_sha256") == old.get("image_sha256"))
                ):
                    item["review_status"] = old.get(
                        "review_status", item["review_status"]
                    )
            report["visual_evidence"] = visual
        if isinstance(d.raw, dict) and isinstance(d.raw.get("page_initials"), dict):
            if (
                isinstance(d.normalized, dict)
                and "page_initials" in d.normalized
                and "page_initials" not in (d.overrides or {})
            ):
                d.normalized = {
                    **d.normalized,
                    "page_initials": copy.deepcopy(d.raw["page_initials"]),
                }
            if isinstance(report.get("fields"), dict) and "page_initials" in report["fields"]:
                report["fields"]["page_initials"]["raw_value"] = copy.deepcopy(
                    d.raw["page_initials"]
                )
                if "page_initials" not in (d.overrides or {}):
                    report["fields"]["page_initials"]["normalized_value"] = copy.deepcopy(
                        d.raw["page_initials"]
                    )
            if (
                isinstance(report.get("normalized"), dict)
                and "page_initials" in report["normalized"]
                and "page_initials" not in (d.overrides or {})
            ):
                report["normalized"]["page_initials"] = copy.deepcopy(
                    d.raw["page_initials"]
                )
        d.validation = attach_field_evidence(report, evidence)
        audit(
            db,
            d.org,
            user.id,
            "document.field_evidence_refreshed",
            d.branch_id,
            d.case_id,
            document_id=d.id,
            fields=len(evidence),
            available=sum((e["available"] for e in evidence)),
        )
        refresh_case(db, d.case_id)
    return {"queued": True}
