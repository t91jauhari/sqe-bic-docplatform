"""Comparisons application operations.

Transactions, authorization, audit and pinned configuration remain one unit.
"""

from app.errors import ApplicationError
import copy
import json
import time
from sqlalchemy import select
from app.db import Case, Document, DatasetComparison, SessionLocal
from app.auditing import audit
from app.access import authorized
from app.contracts import ComparisonInput
from app.projections import comparison_view


def dataset_sample(*, case_id: str, user):
    from app.dataset_comparison import dataset_for_case
    from app.configuration.dataset_sources import resolve_dataset

    if not case_id:
        with SessionLocal() as db:
            return resolve_dataset(db, user.org, "forex-sample-v1")
    with SessionLocal() as db:
        case = authorized(db, Case, case_id, user)
        return dataset_for_case(db, case)


def dataset_comparison(*, case_id: str, user):
    with SessionLocal() as db:
        case = authorized(db, Case, case_id, user)
        item = db.scalar(
            select(DatasetComparison).where(DatasetComparison.case_id == case.id)
        )
        return comparison_view(db, case, item.payload if item else {})


def edit_comparison(*, case_id: str, data: ComparisonInput, user):
    from app.dataset_comparison import dataset_for_case

    with SessionLocal.begin() as db:
        case = authorized(db, Case, case_id, user)
        DATASET = dataset_for_case(db, case)
        if data.sample_id not in {s["id"] for s in DATASET["samples"]}:
            raise ApplicationError(
                "invalid_input", "Unknown dataset sample for this transaction flow."
            )
        rows = {r["id"]: r for r in DATASET["rows"]}
        if (
            any((k not in rows for k in data.edits))
            or len(json.dumps(data.edits)) > 200000
        ):
            raise ApplicationError(
                "invalid_input",
                "Unknown reference field or reference edits are too large.",
            )
        sections = {str(r["section"]): r["document_type"] for r in rows.values()}
        db.scalar(select(Case).where(Case.id == case.id).with_for_update())
        item = db.scalar(
            select(DatasetComparison)
            .where(DatasetComparison.case_id == case.id)
            .with_for_update()
        )
        previous = item.payload if item else {}
        if previous.get("revision", 0) != data.expected_revision:
            raise ApplicationError(
                "conflict", "Comparison changed. Reload before saving your edits."
            )
        for section, doc_id in data.documents.items():
            doc = db.get(Document, doc_id)
            if (
                section not in sections
                or not doc
                or doc.case_id != case.id
                or (doc.org != case.org)
                or (doc.doc_type != sections[section])
            ):
                raise ApplicationError(
                    "invalid_input",
                    "Source document must belong to this case and match the section type.",
                )
        edits = (
            copy.deepcopy(previous.get("edits", {}))
            if previous.get("sample_id") == data.sample_id
            else {}
        )
        for row_id, value in data.edits.items():
            if value is not None and (
                not isinstance(value, (str, bool, int, float, list, dict))
            ):
                raise ApplicationError("invalid_input", "Unsupported reference value.")
            edits[row_id] = {
                "value": value,
                "actor": user.id,
                "reason": data.reason,
                "at": time.time(),
            }
        payload = {
            "revision": data.expected_revision + 1,
            "sample_id": data.sample_id,
            "documents": data.documents,
            "edits": edits,
        }
        if not item:
            item = DatasetComparison(
                org=case.org, branch_id=case.branch_id, case_id=case.id, payload=payload
            )
            db.add(item)
        else:
            item.payload = payload
        audit(
            db,
            case.org,
            user.id,
            "dataset.comparison_saved",
            case.branch_id,
            case.id,
            before=previous,
            after=payload,
            reason=data.reason,
        )
        return comparison_view(db, case, payload)
