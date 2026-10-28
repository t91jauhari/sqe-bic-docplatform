"""Cases application operations.

Transactions, authorization, audit and pinned configuration remain one unit.
"""

from app.errors import ApplicationError
from app.configuration.repository import get_revision
import copy
import json
import time
from sqlalchemy import func, select
from app.db import (
    Audit,
    Case,
    CaseTask,
    CaseContext,
    CaseRun,
    Document,
    Job,
    Config,
    Report,
    SessionLocal,
    User,
)
from app.auditing import audit
from app.case_lifecycle import enqueue, refresh_case
from app.configuration.revisions import latest_config
from app.access import authorized, scoped
from app.contracts import (
    ContextInput,
    EnumRevalidationInput,
    FindingReview,
    TaskAssignment,
)
from collections import OrderedDict
from app.projections import case_view, case_views, doc_view

_REPORT_DETAIL_KEYS = (
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
)
_MAX_CASE_REPORT_CACHE = 512


def _case_report_snapshots(db, report_meta):
    if not report_meta:
        return {}
    clean = not (db.new or db.dirty or db.deleted)
    bind = db.get_bind()
    cache = getattr(bind, "_sqe_case_report_cache", None) if clean else None
    if clean and cache is None:
        cache = OrderedDict()
        setattr(bind, "_sqe_case_report_cache", cache)
    result = {}
    missing_ids = []
    for r_id, _, _, _, _, fp in report_meta:
        key = (r_id, fp)
        if cache is not None and key in cache:
            cache.move_to_end(key)
            result[r_id] = cache[key]
        else:
            missing_ids.append(r_id)
    if missing_ids:
        for r_id, fp, snap in db.execute(
            select(Report.id, Report.fingerprint, Report.snapshot).where(
                Report.id.in_(missing_ids)
            )
        ):
            projected = {k: snap.get(k) for k in _REPORT_DETAIL_KEYS}
            result[r_id] = projected
            if cache is not None:
                cache[(r_id, fp)] = projected
                cache.move_to_end((r_id, fp))
                while len(cache) > _MAX_CASE_REPORT_CACHE:
                    cache.popitem(last=False)
    return result


def cases(*, q: str, status: str, transaction_flow: str, offset: int, limit: int, user):
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
        rows = db.scalars(
            query.order_by(Case.updated_at.desc()).offset(offset).limit(limit)
        ).all()
        return {
            "total": count,
            "items": case_views(rows, db),
        }


def case_detail(*, case_id: str, user):
    with SessionLocal() as db:
        c = authorized(db, Case, case_id, user)
        docs = db.scalars(
            select(Document)
            .where(Document.case_id == c.id)
            .order_by(Document.created_at)
        ).all()
        report_meta = db.execute(
            select(
                Report.id,
                Report.version,
                Report.state,
                Report.created_at,
                Report.approved_by,
                Report.fingerprint,
            )
            .where(Report.case_id == c.id)
            .order_by(Report.version.desc())
            .limit(1)
        ).all()
        report_snapshots = _case_report_snapshots(db, report_meta)
        events = db.scalars(
            select(Audit)
            .where(Audit.case_id == c.id)
            .order_by(Audit.created_at.desc())
            .limit(100)
        ).all()
        ctx_payload = db.scalar(
            select(CaseContext.payload).where(CaseContext.case_id == c.id)
        )
        if not ctx_payload or not any(k in ctx_payload for k in ("threshold_state", "customer_type", "payment_basis")):
            from app.case_context import ensure_case_context
            ctx_item = ensure_case_context(db, c.id)
            ctx_payload = ctx_item.payload if ctx_item else {}
        run_rows = db.execute(
            select(
                CaseRun.id,
                CaseRun.status,
                CaseRun.stage,
                CaseRun.error,
                CaseRun.fingerprint,
                CaseRun.created_at,
            )
            .where(CaseRun.case_id == c.id)
            .order_by(CaseRun.created_at.desc())
            .limit(10)
        ).all()
        rev = get_revision(db, c.config_id, copy_payload=False)
        doc_rows = [(d.doc_type, d.status) for d in docs]
        return {
            **case_view(c, db, doc_rows=doc_rows, rev=rev),
            "context_suggestions": __import__(
                "app.case_context", fromlist=["suggestions"]
            ).suggestions(docs),
            "case_context": ctx_payload if ctx_payload is not None else {},
            "sop_runs": [
                {
                    "id": r_id,
                    "status": r_status,
                    "stage": r_stage,
                    "error": r_error,
                    "snapshot_hash": r_fp,
                    "created_at": r_created_at,
                }
                for r_id, r_status, r_stage, r_error, r_fp, r_created_at in run_rows
            ],
            "documents": [doc_view(d) for d in docs],
            "reports": [
                {
                    "id": r_id,
                    "version": r_version,
                    "state": "FINAL",
                    "created_at": r_created_at,
                    "approved_by": r_approved_by,
                    "snapshot": report_snapshots[r_id],
                }
                for r_id, r_version, r_state, r_created_at, r_approved_by, _ in report_meta
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
            "can_adopt_configuration": user.role in {"bank_admin", "branch_admin"},
            "maker_checker": rev.payload["maker_checker"],
        }


def edit_case_context(*, case_id: str, data: ContextInput, user):
    from app.configuration.contexts import validate_values

    with SessionLocal.begin() as db:
        case = authorized(db, Case, case_id, user)
        config = get_revision(db, case.config_id)
        family = config.payload["templates"][case.template].get(
            "document_family", "forex"
        )
        try:
            validate_values(
                config.payload,
                data.values,
                family=family,
                document_lookup=lambda identifier: db.get(Document, identifier),
                case_id=case.id,
            )
        except ValueError as exc:
            raise ApplicationError("invalid_input", str(exc)) from exc
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


def rerun_sop(*, case_id: str, user):
    from app.case_processing import queue_case

    with SessionLocal.begin() as db:
        case = authorized(db, Case, case_id, user)
        for run in db.scalars(
            select(CaseRun).where(CaseRun.case_id == case.id, CaseRun.status == "ERROR")
        ):
            run.status = "QUEUED"
            run.error = ""
            run.lease_until = 0
        queue_case(db, case.id, force=True)
        audit(db, case.org, user.id, "sop.rerun_requested", case.branch_id, case.id)
        return {
            "queued": True,
            "note": "Uses stored extraction and pinned rules. No cloud jobs.",
        }


def review_sop(*, case_id: str, data: FindingReview, user):
    if data.result not in {"PASS", "FAIL"}:
        raise ApplicationError("invalid_input", "Review result must be PASS or FAIL.")
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
            raise ApplicationError(
                "conflict",
                "The SOP report changed. Reload the check and inspect the latest evidence before saving.",
            )
        from app.case_processing import fingerprint, inputs

        if (
            report
            and "configuration" in report.snapshot
            and (fingerprint(inputs(db, case)) != report.fingerprint)
        ):
            raise ApplicationError(
                "conflict",
                "Case inputs changed. Wait for the latest SOP report before review.",
            )
        if (
            not finding
            or finding["result"] != "REVIEW"
            or finding.get("evaluation_type") != "VISUAL"
            or (not finding.get("eligible"))
        ):
            raise ApplicationError(
                "conflict", "Only unresolved eligible findings can be reviewed."
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
                or (not isinstance(o.get("region"), str))
                or (len(o["region"]) < 3)
            ):
                raise ApplicationError(
                    "invalid_input",
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
        if related and any(
            (o["document_id"] not in related for o in data.observations)
        ):
            raise ApplicationError(
                "invalid_input",
                "Evidence must reference the documents used by this finding.",
            )
        policy = finding.get("evidence", {}).get("policy", {})
        # Historical findings store a policy label rather than a typed policy.
        if not isinstance(policy, dict):
            policy = {}
        if (
            policy.get("type") == "visual"
            and policy.get("check") == "consistency"
            and data.result == "PASS"
        ):
            observed = {
                (o["document_id"], o["page"], o["region"]) for o in data.observations
            }
            if (
                not related
                or {o["document_id"] for o in data.observations} != related
                or len(observed) < 2
            ):
                raise ApplicationError(
                    "invalid_input",
                    "Visual consistency requires separate observations of both source regions.",
                )
        if (
            rule
            and (
                rule["operator"] == "signature_visual_consistency"
                or (
                    rule["operator"] == "account_check"
                    and json.loads(rule["comparison_policy"]).get(
                        "require_two_signatures"
                    )
                )
            )
            and (data.result == "PASS")
        ):
            if (
                not related
                or {o["document_id"] for o in data.observations} != related
                or len(related) < 2
            ):
                raise ApplicationError(
                    "invalid_input",
                    "Signature consistency needs reviewed observations from both document signing regions.",
                )
        if cfg.payload["maker_checker"] and case.created_by == user.id:
            raise ApplicationError(
                "forbidden", "A different reviewer must record this finding review."
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
            **data.model_dump()
        )
        refresh_case(db, case.id)
        return {"queued": True}


def retry_case_documents(*, case_id: str, user, only_failed: bool = True):
    with SessionLocal.begin() as db:
        case = authorized(db, Case, case_id, user)
        # If case is bound to an obsolete configuration (e.g. removed 'llama' provider), upgrade to latest published config
        latest = latest_config(db, case.org)
        if latest and case.config_id != latest.id:
            curr_cfg = db.scalar(select(Config).where(Config.id == case.config_id))
            if not curr_cfg or (curr_cfg.payload and curr_cfg.payload.get('provider') == 'llama'):
                case.config_id = latest.id
        docs = db.scalars(select(Document).where(Document.case_id == case.id)).all()
        has_failed = any(d.status in {"ERROR", "FAILED"} for d in docs)
        queued = []
        skipped = []
        for d in docs:
            # If only_failed is true and some documents failed, protect completed documents so valid extractions are never lost
            if only_failed and has_failed and d.status == "COMPLETED" and d.raw:
                skipped.append(
                    {
                        "id": d.id,
                        "filename": d.filename,
                        "reason": "already completed with stored extraction",
                    }
                )
                continue
            if d.provider_state.get("pending_create"):
                skipped.append(
                    {
                        "id": d.id,
                        "filename": d.filename,
                        "reason": "uncertain provider submission — reconcile first",
                    }
                )
                continue
            # Reset extraction state while preserving storage location and upload grouping
            preserved_state = {
                k: v
                for k, v in (d.provider_state or {}).items()
                if k in {"storage_key", "grouping"}
            }
            d.raw = None
            d.metadata_json = {}
            d.normalized = {}
            d.validation = {}
            d.error = ""
            d.provider_state = preserved_state
            d.status = "QUEUED"
            job = enqueue(db, d, action="reextract")
            queued.append({"id": d.id, "filename": d.filename, "job_id": job.id})
        for run in db.scalars(select(CaseRun).where(CaseRun.case_id == case.id)):
            run.status = "SUPERSEDED"
        if queued:
            case.status = "PROCESSING"
            case.validation_status = "PENDING"
            case.updated_at = time.time()
        audit(
            db,
            case.org,
            user.id,
            "case.documents_retry_requested",
            case.branch_id,
            case.id,
            queued_count=len(queued),
            skipped_count=len(skipped),
        )
        db.flush()
        return {"queued": queued, "skipped": skipped}


def case_assignment(*, case_id: str, user):
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


def assign_case(*, case_id: str, data: TaskAssignment, user):
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
                raise ApplicationError(
                    "invalid_input", "Assignee must have access to this branch."
                )
        task = db.scalar(
            select(CaseTask).where(CaseTask.case_id == c.id, CaseTask.org == user.org)
        )
        if not task:
            task = CaseTask(
                org=user.org, branch_id=c.branch_id, case_id=c.id, assigned_by=user.id
            )
            db.add(task)
        (task.assigned_to, task.due_at, task.assigned_by) = (
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


def revalidate_enum_aliases(*, case_id: str, data: EnumRevalidationInput, user):
    from app.enum_aliases import validate_aliases

    with SessionLocal.begin() as db:
        case = authorized(db, Case, case_id, user)
        documents = db.scalars(
            select(Document).where(Document.case_id == case.id)
        ).all()
        if any(
            (
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
            )
        ) or db.scalar(
            select(Job).where(
                Job.document_id.in_([d.id for d in documents]),
                Job.status.in_(["QUEUED", "DISPATCHED", "RUNNING"]),
            )
        ):
            raise ApplicationError("conflict", "Wait for case processing to finish.")
        targets = [
            d
            for d in documents
            if d.doc_type == "ektp" and d.status == "COMPLETED" and d.raw
        ]
        if not targets:
            raise ApplicationError(
                "invalid_input", "No completed eKTP extraction is available."
            )
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
            targets_in_policy = set(policy["enum_aliases"]) | set(
                policy["enum_raw_fallback_fields"]
            )
            if not targets_in_policy or targets_in_policy - set(
                payload["profiles"]["ektp"]["schema"]["properties"]
            ):
                raise ValueError(
                    "Choose an approved enum policy for fields present in this document profile before revalidation."
                )
        except ValueError as exc:
            raise ApplicationError("invalid_input", str(exc))
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
