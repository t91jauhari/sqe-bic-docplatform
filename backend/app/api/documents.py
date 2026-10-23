"""Documents HTTP boundary."""
from fastapi import APIRouter
from app.configuration.repository import get_revision
from app.configuration.profiles import profile_schema, validate_shape
import copy
import re
from fastapi import Depends, HTTPException, Response
from sqlalchemy import select
from app.db import Case, Document, SessionLocal
from app.domain import audit, enqueue, refresh_case
from app.security import authorized, current_user, scoped
from app.storage import original_key, store, sniff_mime
from app.api.dependencies import ADMIN, REVIEW, WRITE
from app.api.contracts import ClassificationInput, CorrectionInput, EffectiveCorrectionInput, MoveInput, ReconcileInput, SpiderResubmit

router = APIRouter(tags=['documents'])

@router.post("/api/documents/{doc_id}/spider-resubmit", status_code=202)
def spider_resubmit(doc_id: str, data: SpiderResubmit, user=Depends(WRITE)):
    with SessionLocal.begin() as db:
        d = authorized(db, Document, doc_id, user)
        pending = str(d.provider_state.get("pending_create") or "")
        stage = (
            pending.removeprefix("spider_")
            if pending.startswith("spider_")
            else str(d.provider_state.get("provider_stage", ""))
            .removeprefix("SPIDER_")
            .lower()
        )
        cached_key = d.provider_state.get(f"spider_{stage}_response_key")
        if stage.startswith('fields_'):
            raise HTTPException(409,'This is a failed field reread. Resume its field request instead of resubmitting the whole document.')
        if (
            d.status != "ERROR"
            or not (
                stage in {"classify", "extract"}
                or re.fullmatch(r"extract_page_([1-9]|1[0-9]|20)", stage)
            )
            or not (pending.startswith("spider_") or cached_key)
            or not data.accept_possible_duplicate_charge
        ):
            raise HTTPException(
                409,
                "Only uncertain or cached failed Spider-AI submissions can be explicitly resubmitted.",
            )
        state = {**d.provider_state, "pending_create": None}
        state.pop(f"spider_{stage}_response_key", None)
        d.provider_state = state
        if stage.startswith("extract"):
            d.raw = {}
            d.metadata_json = {}
        job = enqueue(db, d)
        audit(
            db,
            user.org,
            user.id,
            "spider.resubmission_authorized",
            d.branch_id,
            d.case_id,
            document_id=d.id,
            reason=data.reason,
            duplicate_charge_accepted=True,
            stage=stage,
            previous_response_key=cached_key,
        )
        db.flush()
        return {"job_id": job.id}

@router.get("/api/documents/failure-summary")
def failure_summary(since: float = 0, user=Depends(current_user)):
    """Group recent document errors by their first-line prefix so the UI can
    surface transient-failure clusters (e.g. one network outage failing many
    uploads). Read-only and org-scoped via `authorized`/scoped queries."""
    since = max(0.0, float(since or 0))
    with SessionLocal() as db:
        query = scoped(select(Document), Document, user).where(
            Document.error != "",
            Document.created_at >= since,
        )
        rows = db.scalars(query).all()
        grouped: dict[str, dict] = {}
        for d in rows:
            prefix = " ".join((d.error or "").split()[:8]) or "Unknown error"
            entry = grouped.setdefault(
                prefix,
                {"error_prefix": prefix, "count": 0, "case_ids": [], "first_seen": d.created_at},
            )
            entry["count"] += 1
            if d.case_id not in entry["case_ids"]:
                entry["case_ids"].append(d.case_id)
            entry["first_seen"] = min(entry["first_seen"], d.created_at)
        return sorted(grouped.values(), key=lambda g: -g["count"])

@router.get("/api/documents/{doc_id}/file")
def document_file(doc_id: str, user=Depends(current_user)):
    with SessionLocal() as db:
        d = authorized(db, Document, doc_id, user)
    data = store().read(original_key(d))
    return Response(
        data,
        media_type=sniff_mime(data),
        headers={"Content-Disposition": "inline", "Cache-Control": "no-store"},
    )

@router.post("/api/documents/{doc_id}/retry", status_code=202)
def retry_document(doc_id: str, user=Depends(WRITE)):
    with SessionLocal.begin() as db:
        d = authorized(db, Document, doc_id, user)
        if d.status not in {"ERROR", "NEEDS_CLASSIFICATION"}:
            raise HTTPException(409, "Document is not waiting for retry.")
        if d.provider_state.get("pending_create"):
            if str(d.provider_state['pending_create']).startswith('spider_fields_'):
                raise HTTPException(409,'Resume the failed field request instead of retrying the whole document.')
            from app.spider_failures import confirmed_connection_rejection
            rejection=confirmed_connection_rejection(d.provider_state)
            if not rejection:raise HTTPException(409, "Reconcile the uncertain provider submission before retrying.")
            audit(db,d.org,user.id,'spider.connection_rejection_reconciled',d.branch_id,d.case_id,document_id=d.id,pending_stage=d.provider_state['pending_create'])
            d.provider_state={**d.provider_state,'pending_create':None}
        if d.status == "NEEDS_CLASSIFICATION":
            raise HTTPException(409, "Confirm document type before retrying.")
        job = enqueue(db, d)
        audit(
            db,
            user.org,
            user.id,
            "document.retry_requested",
            d.branch_id,
            d.case_id,
            document_id=d.id,
        )
        db.flush()
        return {"job_id": job.id}

@router.post("/api/documents/{doc_id}/classification", status_code=202)
def confirm_type(doc_id: str, data: ClassificationInput, user=Depends(REVIEW)):
    with SessionLocal.begin() as db:
        d = authorized(db, Document, doc_id, user)
        if d.status not in {"NEEDS_CLASSIFICATION", "ERROR"} or d.raw:
            raise HTTPException(409, "Type can only be assigned before extraction.")
        cfg = get_revision(db, db.get(Case, d.case_id).config_id).payload
        if data.doc_type not in cfg["profiles"]:
            raise HTTPException(422, "Unknown profile.")
        before = d.doc_type
        d.doc_type = data.doc_type
        d.classification = {
            **d.classification,
            "manual": True,
            "type": data.doc_type,
            "confirmed": True,
            "reviewer": user.id,
            "reason": data.reason,
        }
        if before != d.doc_type:
            # An already-created specialized parse belongs to its old profile.
            d.provider_state = {
                k: v
                for k, v in d.provider_state.items()
                if k
                not in {"parse_job_id", "extract_job_id", "spider_extract_response_key"}
                and not re.fullmatch(r"spider_extract_page_\d+_response_key", k)
            }
        enqueue(db, d)
        audit(
            db,
            user.org,
            user.id,
            "document.classification_confirmed",
            d.branch_id,
            d.case_id,
            document_id=d.id,
            reason=data.reason,
            type=data.doc_type,
        )
        return {"ok": True}

@router.post("/api/documents/{doc_id}/corrections", status_code=202)
def correct_field(doc_id: str, data: CorrectionInput, user=Depends(REVIEW)):
    from validation import check_schema

    with SessionLocal.begin() as db:
        d = authorized(db, Document, doc_id, user)
        if d.status != "COMPLETED":
            raise HTTPException(409, "Wait for document completion.")
        if data.field not in d.raw:
            raise HTTPException(422, "Unknown field.")
        effective = copy.deepcopy(d.raw)
        effective.update(d.overrides)
        effective[data.field] = data.value
        cfg = get_revision(db, db.get(Case, d.case_id).config_id).payload
        try:
            if cfg.get("provider") != "spider-ai":
                if cfg["profiles"][d.doc_type].get("validation_adapter") == "schema":
                    validate_shape(effective, profile_schema(cfg, d.doc_type))
                else:
                    check_schema(effective, profile_schema(cfg, d.doc_type))
        except ValueError:
            raise HTTPException(
                422, "Value does not match this field's extraction schema."
            )
        previous = d.overrides.get(data.field, d.raw[data.field])
        d.overrides = {**d.overrides, data.field: data.value}
        enqueue(db, d, "revalidate")
        audit(
            db,
            user.org,
            user.id,
            "document.field_corrected",
            d.branch_id,
            d.case_id,
            document_id=d.id,
            field=data.field,
            before=previous,
            after=data.value,
            reason=data.reason,
        )
        return {"ok": True}

@router.post("/api/documents/{doc_id}/effective-corrections", status_code=202)
def correct_effective_field(
    doc_id: str, data: EffectiveCorrectionInput, user=Depends(REVIEW)
):
    from app.effective_corrections import extraction_value
    from app.provider import validate_extraction
    from validation import check_schema

    with SessionLocal.begin() as db:
        d = authorized(db, Document, doc_id, user)
        db.scalar(select(Document).where(Document.id == d.id).with_for_update())
        if d.status != "COMPLETED":
            raise HTTPException(409, "Wait for document completion or revalidation.")
        if data.field not in d.raw or data.field not in d.normalized:
            raise HTTPException(422, "Unknown effective field.")
        before = d.normalized[data.field]
        if before != data.expected_value:
            raise HTTPException(
                409, "The effective value changed. Refresh before correcting it."
            )
        cfg = get_revision(db, db.get(Case, d.case_id).config_id).payload
        try:
            replacement = (
                data.value
                if cfg.get("provider") == "spider-ai"
                else extraction_value(
                    data.field,
                    data.value,
                    d.overrides.get(data.field, d.raw[data.field]),
                    cfg["profiles"][d.doc_type]["policy"],
                )
            )
            effective = {**copy.deepcopy(d.raw), **d.overrides, data.field: replacement}
            if cfg.get("provider") != "spider-ai":
                if cfg["profiles"][d.doc_type].get("validation_adapter") == "schema":
                    validate_shape(effective, profile_schema(cfg, d.doc_type))
                else:
                    check_schema(effective, profile_schema(cfg, d.doc_type))
            from types import SimpleNamespace

            candidate = SimpleNamespace(
                doc_type=d.doc_type,
                overrides={**d.overrides, data.field: replacement},
                provider_state=d.provider_state,
            )
            preview = validate_extraction(
                candidate,
                cfg,
                {
                    "extract_result": d.raw,
                    "extract_metadata": d.metadata_json,
                    "id": d.provider_state.get("extract_job_id"),
                },
            )
            after = preview["normalized"].get(data.field)
            if after == before:
                raise ValueError(
                    "This edit does not change the effective value. Computed fields must be corrected through their source inputs."
                )
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(422, str(exc)) from exc
        d.overrides = candidate.overrides
        enqueue(db, d, "revalidate")
        audit(
            db,
            d.org,
            user.id,
            "document.effective_value_corrected",
            d.branch_id,
            d.case_id,
            document_id=d.id,
            field=data.field,
            before=before,
            requested=data.value,
            validated_preview=after,
            reason=data.reason,
        )
        return {"queued": True, "normalized_preview": after}

@router.post("/api/documents/{doc_id}/move")
def move_document(doc_id: str, data: MoveInput, user=Depends(REVIEW)):
    with SessionLocal.begin() as db:
        d = authorized(db, Document, doc_id, user)
        target = authorized(db, Case, data.case_id, user)
        if d.status not in {"COMPLETED", "ERROR", "NEEDS_CLASSIFICATION"}:
            raise HTTPException(409, "Wait until processing stops before moving.")
        if d.branch_id != target.branch_id:
            raise HTTPException(422, "Move documents only within the same branch.")
        if db.get(Case, d.case_id).config_id != target.config_id:
            raise HTTPException(
                422, "Case configurations differ; reprocessing migration is required."
            )
        old = d.case_id
        d.case_id = target.id
        db.flush()
        refresh_case(db, old)
        refresh_case(db, target.id)
        audit(
            db,
            user.org,
            user.id,
            "document.moved",
            d.branch_id,
            target.id,
            document_id=d.id,
            from_case=old,
            reason=data.reason,
        )
        return {"ok": True}

@router.post("/api/documents/{doc_id}/reconcile", status_code=202)
def reconcile(doc_id: str, data: ReconcileInput, user=Depends(ADMIN)):
    with SessionLocal.begin() as db:
        d = authorized(db, Document, doc_id, user)
        if d.status != "ERROR" or d.provider_state.get("pending_create") != data.stage:
            raise HTTPException(
                409,
                "This document does not have an uncertain submission for that stage.",
            )
        d.provider_state = {
            **d.provider_state,
            data.stage: data.provider_id,
            "pending_create": None,
        }
        enqueue(db, d)
        audit(
            db,
            user.org,
            user.id,
            "provider.submission_reconciled",
            d.branch_id,
            d.case_id,
            document_id=d.id,
            stage=data.stage,
            provider_id=data.provider_id,
            reason=data.reason,
        )
        return {"ok": True}
