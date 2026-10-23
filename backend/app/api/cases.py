"""Cases HTTP boundary."""
from fastapi import APIRouter
from app.configuration.repository import get_revision
import copy
import json
import time
from fastapi import Depends, HTTPException
from sqlalchemy import func, select
from app.db import Audit, Case, CaseTask, CaseContext, CaseRun, Document, Job, Report, SessionLocal, User
from app.domain import audit, enqueue, latest_config, refresh_case
from app.security import authorized, current_user, scoped
from app.api.dependencies import REVIEW, WRITE
from app.api.contracts import ContextInput, EnumRevalidationInput, FindingReview, TaskAssignment
from app.api.views import case_view, doc_view

router = APIRouter(tags=['cases'])

@router.get("/api/cases")
def cases(
    q: str = "",
    status: str = "",
    transaction_flow: str = "",
    offset: int = 0,
    limit: int = 50,
    user=Depends(current_user),
):
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    with SessionLocal() as db:
        query = scoped(select(Case), Case, user)
        if not status:
            query = query.where(Case.status != "MERGED")
        if transaction_flow:
            query = query.where(Case.template == transaction_flow)
        if q:
            query = query.where(Case.customer.ilike("%" + q[:100] + "%"))
        if status:
            query = query.where(Case.status == status)
        count = db.scalar(select(func.count()).select_from(query.subquery()))
        return {
            "total": count,
            "items": [
                case_view(c, db)
                for c in db.scalars(
                    query.order_by(Case.updated_at.desc()).offset(offset).limit(limit)
                )
            ],
        }

@router.get("/api/cases/{case_id}")
def case_detail(case_id: str, user=Depends(current_user)):
    with SessionLocal() as db:
        c = authorized(db, Case, case_id, user)
        docs = db.scalars(
            select(Document)
            .where(Document.case_id == c.id)
            .order_by(Document.created_at)
        ).all()
        reports = db.scalars(
            select(Report).where(Report.case_id == c.id).order_by(Report.version.desc())
        ).all()
        events = db.scalars(
            select(Audit)
            .where(Audit.case_id == c.id)
            .order_by(Audit.created_at.desc())
            .limit(100)
        ).all()
        return {
            **case_view(c, db),
            "context_suggestions": __import__(
                "app.case_context", fromlist=["suggestions"]
            ).suggestions(docs),
            "case_context": (
                db.scalar(
                    select(CaseContext).where(CaseContext.case_id == c.id)
                ).payload
                if db.scalar(select(CaseContext).where(CaseContext.case_id == c.id))
                else {}
            ),
            "sop_runs": [
                {
                    "id": run.id,
                    "status": run.status,
                    "stage": run.stage,
                    "error": run.error,
                    "snapshot_hash": run.fingerprint,
                    "created_at": run.created_at,
                }
                for run in db.scalars(
                    select(CaseRun)
                    .where(CaseRun.case_id == c.id)
                    .order_by(CaseRun.created_at.desc())
                    .limit(10)
                )
            ],
            "documents": [doc_view(d) for d in docs],
            "reports": [
                {
                    "id": r.id,
                    "version": r.version,
                    "state": r.state,
                    "created_at": r.created_at,
                    "approved_by": r.approved_by,
                    "snapshot": {
                        key: r.snapshot.get(key)
                        for key in [
                            "findings",
                            "missing",
                            "validation_status",
                            "provider",
                            "customer",
                            "config_version",
                            "scores",
                            "sop_summary",
                            "sop_packages",
                            "technical_findings",
                        ]
                    },
                }
                for r in reports
            ],
            "timeline": [
                {
                    "id": e.id,
                    "event": e.event,
                    "actor": e.actor,
                    "created_at": e.created_at,
                    "details": e.details,
                }
                for e in events
            ],
            "can_write": user.role not in {"auditor"},
            "can_review": user.role in {"bank_admin", "branch_admin", "reviewer"},
            "maker_checker": get_revision(db, c.config_id).payload["maker_checker"],
        }

@router.put("/api/cases/{case_id}/context")
def edit_case_context(case_id: str, data: ContextInput, user=Depends(WRITE)):
    from app.configuration.contexts import validate_values
    with SessionLocal.begin() as db:
        case = authorized(db, Case, case_id, user)
        config = get_revision(db, case.config_id)
        family = config.payload["templates"][case.template].get("document_family", "forex")
        try:
            validate_values(config.payload, data.values, family=family,
                            document_lookup=lambda identifier: db.get(Document, identifier), case_id=case.id)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        item = db.scalar(
            select(CaseContext).where(CaseContext.case_id == case.id).with_for_update()
        )
        if not item:
            item = CaseContext(
                org=case.org, branch_id=case.branch_id, case_id=case.id, payload={}
            )
            db.add(item)
        previous = item.payload
        item.payload = {
            **previous,
            **data.values,
            "annotation": {
                "actor": user.id,
                "reason": data.reason,
                "evidence": data.evidence,
                "at": time.time(),
            },
            "rule_reviews": {},
        }
        audit(
            db,
            case.org,
            user.id,
            "case.context_corrected",
            case.branch_id,
            case.id,
            before=previous,
            after=item.payload,
        )
        refresh_case(db, case.id)
        return {"queued": True}

@router.post("/api/cases/{case_id}/sop-rerun", status_code=202)
def rerun_sop(case_id: str, user=Depends(WRITE)):
    from app.case_processing import queue_case

    with SessionLocal.begin() as db:
        case = authorized(db, Case, case_id, user)
        for run in db.scalars(
            select(CaseRun).where(CaseRun.case_id == case.id, CaseRun.status == "ERROR")
        ):
            run.status = "QUEUED"
            run.error = ""
            run.lease_until = 0
        queue_case(db, case.id)
        audit(db, case.org, user.id, "sop.rerun_requested", case.branch_id, case.id)
        return {
            "queued": True,
            "note": "Uses stored extraction and pinned rules. No cloud jobs.",
        }

@router.post("/api/cases/{case_id}/sop-review", status_code=202)
def review_sop(case_id: str, data: FindingReview, user=Depends(REVIEW)):
    if data.result not in {"PASS", "FAIL"}:
        raise HTTPException(422, "Review result must be PASS or FAIL.")
    with SessionLocal.begin() as db:
        case = authorized(db, Case, case_id, user)
        report = db.scalar(
            select(Report)
            .where(Report.case_id == case.id)
            .order_by(Report.version.desc())
            .limit(1)
        )
        finding = (
            next(
                (
                    f
                    for f in report.snapshot["findings"]
                    if f["rule_id"] == data.rule_id
                ),
                None,
            )
            if report
            else None
        )
        if data.report_id and (not report or report.id != data.report_id):
            raise HTTPException(409, "The SOP report changed. Reload the check and inspect the latest evidence before saving.")

        from app.case_processing import fingerprint, inputs

        if (
            report
            and "configuration" in report.snapshot
            and fingerprint(inputs(db, case)) != report.fingerprint
        ):
            raise HTTPException(
                409,
                "Case inputs changed. Wait for the latest SOP report before review.",
            )
        if not finding or finding["result"] != "REVIEW" or finding.get("evaluation_type") != "VISUAL" or not finding.get("eligible"):
            raise HTTPException(
                409, "Only unresolved eligible findings can be reviewed."
            )
        docs = {
            d.id: d
            for d in db.scalars(select(Document).where(Document.case_id == case.id))
        }
        for o in data.observations:
            if (
                o.get("document_id") not in docs
                or type(o.get("page")) is not int
                or o["page"] < 1
                or not isinstance(o.get("region"), str)
                or len(o["region"]) < 3
            ):
                raise HTTPException(
                    422,
                    "Each observation needs a case document, 1-based page and visible region description.",
                )
        cfg = get_revision(db, case.config_id)
        rule = next(
            (r for r in cfg.payload.get("sop_rules", []) if r["id"] == data.rule_id),
            None,
        )
        related = set(
            finding.get("evidence", {}).get("document_ids", [])
            + finding.get("evidence", {}).get("reference_document_ids", [])
        )
        if related and any(o["document_id"] not in related for o in data.observations):
            raise HTTPException(
                422, "Evidence must reference the documents used by this finding."
            )
        if (
            rule
            and (
                rule["operator"] == "signature_visual_consistency"
                or rule["operator"] == "account_check"
                and json.loads(rule["comparison_policy"]).get("require_two_signatures")
            )
            and data.result == "PASS"
        ):
            if (
                not related
                or {o["document_id"] for o in data.observations} != related
                or len(related) < 2
            ):
                raise HTTPException(
                    422,
                    "Signature consistency needs reviewed observations from both document signing regions.",
                )
        if cfg.payload["maker_checker"] and case.created_by == user.id:
            raise HTTPException(
                403, "A different reviewer must record this finding review."
            )
        item = db.scalar(
            select(CaseContext).where(CaseContext.case_id == case.id).with_for_update()
        )
        if not item:
            item = CaseContext(
                org=case.org, branch_id=case.branch_id, case_id=case.id, payload={}
            )
            db.add(item)
        item.payload = {
            **item.payload,
            "rule_reviews": {
                **item.payload.get("rule_reviews", {}),
                data.rule_id: {
                    "result": data.result,
                    "reason": data.reason,
                    "observations": data.observations,
                    "document_basis": fingerprint(
                        {
                            "documents": report.snapshot["documents"],
                            "config_id": report.snapshot["config_id"],
                        }
                    ),
                    "actor": user.id,
                    "at": time.time(),
                },
            },
        }
        audit(
            db,
            case.org,
            user.id,
            "sop.finding_reviewed",
            case.branch_id,
            case.id,
            **data.model_dump(),
        )
        refresh_case(db, case.id)
        return {"queued": True}

@router.post("/api/cases/{case_id}/retry-documents", status_code=202)
def retry_case_documents(case_id: str, user=Depends(WRITE)):
    # Bulk per-document retry: re-queue every document in the case that can be
    # safely re-processed, regardless of its current status (ERROR, COMPLETED,
    # QUEUED, etc.). Documents with an uncertain provider submission
    # (pending_create) are skipped and must be reconciled individually first,
    # since re-submitting them could create a duplicate paid job at the provider.
    # enqueue() deduplicates against in-flight jobs, so re-queueing a document
    # that is already QUEUED/DISPATCHED/RUNNING returns the existing job.
    with SessionLocal.begin() as db:
        case = authorized(db, Case, case_id, user)
        queued = []
        skipped = []
        for d in db.scalars(select(Document).where(Document.case_id == case.id)):
            if d.provider_state.get("pending_create"):
                skipped.append(
                    {
                        "id": d.id,
                        "filename": d.filename,
                        "reason": "uncertain provider submission — reconcile first",
                    }
                )
                continue
            job = enqueue(db, d)
            queued.append({"id": d.id, "filename": d.filename, "job_id": job.id})
        audit(
            db,
            case.org,
            user.id,
            "case.documents_retry_requested",
            case.branch_id,
            case.id,
        )
        db.flush()
        return {"queued": queued, "skipped": skipped}

@router.get("/api/cases/{case_id}/assignment")
def case_assignment(case_id: str, user=Depends(current_user)):
    with SessionLocal() as db:
        c = authorized(db, Case, case_id, user)
        task = db.scalar(
            select(CaseTask).where(CaseTask.case_id == c.id, CaseTask.org == user.org)
        )
        candidates = [
            u
            for u in db.scalars(
                select(User).where(User.org == user.org, User.active.is_(True))
            )
            if u.role == "bank_admin" or c.branch_id in u.branches
        ]
        return {
            "assigned_to": task.assigned_to if task else None,
            "due_at": task.due_at if task else None,
            "candidates": [{"id": u.id, "name": u.name} for u in candidates],
            "can_edit": user.role in {"bank_admin", "branch_admin", "reviewer"},
        }

@router.put("/api/cases/{case_id}/assignment")
def assign_case(case_id: str, data: TaskAssignment, user=Depends(REVIEW)):
    with SessionLocal.begin() as db:
        c = authorized(db, Case, case_id, user)
        if data.assigned_to:
            target = db.get(User, data.assigned_to)
            if (
                not target
                or not target.active
                or target.org != user.org
                or (target.role != "bank_admin" and c.branch_id not in target.branches)
            ):
                raise HTTPException(422, "Assignee must have access to this branch.")
        task = db.scalar(
            select(CaseTask).where(CaseTask.case_id == c.id, CaseTask.org == user.org)
        )
        if not task:
            task = CaseTask(
                org=user.org, branch_id=c.branch_id, case_id=c.id, assigned_by=user.id
            )
            db.add(task)
        task.assigned_to, task.due_at, task.assigned_by = (
            data.assigned_to,
            data.due_at,
            user.id,
        )
        audit(
            db,
            user.org,
            user.id,
            "case.assignment_updated",
            c.branch_id,
            c.id,
            assigned_to=data.assigned_to,
            due_at=data.due_at,
        )
    return {"saved": True}

@router.post("/api/cases/{case_id}/revalidate-enum-aliases", status_code=202)
def revalidate_enum_aliases(
    case_id: str, data: EnumRevalidationInput, user=Depends(REVIEW)
):
    from app.enum_aliases import validate_aliases

    with SessionLocal.begin() as db:
        case = authorized(db, Case, case_id, user)
        documents = db.scalars(
            select(Document).where(Document.case_id == case.id)
        ).all()
        if any(
            d.status
            in {
                "QUEUED",
                "PROCESSING",
                "CLASSIFYING",
                "PARSING",
                "EXTRACTING",
                "VALIDATING",
            }
            for d in documents
        ) or db.scalar(
            select(Job).where(
                Job.document_id.in_([d.id for d in documents]),
                Job.status.in_(["QUEUED", "DISPATCHED", "RUNNING"]),
            )
        ):
            raise HTTPException(409, "Wait for case processing to finish.")
        targets = [
            d
            for d in documents
            if d.doc_type == "ektp" and d.status == "COMPLETED" and d.raw
        ]
        if not targets:
            raise HTTPException(422, "No completed eKTP extraction is available.")
        old = get_revision(db, case.config_id)
        latest = latest_config(db, user.org)
        payload = copy.deepcopy(old.payload)
        policy = payload["profiles"]["ektp"]["policy"]
        policy["enum_aliases"] = copy.deepcopy(
            latest.payload["profiles"]["ektp"]["policy"].get("enum_aliases", {})
        )
        policy["enum_raw_fallback_fields"] = copy.deepcopy(
            latest.payload["profiles"]["ektp"]["policy"].get(
                "enum_raw_fallback_fields", ["religion"]
            )
        )
        try:
            validate_aliases(policy)
            targets_in_policy = set(policy['enum_aliases']) | set(policy['enum_raw_fallback_fields'])
            if not targets_in_policy or targets_in_policy - set(payload['profiles']['ektp']['schema']['properties']):
                raise ValueError('Choose an approved enum policy for fields present in this document profile before revalidation.')
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        aliases = copy.deepcopy(policy["enum_aliases"])
        for d in targets:
            d.provider_state = {
                **d.provider_state,
                "normalization_enum_aliases": aliases,
                "normalization_enum_raw_fallback_fields": policy[
                    "enum_raw_fallback_fields"
                ],
                "normalization_source_config_id": latest.id,
            }
            enqueue(db, d, "revalidate")
        audit(
            db,
            user.org,
            user.id,
            "case.enum_aliases_revalidated",
            case.branch_id,
            case.id,
            config_id=old.id,
            source_config_id=latest.id,
            reason=data.reason,
            enum_aliases=aliases,
        )
        return {"queued": len(targets)}
