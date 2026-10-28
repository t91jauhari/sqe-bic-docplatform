"""Case Lifecycle operations."""

from app.configuration.repository import get_revision
import hashlib
import json
import time
from sqlalchemy import func, select
from app.db import Case, Document, Inbox, Job, Report


def enqueue(db, doc, action="process"):
    running = db.scalar(
        select(Job).where(
            Job.document_id == doc.id,
            Job.status.in_(["QUEUED", "DISPATCHED", "RUNNING"]),
        )
    )
    if running:
        if action == "reextract":
            running.action = "reextract"
            doc.status = "QUEUED"
        return running
    doc.status = "QUEUED"
    doc.error = ""
    case = db.get(Case, doc.case_id)
    case.status = "QUEUED"
    case.updated_at = time.time()
    job = Job(org=doc.org, branch_id=doc.branch_id, document_id=doc.id, action=action)
    db.add(job)
    return job


def refresh_case(db, case_id):
    from app.auditing import audit, serial
    from app.legacy_case_rules import evaluate_rules, riplay_identity_findings

    case = db.scalar(select(Case).where(Case.id == case_id).with_for_update())
    docs = db.scalars(
        select(Document)
        .where(Document.case_id == case_id)
        .order_by(Document.created_at)
    ).all()
    cfg_record = get_revision(db, case.config_id)
    cfg = cfg_record.payload
    if "workflow" in cfg:
        from app.case_processing import queue_case

        return queue_case(db, case_id)
    required = cfg["templates"][case.template]["required"]
    present = {d.doc_type for d in docs}
    missing = [x for x in required if x not in present]
    findings = riplay_identity_findings(docs, cfg)
    for name in missing:
        findings.append(
            {
                "rule_id": "case.required_document",
                "field": name,
                "result": "FAIL",
                "actual": None,
                "expected": "Document present",
                "message": "Missing " + cfg["profiles"][name].get("label", name),
                "evidence": {},
            }
        )
    for name in set((d.doc_type for d in docs if d.doc_type != "unknown")):
        if sum((d.doc_type == name for d in docs)) > 1:
            findings.append(
                {
                    "rule_id": "case.duplicate_type",
                    "field": name,
                    "result": "REVIEW",
                    "message": "Multiple documents of this type. Review case membership.",
                    "evidence": {},
                }
            )
    for d in docs:
        if d.status == "ERROR":
            findings.append(
                {
                    "rule_id": "processing.error",
                    "field": d.filename,
                    "result": "REVIEW",
                    "message": d.error,
                    "evidence": {"document_id": d.id},
                }
            )
        if d.doc_type == "unknown":
            findings.append(
                {
                    "rule_id": "case.unassigned",
                    "field": d.filename,
                    "result": "REVIEW",
                    "message": "Document type and case membership need review.",
                    "evidence": {"document_id": d.id},
                }
            )
        for key, field in d.validation.get("fields", {}).items():
            for issue in field.get("issues", []):
                findings.append(
                    {
                        "rule_id": issue["code"],
                        "field": f"{d.doc_type}.{key}",
                        "result": issue.get("severity", "REVIEW"),
                        "actual": field.get("normalized_value"),
                        "message": issue["code"].replace("_", " ").capitalize(),
                        "evidence": {
                            "document_id": d.id,
                            "metadata": field.get("metadata", {}),
                        },
                    }
                )
    findings += evaluate_rules(docs, cfg["rules"])
    active = any(
        (
            d.status
            in {
                "QUEUED",
                "CLASSIFYING",
                "UPLOADING",
                "PARSING",
                "EXTRACTING",
                "VALIDATING",
            }
            for d in docs
        )
    )
    if active:
        case.status = "PROCESSING"
    elif any((d.status == "ERROR" for d in docs)):
        case.status = "PROCESSING_ERROR"
    elif missing:
        case.status = "WAITING_DOCUMENTS"
    elif any((d.status == "NEEDS_CLASSIFICATION" for d in docs)):
        case.status = "NEEDS_REVIEW"
    else:
        case.status = (
            "NEEDS_REVIEW"
            if any((x["result"] in {"FAIL", "REVIEW"} for x in findings))
            else "READY"
        )
    case.validation_status = (
        "FAIL"
        if any((x["result"] == "FAIL" for x in findings))
        else (
            "REVIEW"
            if any((x["result"] == "REVIEW" for x in findings))
            else "PENDING" if active else "PASS"
        )
    )
    case.updated_at = time.time()
    snapshot = {
        "case_id": case.id,
        "reference": case.reference,
        "customer": case.customer,
        "branch_id": case.branch_id,
        "organization": case.org,
        "status": case.status,
        "validation_status": case.validation_status,
        "config_version": cfg_record.version,
        "config_id": cfg_record.id,
        "report_title": cfg["report_title"],
        "provider": cfg["provider"],
        "missing": missing,
        "findings": serial(findings),
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
                "provider_state": d.provider_state,
            }
            for d in docs
        ],
    }
    fingerprint = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, default=str).encode()
    ).hexdigest()
    report = db.scalar(
        select(Report).where(
            Report.case_id == case.id, Report.fingerprint == fingerprint
        )
    )
    if not active and (not report):
        version = (
            db.scalar(select(func.max(Report.version)).where(Report.case_id == case.id))
            or 0
        ) + 1
        snapshot["generated_at"] = time.time()
        report = Report(
            org=case.org,
            branch_id=case.branch_id,
            case_id=case.id,
            version=version,
            fingerprint=fingerprint,
            snapshot=snapshot,
            state="FINAL",
        )
        db.add(report)
        db.flush()
        from app.reporting import persist_report

        if case.status != "PROCESSING_ERROR":
            persist_report(report)
        audit(
            db,
            case.org,
            "worker",
            "report.draft_generated",
            case.branch_id,
            case.id,
            version=version,
        )
    inbox = db.scalar(select(Inbox).where(Inbox.key == case.id))
    actionable = case.status in {
        "WAITING_DOCUMENTS",
        "PROCESSING_ERROR",
        "NEEDS_REVIEW",
        "READY",
    }
    title = f"{case.customer} · " + {
        "WAITING_DOCUMENTS": "Missing documents",
        "PROCESSING_ERROR": "Processing needs attention",
        "NEEDS_REVIEW": "Review findings",
        "READY": "Report ready for release",
    }.get(case.status, "Processing")
    body = f"{len(findings)} findings · {len(missing)} missing documents · {case.validation_status}"
    if not inbox and actionable:
        db.add(
            Inbox(
                org=case.org,
                branch_id=case.branch_id,
                case_id=case.id,
                key=case.id,
                title=title,
                body=body,
                severity="action",
                resolved=False,
            )
        )
    elif inbox:
        if inbox.title != title or inbox.body != body:
            inbox.read_by = []
        inbox.title = title
        inbox.body = body
        inbox.resolved = not actionable
    return snapshot
