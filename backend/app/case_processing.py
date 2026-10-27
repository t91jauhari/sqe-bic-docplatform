"""Frozen case inputs and independently dispatched SOP/report jobs."""

from .configuration.repository import get_revision


import hashlib
import json
import time

from sqlalchemy import func, select

from .db import (
    Branch,
    Case,
    CaseContext,
    CaseRun,
    Config,
    Document,
    Inbox,
    Report,
    SessionLocal,
)
from .sop import evaluate

ACTIVE = {"QUEUED", "CLASSIFYING", "UPLOADING", "PARSING", "EXTRACTING", "VALIDATING"}


def inputs(db, case):
    cfg = get_revision(db, case.config_id)
    docs = db.scalars(
        select(Document).where(Document.case_id == case.id).order_by(Document.id)
    ).all()
    context = db.scalar(select(CaseContext).where(CaseContext.case_id == case.id))
    if not context or not context.payload or not any(k in context.payload for k in ("threshold_state", "customer_type", "payment_basis")):
        from app.case_context import ensure_case_context
        context = ensure_case_context(db, case.id)
    branch = db.get(Branch, case.branch_id)
    return {
        "sop_contract_version": 2,
        "case_id": case.id,
        "reference": case.reference,
        "customer": case.customer,
        "branch_id": case.branch_id,
        "branch_name": branch.name,
        "branch_code": branch.code,
        "organization": case.org,
        "config_version": cfg.version,
        "config_id": cfg.id,
        "configuration": cfg.payload,
        "template": case.template,
        "report_title": cfg.payload["report_title"],
        "provider": cfg.payload["provider"],
        "case_context": context.payload if context else {},
        "documents": [
            {
                "id": d.id,
                "filename": d.filename,
                "sha256": d.sha256,
                "doc_type": d.doc_type,
                "status": d.status,
                "classification": d.classification,
                "raw": d.raw,
                "normalized": d.normalized,
                "overrides": d.overrides,
                "validation": d.validation,
                "metadata": d.metadata_json,
                "provider_state": d.provider_state,
                "error": d.error,
            }
            for d in docs
        ],
    }


def fingerprint(snapshot):
    return hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, default=str).encode()
    ).hexdigest()


def queue_case(db, case_id, force=False):
    from app.auditing import audit

    case = db.scalar(select(Case).where(Case.id == case_id).with_for_update())
    frozen = inputs(db, case)
    if any(d["status"] in ACTIVE for d in frozen["documents"]):
        case.status = "PROCESSING"
        case.validation_status = "PENDING"
        case.updated_at = time.time()
        return frozen
    key = fingerprint(frozen)
    prior = db.scalar(
        select(CaseRun).where(CaseRun.case_id == case.id, CaseRun.fingerprint == key)
    )
    if prior and not force:
        # The inputs match a prior run. A retry that reproduces identical
        # extraction (process_job reuses stored raw) yields the same
        # fingerprint, so no new SOP run is queued. Restore the case status
        # from the prior run's report so the case is not left stuck in
        # PROCESSING after process_job set it at the start of the retry.
        if prior.status == "COMPLETED":
            report = db.scalar(
                select(Report).where(
                    Report.case_id == case.id, Report.fingerprint == key
                )
            )
            if report and report.snapshot.get("status"):
                case.status = report.snapshot["status"]
                case.validation_status = report.snapshot.get(
                    "validation_status", case.validation_status
                )
                case.updated_at = time.time()
        elif prior.status in {"QUEUED", "DISPATCHED", "RUNNING"}:
            case.status = "SOP_QUEUED"
            case.validation_status = "PENDING"
            case.updated_at = time.time()
        elif prior.status == "ERROR":
            case.status = "SOP_ERROR"
            case.validation_status = "ERROR"
            case.updated_at = time.time()
        return frozen
    if prior and force:
        db.delete(prior)
        db.flush()
    run = CaseRun(
        org=case.org,
        branch_id=case.branch_id,
        case_id=case.id,
        fingerprint=key,
        snapshot=frozen,
    )
    db.add(run)
    case.status = "SOP_QUEUED"
    case.validation_status = "PENDING"
    case.updated_at = time.time()
    audit(
        db,
        case.org,
        "worker",
        "sop.queued",
        case.branch_id,
        case.id,
        snapshot_hash=key,
        config_version=frozen["config_version"],
    )
    return frozen


def publish_inbox(db, case, count, missing):
    title = f"{case.customer} · " + {
        "READY": "Report ready for release",
        "NEEDS_REVIEW": "Review findings",
        "WAITING_DOCUMENTS": "Missing documents",
        "PROCESSING_ERROR": "Processing needs attention",
        "SOP_ERROR": "SOP/report processing needs attention",
    }.get(case.status, "Processing")
    body = (
        f"{count} SOP results · {missing} missing documents · {case.validation_status}"
    )
    item = db.scalar(select(Inbox).where(Inbox.key == case.id))
    if not item:
        db.add(
            Inbox(
                org=case.org,
                branch_id=case.branch_id,
                case_id=case.id,
                key=case.id,
                title=title,
                body=body,
                severity="action",
            )
        )
    else:
        if item.title != title or item.body != body:
            item.read_by = []
        item.title = title
        item.body = body
        item.resolved = False


def process_case_run(run_id):
    from app.auditing import audit
    from .reporting import persist_report

    with SessionLocal.begin() as db:
        run = db.get(CaseRun, run_id)
        if not run or run.status in {"COMPLETED", "SUPERSEDED"}:
            return
        run.status = "RUNNING"
        run.stage = "CASE_SOP"
        run.lease_until = time.time() + 120
        frozen = run.snapshot
        case = db.get(Case, run.case_id)
        if fingerprint(inputs(db, case)) != run.fingerprint:
            run.status = "SUPERSEDED"
            run.lease_until = 0
            queue_case(db, case.id)
            return
        case.status = "SOP_CHECKING"
    try:
        from .transaction_flows import scope_configuration, score_configuration

        cfg = scope_configuration(frozen["configuration"], frozen["template"])
        docs = frozen["documents"]
        context = frozen["case_context"]
        findings = evaluate(docs, cfg, context)
        # Manual observations are attached to immutable inputs and cannot override missing processing.
        for f in findings:
            review = context.get("rule_reviews", {}).get(f["rule_id"])
            if (
                review
                and review.get("document_basis")
                == fingerprint({"documents": docs, "config_id": frozen["config_id"]})
                and f["result"] == "REVIEW"
            ):
                f["automated_result"] = f["result"]
                f["result"] = review["result"]
                f["reason_code"] = "VISUAL_REVIEW_" + review["result"]
                f["evidence"]["review"] = review
        missing = [
            t
            for t in cfg["templates"][frozen["template"]]["required"]
            if t not in {d["doc_type"] for d in docs}
        ]
        from .grouping import identity_conflicts

        grouping_findings = identity_conflicts(docs, cfg)
        templates = cfg.get("sop_message_templates", {})
        technical = list(grouping_findings)
        for d in docs:
            if d["status"] != "COMPLETED":
                technical.append(
                    {
                        "rule_id": "processing.incomplete",
                        "field": d["filename"],
                        "result": "ERROR",
                        "eligible": False,
                        "message": d.get("error")
                        or templates.get(
                            "processing.incomplete", "Document processing incomplete."
                        ),
                        "evidence": {"document_id": d["id"]},
                    }
                )
            for k, v in d["validation"].get("fields", {}).items():
                for issue in v.get("issues", []):
                    technical.append(
                        {
                            "rule_id": issue["code"],
                            "field": d["doc_type"] + "." + k,
                            "result": issue.get("severity", "REVIEW"),
                            "eligible": False,
                            "message": templates.get(
                                "processing.native_quality",
                                "Native document quality check",
                            ),
                            "evidence": {"document_id": d["id"]},
                        }
                    )
        for t in missing:
            technical.append(
                {
                    "rule_id": "case.required_document",
                    "eligible": False,
                    "field": t,
                    "result": "FAIL",
                    "message": templates.get(
                        "processing.required_missing", "Required document missing."
                    ),
                    "actual": None,
                    "expected": t,
                    "evidence": {},
                }
            )
        errors = any(d["status"] != "COMPLETED" for d in docs)
        # Phase 2 §3.2.2 — Configurable SOP Review Bypass
        # Legacy bypass cannot replace observed review evidence.
        effective_findings = findings
        applicable = any(f["result"] != "NOT_APPLICABLE" for f in effective_findings)
        status = (
            "REVIEW"
            if not applicable and not errors
            else (
                "ERROR"
                if errors
                else (
                    "FAIL"
                    if any(f["result"] == "FAIL" for f in effective_findings)
                    else (
                        "REVIEW"
                        if missing
                        or grouping_findings
                        or any(f["result"] == "REVIEW" for f in effective_findings)
                        else "PASS"
                    )
                )
            )
        )
        from .sop_scoring import point_summary
        from .forex_sop import package_summary

        snapshot = {
            **frozen,
            "configuration": cfg,
            "transaction_flow": {
                "id": frozen["template"],
                "label": cfg["templates"][frozen["template"]]["label"],
            },
            "findings": findings,
            "technical_findings": technical,
            "missing": missing,
            "validation_status": status,
            "scores": score_configuration(cfg, frozen["template"], findings),
            "sop_summary": point_summary(findings),
            "sop_packages": package_summary(findings),
            "sop_completed_at": time.time(),
            "generated_at": time.time(),
        }
        # QA remains visible but never enters SOP scores. Processing/classification failures block release.
        # Phase 2 §3.2.2 — when bypass is on, only FAIL/ERROR findings and structural blockers force NEEDS_REVIEW.
        snapshot["status"] = (
            "PROCESSING_ERROR"
            if errors
            else (
                "WAITING_DOCUMENTS"
                if missing
                else (
                    "NEEDS_REVIEW"
                    if any(
                        (
                            (
                                e.get("observed_present") is not False
                                and not e.get("available")
                            )
                            or e.get("link_review_required")
                        )
                        for d in docs
                        for e in d.get("validation", {}).get("visual_evidence", [])
                    )
                    or status == "REVIEW"
                    or any(
                        f["result"] in {"REVIEW", "ERROR"} for f in effective_findings
                    )
                    else "READY"
                )
            )
        )
        with SessionLocal.begin() as db:
            run = db.get(CaseRun, run_id)
            run.stage = "RENDER_REPORT"
            case = db.scalar(
                select(Case).where(Case.id == run.case_id).with_for_update()
            )
            if fingerprint(inputs(db, case)) != run.fingerprint:
                run.status = "SUPERSEDED"
                run.lease_until = 0
                queue_case(db, case.id)
                return
            report = db.scalar(
                select(Report).where(
                    Report.case_id == case.id, Report.fingerprint == run.fingerprint
                )
            )
            if not report:
                version = (
                    db.scalar(
                        select(func.max(Report.version)).where(
                            Report.case_id == case.id
                        )
                    )
                    or 0
                ) + 1
                report = Report(
                    org=case.org,
                    branch_id=case.branch_id,
                    case_id=case.id,
                    version=version,
                    fingerprint=run.fingerprint,
                    snapshot=snapshot,
                )
                db.add(report)
                db.flush()
                if not errors:
                    persist_report(report)
            else:
                report.snapshot = snapshot
                db.flush()
                if not errors:
                    persist_report(report)
            run.status = "COMPLETED"
            run.stage = "COMPLETE"
            run.lease_until = 0
            run.error = ""
            case.status = snapshot["status"]
            case.validation_status = status
            case.updated_at = time.time()
            publish_inbox(db, case, len(findings), len(missing))
            audit(
                db,
                case.org,
                "worker",
                "sop.completed",
                case.branch_id,
                case.id,
                run_id=run.id,
                snapshot_hash=run.fingerprint,
                result=status,
                report_id=report.id,
            )
    except Exception as exc:
        with SessionLocal.begin() as db:
            run = db.get(CaseRun, run_id)
            run.status = "ERROR"
            run.lease_until = 0
            run.error = f"SOP/report activity failed ({type(exc).__name__}). Resume without extraction."
            case = db.get(Case, run.case_id)
            if fingerprint(inputs(db, case)) == run.fingerprint:
                case.status = "SOP_ERROR"
                case.validation_status = "ERROR"
                publish_inbox(db, case, 0, 0)
            audit(
                db,
                case.org,
                "worker",
                "sop.failed",
                case.branch_id,
                case.id,
                error_type=type(exc).__name__,
            )
        raise
