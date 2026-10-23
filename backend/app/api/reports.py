"""Reports HTTP boundary."""
from fastapi import APIRouter
from app.configuration.repository import get_revision
import json
import time
from fastapi import Depends, HTTPException, Response
from sqlalchemy import select
from app.db import Case, Inbox, Report, SessionLocal, uid
from app.domain import audit
from app.reporting import make_report, persist_report, report_key
from app.security import authorized, branch_allowed, current_user, scoped
from app.storage import object_key, store
from app.api.dependencies import REVIEW
from app.api.views import report_download_name

router = APIRouter(tags=['reports'])

@router.get("/api/reports")
def reports(user=Depends(current_user)):
    from app.report_queries import ReportAudience, ReportQueries
    audience = ReportAudience(user.org, None if user.role == "bank_admin" else tuple(user.branches))
    with SessionLocal() as db:
        return ReportQueries(db, audience).current()

@router.get("/api/reports/kertas-kerja")
def export_branch_report(branch_id: str, transaction_flow: str | None = None, date_from: str | None = None, date_to: str | None = None, user=Depends(current_user)):
    from app.config_workbook import MIME
    from app.kertas_kerja import workbook

    from app.branch_report import select_branch_reports, export_period
    from datetime import date
    try:
        start_date = date.fromisoformat(date_from) if date_from else None
        end_date = date.fromisoformat(date_to) if date_to else None
        if start_date and end_date and start_date > end_date:
            raise ValueError()
    except ValueError:
        raise HTTPException(422,"Use valid YYYY-MM-DD transaction dates; the start must not be after the end.")
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
        latest = select_branch_reports(db, reports, transaction_flow, start_date, end_date)
        if not latest:
            raise HTTPException(404, "No current customer reports match this branch, transaction flow and transaction-date range.")
        period = export_period(start_date,end_date)
        snapshots = [
            {**r.snapshot, "release_state": r.state, "snapshot_hash": r.fingerprint,
             "report_export_context":{"period":period,"transaction_flow":transaction_flow or "All services"}}
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
            "transaction_flow":transaction_flow,
            "date_from":date_from, "date_to":date_to,
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
        data, mime = make_report(r, format)
        # Also materialize legacy/error-case artifacts after storage recovery.
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
        headers={
            "Content-Disposition": report_download_name(r,format)
        },
    )

@router.get('/api/reports/{report_id}')
def report_detail(report_id: str, user=Depends(current_user)):
    with SessionLocal() as db:
        original=authorized(db,Report,report_id,user)
        case=authorized(db,Case,original.case_id,user)
        if case.status=='MERGED':raise HTTPException(404,'This case has been merged.')
        report=db.scalar(scoped(select(Report).where(Report.case_id==case.id),Report,user).order_by(Report.version.desc(),Report.created_at.desc()).limit(1))
        return {'id':report.id,'case_id':case.id,'customer':report.snapshot['customer'],
                'version':report.version,'state':report.state,'created_at':report.created_at,
                'validation_status':report.snapshot['validation_status'],'provider':report.snapshot['provider'],
                'reference':report.snapshot.get('reference',case.reference),
                'snapshot':report.snapshot}

@router.post("/api/reports/{report_id}/approve")
def approve_report(report_id: str, user=Depends(REVIEW)):
    with SessionLocal.begin() as db:
        r = authorized(db, Report, report_id, user)
        c = db.get(Case, r.case_id)
        latest = db.scalar(
            select(Report)
            .where(Report.case_id == c.id)
            .order_by(Report.version.desc())
            .limit(1)
        )
        if (
            not latest
            or latest.id != r.id
            or c.status != "READY"
            or r.snapshot["validation_status"] not in {"PASS", "FAIL"}
            or r.snapshot.get("missing")
            or any(
                (not e.get("available") or e.get("link_review_required"))
                for d in r.snapshot.get("documents", [])
                for e in d.get("validation", {}).get("visual_evidence", [])
            )
            or any(f["result"] in {"REVIEW", "ERROR"} for f in r.snapshot["findings"])
        ):
            raise HTTPException(
                409,
                "Only the latest ready report with complete processing and no unresolved review findings can be released. Confirmed violations may be released.",
            )
        cfg = get_revision(db, c.config_id)
        if cfg.payload["maker_checker"] and c.created_by == user.id:
            raise HTTPException(403, "A different reviewer must approve this case.")
        r.state = "FINAL"
        r.approved_by = user.id
        persist_report(r)
        c.status = "FINALIZED"
        item = db.scalar(select(Inbox).where(Inbox.case_id == c.id))
        if item:
            item.resolved = True
        audit(
            db,
            user.org,
            user.id,
            "report.approved",
            c.branch_id,
            c.id,
            report_id=r.id,
            version=r.version,
        )
        return {"ok": True}
