"""Repair one historical batch without repeating provider extraction."""

from .configuration.repository import get_revision


import hashlib
import json
import time
from collections import Counter
from fastapi import HTTPException
from sqlalchemy import select
from .db import (
    Batch,
    Case,
    CaseContext,
    CaseRun,
    CaseTask,
    Config,
    Document,
    Inbox,
    Job,
    Report,
)
from app.auditing import audit
from app.case_lifecycle import refresh_case
from .grouping import plan_grouping
from .security import authorized


def load_batch(db, batch_id, user, lock=False):
    batch = authorized(db, Batch, batch_id, user)
    query = select(Document).where(Document.batch_id == batch.id).order_by(Document.id)
    docs = db.scalars(query.with_for_update() if lock else query).all()
    if not docs or len(docs) > 100:
        raise HTTPException(
            409, "Repair supports nonempty batches of up to 100 documents."
        )
    if len({d.filename for d in docs}) != len(docs):
        raise HTTPException(
            409,
            "This older batch has duplicate filenames. Use individual document moves.",
        )
    cases = {d.case_id: authorized(db, Case, d.case_id, user) for d in docs}
    if len({(c.config_id, c.template) for c in cases.values()}) != 1:
        raise HTTPException(
            409,
            "Case configurations or templates differ. Use individual document moves.",
        )
    revision = hashlib.sha256(
        json.dumps(
            [
                (d.id, d.case_id, d.status, d.provider_state.get("grouping"))
                for d in docs
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()
    cfg = get_revision(db, next(iter(cases.values())).config_id).payload
    return batch, docs, cases, cfg, revision


def preview(db, batch_id, user):
    batch, docs, cases, cfg, revision = load_batch(db, batch_id, user)
    rows = plan_grouping([d.filename for d in docs], cfg)
    for row, doc in zip(rows, docs):
        row.update(document_id=doc.id, current_customer=cases[doc.case_id].customer)
    return dict(batch_id=batch.id, revision=revision, rows=rows)


def apply(db, batch_id, user, labels, expected_revision, reason):
    batch, docs, cases, cfg, revision = load_batch(db, batch_id, user, True)
    if revision != expected_revision:
        raise HTTPException(
            409, "Batch changed. Reopen grouping to review its current documents."
        )
    if set(labels) != {d.filename for d in docs} or any(
        not isinstance(v, str) or not v.strip() or len(v) > 180 for v in labels.values()
    ):
        raise HTTPException(
            422, "Assign every batch document to a customer name up to 180 characters."
        )
    case_ids = list(cases)
    # Existing worker code owns its leases. Do not change membership while a
    # worker or frozen case calculation can still publish its result.
    if (
        any(
            d.status not in {"COMPLETED", "ERROR", "NEEDS_CLASSIFICATION"} for d in docs
        )
        or db.scalar(
            select(Job).where(
                Job.document_id.in_([d.id for d in docs]),
                Job.status.in_(["QUEUED", "DISPATCHED", "RUNNING"]),
            )
        )
        or db.scalar(
            select(CaseRun).where(
                CaseRun.case_id.in_(case_ids),
                CaseRun.status.in_(["QUEUED", "DISPATCHED", "RUNNING"]),
            )
        )
    ):
        raise HTTPException(
            409, "Wait until document and case processing stops before regrouping."
        )
    if db.scalar(
        select(Report).where(Report.case_id.in_(case_ids), Report.state != "DRAFT")
    ):
        raise HTTPException(
            409,
            "This batch has an approved or released report. Use the report revision process first.",
        )
    # Preserve contexts and assignments rather than guessing how to combine
    # conflicting business decisions during a many-to-many regroup.
    if any(
        c.payload
        for c in db.scalars(
            select(CaseContext).where(CaseContext.case_id.in_(case_ids))
        )
    ) or any(
        t.assigned_to or t.due_at
        for t in db.scalars(select(CaseTask).where(CaseTask.case_id.in_(case_ids)))
    ):
        raise HTTPException(
            409,
            "Case context or assignments need reconciliation. Use individual document moves.",
        )
    if any(
        db.scalar(
            select(Document.id).where(
                Document.case_id == cid, Document.batch_id != batch.id
            )
        )
        for cid in case_ids
    ):
        raise HTTPException(
            409,
            "A case contains documents from other batches. Use individual document moves.",
        )
    rows = plan_grouping([d.filename for d in docs], cfg, labels)
    targets, used = {}, set()
    groups = {}
    for doc, row in zip(docs, rows):
        groups.setdefault(row["customer"].casefold(), []).append((doc, row))
    for key, members in groups.items():
        label = members[0][1]["customer"]
        counts = Counter(d.case_id for d, _ in members)
        options = sorted(
            (cid for cid in counts if cid not in used),
            key=lambda cid: (-counts[cid], cid),
        )
        if options:
            target = cases[options[0]]
        else:
            source = cases[members[0][0].case_id]
            target = Case(
                org=batch.org,
                branch_id=batch.branch_id,
                customer=label,
                reference=f"{label} / {batch.id[:8]}",
                template=source.template,
                created_by=user.id,
                config_id=source.config_id,
            )
            db.add(target)
            db.flush()
        used.add(target.id)
        target.customer = label
        target.reference = f"{label} / {batch.id[:8]}"
        target.updated_at = time.time()
        targets[key] = target
        for doc, row in members:
            old = doc.case_id
            doc.case_id = target.id
            doc.provider_state = {
                **doc.provider_state,
                "grouping": {k: v for k, v in row.items() if k != "classification"},
            }
            audit(
                db,
                user.org,
                user.id,
                "document.grouping_confirmed",
                batch.branch_id,
                target.id,
                document_id=doc.id,
                from_case=old,
                customer=label,
                reason=reason,
            )
    db.flush()
    for cid, old in cases.items():
        if cid not in used:
            old.status = "MERGED"
            old.validation_status = "PENDING"
            old.updated_at = time.time()
            for item in db.scalars(select(Inbox).where(Inbox.case_id == cid)):
                item.resolved = True
            audit(
                db,
                user.org,
                user.id,
                "case.merged",
                batch.branch_id,
                cid,
                target_case_ids=list(used),
                reason=reason,
            )
    for target in targets.values():
        refresh_case(db, target.id)
    return dict(case_ids=[c.id for c in targets.values()], batch_id=batch.id)
