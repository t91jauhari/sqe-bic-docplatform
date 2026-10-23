"""Reports HTTP boundary."""

from app.application import reports as use_cases
from fastapi import APIRouter
import json
import time
from fastapi import Depends, HTTPException, Response
from sqlalchemy import select
from app.db import Case, Report, SessionLocal, uid
from app.auditing import audit
from app.reporting import make_report, report_key
from app.security import authorized, branch_allowed, current_user
from app.storage import object_key, store
from app.api.dependencies import REVIEW
from app.api.views import report_download_name

router = APIRouter(tags=["reports"])


@router.get("/api/reports")
def reports(user=Depends(current_user)):
    return use_cases.reports(user=user)


@router.get("/api/reports/kertas-kerja")
def export_branch_report(
    branch_id: str,
    transaction_flow: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    user=Depends(current_user),
):
    from app.config_workbook import MIME
    from app.kertas_kerja import workbook
    from app.branch_report import select_branch_reports, export_period
    from datetime import date

    try:
        start_date = date.fromisoformat(date_from) if date_from else None
        end_date = date.fromisoformat(date_to) if date_to else None
        if start_date and end_date and (start_date > end_date):
            raise ValueError()
    except ValueError:
        raise HTTPException(
            422,
            "Use valid YYYY-MM-DD transaction dates; the start must not be after the end.",
        )
    with SessionLocal.begin() as db:
        branch_allowed(db, branch_id, user)
        reports = db.scalars(
            select(Report)
            .where(
                Report.org == user.org,
                Report.branch_id == branch_id,
                Report.case_id.in_(select(Case.id).where(Case.status != "MERGED")),
            )
            .order_by(Report.case_id, Report.version.desc())
        ).all()
        latest = select_branch_reports(
            db, reports, transaction_flow, start_date, end_date
        )
        if not latest:
            raise HTTPException(
                404,
                "No current customer reports match this branch, transaction flow and transaction-date range.",
            )
        period = export_period(start_date, end_date)
        snapshots = [
            {
                **r.snapshot,
                "release_state": r.state,
                "snapshot_hash": r.fingerprint,
                "report_export_context": {
                    "period": period,
                    "transaction_flow": transaction_flow or "All services",
                },
            }
            for r in latest.values()
        ]
        data = workbook(snapshots)
        export_id = uid()
        key = object_key(user.org, branch_id, "exports", export_id, "kertas-kerja.xlsx")
        store().put(key, data, MIME)
        manifest = {
            "reports": [
                {"id": r.id, "version": r.version, "snapshot_hash": r.fingerprint}
                for r in latest.values()
            ],
            "exported_by": user.id,
            "at": time.time(),
            "branch_id": branch_id,
            "transaction_flow": transaction_flow,
            "date_from": date_from,
            "date_to": date_to,
        }
        store().put(
            object_key(user.org, branch_id, "exports", export_id, "manifest.json"),
            json.dumps(manifest).encode(),
            "application/json",
        )
        audit(
            db,
            user.org,
            user.id,
            "report.branch_exported",
            branch_id,
            export_id=export_id,
            source_reports=manifest["reports"],
        )
        return Response(
            data,
            media_type=MIME,
            headers={
                "Content-Disposition": 'attachment; filename="branch-kertas-kerja.xlsx"'
            },
        )


@router.get("/api/reports/{report_id}/download")
def download_report(report_id: str, format: str = "pdf", user=Depends(current_user)):
    if format not in {"pdf", "xlsx", "json"}:
        raise HTTPException(422, "Use pdf, xlsx or json.")
    with SessionLocal.begin() as db:
        r = authorized(db, Report, report_id, user)
        (data, mime) = make_report(r, format)
        store().put(report_key(r, format), data, mime)
        data = store().read(report_key(r, format))
        audit(
            db,
            user.org,
            user.id,
            "report.downloaded",
            r.branch_id,
            r.case_id,
            report_id=r.id,
            format=format,
        )
    return Response(
        data,
        media_type=mime,
        headers={"Content-Disposition": report_download_name(r, format)},
    )


@router.get("/api/reports/{report_id}")
def report_detail(report_id: str, user=Depends(current_user)):
    return use_cases.report_detail(report_id=report_id, user=user)


@router.post("/api/reports/{report_id}/approve")
def approve_report(report_id: str, user=Depends(REVIEW)):
    return use_cases.approve_report(report_id=report_id, user=user)
