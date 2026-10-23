"""Comparisons HTTP boundary."""
from fastapi import APIRouter
import copy
import csv
import io
import json
import time
from fastapi import Depends, HTTPException, Response
from sqlalchemy import select
from app.db import Case, Document, DatasetComparison, SessionLocal
from app.domain import audit
from app.reporting import csv_safe
from app.security import authorized, current_user, scoped
from app.api.dependencies import WRITE
from app.api.contracts import ComparisonInput
from app.api.views import comparison_view

router = APIRouter(tags=['comparisons'])

@router.get("/api/dataset-sample")
def dataset_sample(case_id: str = "", user=Depends(current_user)):
    from app.dataset_comparison import dataset_for_case
    from app.configuration.dataset_sources import resolve_dataset

    if not case_id:
        with SessionLocal() as db:
            return resolve_dataset(db, user.org, "forex-sample-v1")
    with SessionLocal() as db:
        case = authorized(db, Case, case_id, user)
        return dataset_for_case(db, case)

@router.get("/api/cases/{case_id}/comparison")
def dataset_comparison(case_id: str, user=Depends(current_user)):
    with SessionLocal() as db:
        case = authorized(db, Case, case_id, user)
        item = db.scalar(
            select(DatasetComparison).where(DatasetComparison.case_id == case.id)
        )
        return comparison_view(db, case, item.payload if item else {})

@router.put("/api/cases/{case_id}/comparison")
def edit_comparison(case_id: str, data: ComparisonInput, user=Depends(WRITE)):
    from app.dataset_comparison import dataset_for_case

    with SessionLocal.begin() as db:
        case = authorized(db, Case, case_id, user)
        DATASET = dataset_for_case(db, case)
        if data.sample_id not in {s["id"] for s in DATASET["samples"]}:
            raise HTTPException(
                422, "Unknown dataset sample for this transaction flow."
            )
        rows = {r["id"]: r for r in DATASET["rows"]}
        if (
            any(k not in rows for k in data.edits)
            or len(json.dumps(data.edits)) > 200_000
        ):
            raise HTTPException(
                422, "Unknown reference field or reference edits are too large."
            )
        sections = {str(r["section"]): r["document_type"] for r in rows.values()}
        # Lock the case as well to serialize first writes before a comparison row exists.
        db.scalar(select(Case).where(Case.id == case.id).with_for_update())
        item = db.scalar(
            select(DatasetComparison)
            .where(DatasetComparison.case_id == case.id)
            .with_for_update()
        )
        previous = item.payload if item else {}
        if previous.get("revision", 0) != data.expected_revision:
            raise HTTPException(
                409, "Comparison changed. Reload before saving your edits."
            )
        for section, doc_id in data.documents.items():
            doc = db.get(Document, doc_id)
            if (
                section not in sections
                or not doc
                or doc.case_id != case.id
                or doc.org != case.org
                or doc.doc_type != sections[section]
            ):
                raise HTTPException(
                    422,
                    "Source document must belong to this case and match the section type.",
                )
        edits = (
            copy.deepcopy(previous.get("edits", {}))
            if previous.get("sample_id") == data.sample_id
            else {}
        )
        for row_id, value in data.edits.items():
            if value is not None and not isinstance(
                value, (str, bool, int, float, list, dict)
            ):
                raise HTTPException(422, "Unsupported reference value.")
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

@router.get("/api/cases/{case_id}/comparison/export")
def export_comparison(case_id: str, format: str = "csv", user=Depends(current_user)):
    if format not in {"csv", "json"}:
        raise HTTPException(422, "Supported comparison formats: csv, json.")
    with SessionLocal.begin() as db:
        case = authorized(db, Case, case_id, user)
        item = db.scalar(
            select(DatasetComparison).where(DatasetComparison.case_id == case.id)
        )
        result = comparison_view(db, case, item.payload if item else {})
        if not result.get("sample_id"):
            raise HTTPException(
                409, "Select and save a dataset sample before exporting."
            )
        result["exported_at"] = time.time()
        audit(
            db,
            case.org,
            user.id,
            "dataset.comparison_exported",
            case.branch_id,
            case.id,
            revision=result["revision"],
            fingerprint=result["fingerprint"],
            format=format,
        )
        if format == "json":
            body = json.dumps(result, ensure_ascii=False, indent=2)
            mime = "application/json"
        else:
            stream = io.StringIO()
            writer = csv.writer(stream)
            columns = [
                "case_id",
                "customer",
                "sample_name",
                "revision",
                "fingerprint",
                "dataset_sha256",
                "result",
                "match_rate",
                "complete",
                "compared_fields",
                "policy",
                "document_label",
                "filename",
                "document_id",
                "extraction_id",
                "field",
                "label",
                "original_value",
                "dataset_value",
                "effective_value",
                "status",
                "message",
                "edited",
                "edit_reason",
                "edit_actor",
                "source",
                "similarity",
                "method",
            ]
            writer.writerow(columns)
            for row in result["rows"]:
                record = {
                    **result,
                    **result["summary"],
                    **row,
                    "edit_reason": (row.get("edit") or {}).get("reason"),
                    "edit_actor": (row.get("edit") or {}).get("actor"),
                }
                writer.writerow([csv_safe(record.get(k)) for k in columns])
            body = "\ufeff" + stream.getvalue()
            mime = "text/csv; charset=utf-8"
        return Response(
            body,
            media_type=mime,
            headers={
                "Content-Disposition": f'attachment; filename="comparison-{case.id}-r{result["revision"]}.{format}"'
            },
        )

@router.get("/api/comparisons/export")
def export_all_comparisons(user=Depends(current_user)):
    from app.comparison_excel import MIME, export_workbook

    with SessionLocal.begin() as db:
        cases = db.scalars(
            scoped(
                select(Case)
                .join(DatasetComparison, DatasetComparison.case_id == Case.id)
                .where(Case.status != "MERGED")
                .order_by(Case.created_at),
                Case,
                user,
            )
        ).all()
        results = []
        for case in cases:
            state = db.scalar(
                select(DatasetComparison).where(DatasetComparison.case_id == case.id)
            ).payload
            result = comparison_view(db, case, state)
            if result.get("sample_id"):
                results.append(result)
        if not results:
            raise HTTPException(
                404, "No saved comparisons are available in your accessible cases."
            )
        body = export_workbook(results)
        audit(
            db,
            user.org,
            user.id,
            "dataset.all_comparisons_exported",
            comparisons=[
                {
                    "case_id": r["case_id"],
                    "revision": r["revision"],
                    "fingerprint": r["fingerprint"],
                }
                for r in results
            ],
        )
        return Response(
            body,
            media_type=MIME,
            headers={
                "Content-Disposition": 'attachment; filename="all-dataset-comparisons.xlsx"'
            },
        )
