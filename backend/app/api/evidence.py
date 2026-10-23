"""Evidence HTTP boundary."""
from fastapi import APIRouter
from app.configuration.repository import get_revision
from app.configuration.profiles import profile_schema
import copy
from fastapi import Depends, HTTPException, Response
from sqlalchemy import select
from app.db import Case, Document, SessionLocal
from app.domain import audit, refresh_case
from app.security import authorized, current_user
from app.storage import original_key, store, fitz_open_original
from app.api.dependencies import REVIEW, WRITE
from app.api.contracts import VisualBoxReview

router = APIRouter(tags=['evidence'])

@router.get("/api/location-learning")
def location_learning_history(document_type: str = "", user=Depends(current_user)):
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

@router.post("/api/location-learning/{sample_id}/disable")
def disable_location_learning(sample_id: str, user=Depends(REVIEW)):
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

@router.post("/api/documents/{doc_id}/visual-box", status_code=202)
def review_visual_box(doc_id: str, data: VisualBoxReview, user=Depends(REVIEW)):
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
            raise HTTPException(409, "Wait for document processing to complete.")
        visual_names = {key for key, _ in visual_fields(d.raw)}
        visual_roots = {key.split(".")[0] for key in visual_names}
        ordinary_names = {
            key
            for key, _ in populated_fields(d.raw, include_empty=True)
            if key.split(".")[0] not in visual_roots
        }
        if data.field not in visual_names | ordinary_names:
            raise HTTPException(422, "Unknown extracted field.")
        cfg = get_revision(db, db.get(Case, d.case_id).config_id).payload
        metadata = {
            **d.metadata_json,
            "visual_evidence": {
                **d.metadata_json.get("visual_evidence", {}),
                data.field: {
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
        item = next(e for e in evidence + field_evidence if e["field"] == data.field)
        if not item["available"]:
            raise HTTPException(422, item.get("error", "Invalid visual region."))
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

@router.post("/api/documents/{doc_id}/field-evidence", status_code=202)
def refresh_field_evidence(doc_id: str, user=Depends(WRITE)):
    from app.field_evidence import build_field_evidence, attach_field_evidence

    with SessionLocal.begin() as db:
        d = authorized(db, Document, doc_id, user)
        if d.status != "COMPLETED":
            raise HTTPException(409, "Wait for document processing to complete.")
        response = {
            "extract_result": d.raw,
            "extract_metadata": d.metadata_json,
            "id": d.provider_state.get("extract_job_id"),
        }
        from app.evidence import build_evidence
        evidence = build_field_evidence(d, response)
        report = copy.deepcopy(d.validation)
        if d.metadata_json.get("spatial_evidence"):
            previous = {item["field"]:item for item in report.get("visual_evidence",[])}
            visual = build_evidence(d, response)
            for item in visual:
                old = previous.get(item["field"],{})
                if item.get("available") and item.get("revision") == old.get("revision") and item.get("image_sha256") == old.get("image_sha256"):
                    item["review_status"] = old.get("review_status",item["review_status"])
            report["visual_evidence"] = visual
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
            available=sum(e["available"] for e in evidence),
        )
        refresh_case(db, d.case_id)
    return {"queued": True}

@router.get("/api/documents/{doc_id}/pages/{page_number}")
def document_page(doc_id: str, page_number: int, user=Depends(current_user)):
    import fitz

    with SessionLocal() as db:
        d = authorized(db, Document, doc_id, user)
    with fitz_open_original(store().read(original_key(d))) as pdf:
        if page_number < 1 or page_number > len(pdf):
            raise HTTPException(404, "Page not found.")
        page = pdf[page_number - 1]
        scale = min(4, 3200 / max(page.rect.width, page.rect.height))
        image = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).tobytes(
            "png"
        )
    return Response(
        image, media_type="image/png", headers={"Cache-Control": "no-store"}
    )

@router.get("/api/documents/{doc_id}/evidence/{revision}/{image_id}")
def document_evidence(
    doc_id: str, revision: str, image_id: str, user=Depends(current_user)
):
    with SessionLocal() as db:
        d = authorized(db, Document, doc_id, user)
        from app.field_evidence import evidence_images

        items = evidence_images(d.validation)
        item = next(
            (
                e
                for e in items
                if e.get("available")
                and e.get("revision") == revision
                and e.get("storage_key", "").endswith(
                    "/" + revision + "-" + image_id + ".png"
                )
            ),
            None,
        )
        if not item:
            raise HTTPException(
                404, "Evidence not available for this extraction revision."
            )
    return Response(
        store().read(item["storage_key"]),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )
