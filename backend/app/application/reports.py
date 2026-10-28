"""Reports application operations.

Transactions, authorization, audit and pinned configuration remain one unit.
"""

from app.errors import ApplicationError
from app.configuration.repository import get_revision
from sqlalchemy import select
from app.db import Case, Inbox, Report, SessionLocal
from app.auditing import audit
from app.reporting import persist_report
from app.access import authorized, scoped


def reports(*, user):
    from app.report_queries import ReportAudience, ReportQueries

    audience = ReportAudience(
        user.org, None if user.role == "bank_admin" else tuple(user.branches)
    )
    with SessionLocal() as db:
        return ReportQueries(db, audience).current()


def report_detail(*, report_id: str, user):
    with SessionLocal() as db:
        original = authorized(db, Report, report_id, user)
        case = authorized(db, Case, original.case_id, user)
        if case.status == "MERGED":
            raise ApplicationError("not_found", "This case has been merged.")
        report = db.scalar(
            scoped(select(Report).where(Report.case_id == case.id), Report, user)
            .order_by(Report.version.desc(), Report.created_at.desc())
            .limit(1)
        )
        return {
            "id": report.id,
            "case_id": case.id,
            "customer": report.snapshot["customer"],
            "version": report.version,
            "state": "FINAL",
            "created_at": report.created_at,
            "validation_status": report.snapshot["validation_status"],
            "provider": report.snapshot["provider"],
            "reference": report.snapshot.get("reference", case.reference),
            "snapshot": report.snapshot,
            "case_status": case.status,
            "approved_by": report.approved_by,
        }


def approve_report(*, report_id: str, user):
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
            or c.status not in {"READY", "NEEDS_REVIEW"}
            or r.snapshot.get("missing")
            or any((f.get("result") == "ERROR" for f in r.snapshot.get("findings", [])))
        ):
            raise ApplicationError(
                "conflict",
                "Only the latest report with complete document processing and no unhandled errors can be released.",
            )
        cfg = get_revision(db, c.config_id)
        if cfg.payload["maker_checker"] and c.created_by == user.id:
            raise ApplicationError(
                "forbidden", "A different reviewer must approve this case."
            )
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
