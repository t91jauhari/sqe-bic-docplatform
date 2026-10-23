"""Documents application operations.

Transactions, authorization, audit and pinned configuration remain one unit.
"""

from app.errors import ApplicationError
from app.configuration.repository import get_revision
from app.configuration.profiles import profile_schema, validate_shape
import copy
import re
from sqlalchemy import select
from app.db import Case, Document, SessionLocal
from app.auditing import audit
from app.case_lifecycle import enqueue, refresh_case
from app.access import authorized, scoped
from app.contracts import (
    ClassificationInput,
    CorrectionInput,
    EffectiveCorrectionInput,
    MoveInput,
    ReconcileInput,
    SpiderResubmit,
)


def spider_resubmit(*, doc_id: str, data: SpiderResubmit, user):
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
        if stage.startswith("fields_"):
            raise ApplicationError(
                "conflict",
                "This is a failed field reread. Resume its field request instead of resubmitting the whole document.",
            )
        if (
            d.status != "ERROR"
            or not (
                stage in {"classify", "extract"}
                or re.fullmatch("extract_page_([1-9]|1[0-9]|20)", stage)
            )
            or (not (pending.startswith("spider_") or cached_key))
            or (not data.accept_possible_duplicate_charge)
        ):
            raise ApplicationError(
                "conflict",
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


def failure_summary(*, since: float, user):
    """Group recent document errors by their first-line prefix so the UI can
    surface transient-failure clusters (e.g. one network outage failing many
    uploads). Read-only and org-scoped via `authorized`/scoped queries."""
    since = max(0.0, float(since or 0))
    with SessionLocal() as db:
        query = scoped(select(Document), Document, user).where(
            Document.error != "", Document.created_at >= since
        )
        rows = db.scalars(query).all()
        grouped: dict[str, dict] = {}
        for d in rows:
            prefix = " ".join((d.error or "").split()[:8]) or "Unknown error"
            entry = grouped.setdefault(
                prefix,
                {
                    "error_prefix": prefix,
                    "count": 0,
                    "case_ids": [],
                    "first_seen": d.created_at,
                },
            )
            entry["count"] += 1
            if d.case_id not in entry["case_ids"]:
                entry["case_ids"].append(d.case_id)
            entry["first_seen"] = min(entry["first_seen"], d.created_at)
        return sorted(grouped.values(), key=lambda g: -g["count"])


def retry_document(*, doc_id: str, user):
    with SessionLocal.begin() as db:
        d = authorized(db, Document, doc_id, user)
        if d.status not in {"ERROR", "NEEDS_CLASSIFICATION"}:
            raise ApplicationError("conflict", "Document is not waiting for retry.")
        if d.provider_state.get("pending_create"):
            if str(d.provider_state["pending_create"]).startswith("spider_fields_"):
                raise ApplicationError(
                    "conflict",
                    "Resume the failed field request instead of retrying the whole document.",
                )
            from app.spider_failures import confirmed_connection_rejection

            rejection = confirmed_connection_rejection(d.provider_state)
            if not rejection:
                raise ApplicationError(
                    "conflict",
                    "Reconcile the uncertain provider submission before retrying.",
                )
            audit(
                db,
                d.org,
                user.id,
                "spider.connection_rejection_reconciled",
                d.branch_id,
                d.case_id,
                document_id=d.id,
                pending_stage=d.provider_state["pending_create"],
            )
            d.provider_state = {**d.provider_state, "pending_create": None}
        if d.status == "NEEDS_CLASSIFICATION":
            raise ApplicationError("conflict", "Confirm document type before retrying.")
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


def confirm_type(*, doc_id: str, data: ClassificationInput, user):
    with SessionLocal.begin() as db:
        d = authorized(db, Document, doc_id, user)
        if d.status not in {"NEEDS_CLASSIFICATION", "ERROR"} or d.raw:
            raise ApplicationError(
                "conflict", "Type can only be assigned before extraction."
            )
        cfg = get_revision(db, db.get(Case, d.case_id).config_id).payload
        if data.doc_type not in cfg["profiles"]:
            raise ApplicationError("invalid_input", "Unknown profile.")
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
            d.provider_state = {
                k: v
                for (k, v) in d.provider_state.items()
                if k
                not in {"parse_job_id", "extract_job_id", "spider_extract_response_key"}
                and (not re.fullmatch("spider_extract_page_\\d+_response_key", k))
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


def correct_field(*, doc_id: str, data: CorrectionInput, user):
    from validation import check_schema

    with SessionLocal.begin() as db:
        d = authorized(db, Document, doc_id, user)
        if d.status != "COMPLETED":
            raise ApplicationError("conflict", "Wait for document completion.")
        if data.field not in d.raw:
            raise ApplicationError("invalid_input", "Unknown field.")
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
            raise ApplicationError(
                "invalid_input", "Value does not match this field's extraction schema."
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


def correct_effective_field(*, doc_id: str, data: EffectiveCorrectionInput, user):
    from app.effective_corrections import extraction_value
    from app.provider import validate_extraction
    from validation import check_schema

    with SessionLocal.begin() as db:
        d = authorized(db, Document, doc_id, user)
        db.scalar(select(Document).where(Document.id == d.id).with_for_update())
        if d.status != "COMPLETED":
            raise ApplicationError(
                "conflict", "Wait for document completion or revalidation."
            )
        if data.field not in d.raw or data.field not in d.normalized:
            raise ApplicationError("invalid_input", "Unknown effective field.")
        before = d.normalized[data.field]
        if before != data.expected_value:
            raise ApplicationError(
                "conflict", "The effective value changed. Refresh before correcting it."
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
            raise ApplicationError("invalid_input", str(exc)) from exc
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


def move_document(*, doc_id: str, data: MoveInput, user):
    with SessionLocal.begin() as db:
        d = authorized(db, Document, doc_id, user)
        target = authorized(db, Case, data.case_id, user)
        if d.status not in {"COMPLETED", "ERROR", "NEEDS_CLASSIFICATION"}:
            raise ApplicationError(
                "conflict", "Wait until processing stops before moving."
            )
        if d.branch_id != target.branch_id:
            raise ApplicationError(
                "invalid_input", "Move documents only within the same branch."
            )
        if db.get(Case, d.case_id).config_id != target.config_id:
            raise ApplicationError(
                "invalid_input",
                "Case configurations differ; reprocessing migration is required.",
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


def reconcile(*, doc_id: str, data: ReconcileInput, user):
    with SessionLocal.begin() as db:
        d = authorized(db, Document, doc_id, user)
        if d.status != "ERROR" or d.provider_state.get("pending_create") != data.stage:
            raise ApplicationError(
                "conflict",
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
