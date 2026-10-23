"""Shared projections over caller-authorized records and pinned settings."""

from app.configuration.repository import get_revision
import re
from urllib.parse import quote
from sqlalchemy import select
from app.db import Document


def user_view(user):
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "organization": user.org,
        "branches": user.branches,
        "active": user.active,
    }


def case_view(c, db, *, doc_rows=None, rev=None):
    rows = (
        doc_rows
        if doc_rows is not None
        else db.execute(
            select(Document.doc_type, Document.status).where(Document.case_id == c.id)
        ).all()
    )
    revision = (
        rev if rev is not None else get_revision(db, c.config_id, copy_payload=False)
    )
    payload = revision.payload
    missing_documents = sorted(
        {
            payload["profiles"][doc_type]["label"]
            for doc_type, doc_status in rows
            if doc_type in payload["profiles"] and doc_status != "COMPLETED"
        }
    )
    return {
        "id": c.id,
        "reference": c.reference,
        "customer": c.customer,
        "branch_id": c.branch_id,
        "status": c.status,
        "validation_status": c.validation_status,
        "template": c.template,
        "transaction_flow_label": payload["templates"][c.template]["label"],
        "created_at": c.created_at,
        "updated_at": c.updated_at,
        "documents_count": len(rows),
        "completed_count": sum(doc_status == "COMPLETED" for _, doc_status in rows),
        "missing_documents": missing_documents,
        "created_by": c.created_by,
        "config_version": revision.version,
    }


def case_views(cases, db):
    rows = list(cases)
    if not rows:
        return []
    case_ids = [c.id for c in rows]
    doc_rows_by_case = {cid: [] for cid in case_ids}
    for case_id, doc_type, doc_status in db.execute(
        select(Document.case_id, Document.doc_type, Document.status).where(
            Document.case_id.in_(case_ids)
        )
    ):
        doc_rows_by_case[case_id].append((doc_type, doc_status))
    revisions = {}
    for c in rows:
        if c.config_id not in revisions:
            revisions[c.config_id] = get_revision(
                db, c.config_id, copy_payload=False
            )
    return [
        case_view(c, db, doc_rows=doc_rows_by_case[c.id], rev=revisions[c.config_id])
        for c in rows
    ]


def doc_view(d):
    return {
        "id": d.id,
        "filename": d.filename,
        "doc_type": d.doc_type,
        "status": d.status,
        "validation_status": d.validation_status,
        "classification": d.classification,
        "provider_state": d.provider_state,
        "raw": d.raw,
        "normalized": d.normalized,
        "overrides": d.overrides,
        "validation": d.validation,
        "error": d.error,
        "case_id": d.case_id,
    }


def comparison_view(db, case, state):
    from app.dataset_comparison import compare, dataset_for_case

    docs = db.scalars(
        select(Document)
        .where(Document.case_id == case.id)
        .order_by(Document.created_at)
    ).all()
    from app.configuration.dataset_policy import comparison_policy

    payload = get_revision(db, case.config_id, copy_payload=False).payload
    policy = comparison_policy(payload, case.template)
    return compare(
        case,
        docs,
        state,
        dataset_for_case(db, case, payload=payload),
        policy=policy,
    )


def report_download_name(report, format):
    customer = (
        re.sub(
            r"[^\w .-]", "_", str(report.snapshot.get("customer") or "customer")
        ).strip(" .")[:100]
        or "customer"
    )
    name = f"kertas-kerja-{customer}-v{report.version}.{format}"
    fallback = re.sub(r"[^a-zA-Z0-9 ._-]", "_", name)
    return (
        f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{quote(name,safe="")}'
    )
