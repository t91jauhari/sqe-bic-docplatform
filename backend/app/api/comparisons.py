"""Comparisons HTTP boundary."""

from app.application import comparisons as use_cases
from fastapi import APIRouter
import csv
import io
import json
import time
from fastapi import Depends, HTTPException, Response
from sqlalchemy import select
from app.db import Case, DatasetComparison, SessionLocal
from app.auditing import audit
from app.reporting import csv_safe
from app.security import authorized, current_user, scoped
from app.api.dependencies import WRITE
from app.api.contracts import ComparisonInput
from app.api.views import comparison_view

router = APIRouter(tags=["comparisons"])


@router.get("/api/dataset-sample")
def dataset_sample(case_id: str = "", user=Depends(current_user)):
    return use_cases.dataset_sample(case_id=case_id, user=user)


@router.get("/api/cases/{case_id}/comparison")
def dataset_comparison(case_id: str, user=Depends(current_user)):
    return use_cases.dataset_comparison(case_id=case_id, user=user)


@router.put("/api/cases/{case_id}/comparison")
def edit_comparison(case_id: str, data: ComparisonInput, user=Depends(WRITE)):
    return use_cases.edit_comparison(case_id=case_id, data=data, user=user)


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
                "Content-Disposition": f'''attachment; filename="comparison-{case.id}-r{result['revision']}.{format}"'''
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
