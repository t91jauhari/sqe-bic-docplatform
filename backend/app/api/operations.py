"""Operations HTTP boundary."""
from fastapi import APIRouter
import time
from fastapi import Depends
from sqlalchemy import func, select
from app.db import Case, CaseTask, CaseRun, Document, Inbox, Job, SessionLocal
from app.domain import latest_config
from app.security import current_user, scoped
from app.settings import settings
from app.api.dependencies import ADMIN
from app.api.views import case_view

router = APIRouter(tags=['operations'])

@router.get("/api/operations/metrics")
def operations_metrics(user=Depends(ADMIN)):
    with SessionLocal() as db:
        return {
            "organization": user.org,
            "documents": {
                state: count
                for state, count in db.execute(
                    select(Document.status, func.count())
                    .where(Document.org == user.org)
                    .group_by(Document.status)
                )
            },
            "document_jobs": {
                state: count
                for state, count in db.execute(
                    select(Job.status, func.count())
                    .where(Job.org == user.org)
                    .group_by(Job.status)
                )
            },
            "case_runs": {
                state: count
                for state, count in db.execute(
                    select(CaseRun.status, func.count())
                    .where(CaseRun.org == user.org)
                    .group_by(CaseRun.status)
                )
            },
            "overdue_assignments": db.scalar(
                select(func.count())
                .select_from(CaseTask)
                .join(Case, Case.id == CaseTask.case_id)
                .where(
                    CaseTask.org == user.org,
                    CaseTask.due_at < time.time(),
                    Case.status.notin_(["FINALIZED", "APPROVED"]),
                )
            )
            or 0,
        }

@router.get("/api/dashboard")
def dashboard(user=Depends(current_user)):
    with SessionLocal() as db:
        case_states = db.scalars(
            scoped(select(Case.status).where(Case.status != "MERGED"), Case, user)
        ).all()
        document_count = db.scalar(
            scoped(select(func.count()).select_from(Document), Document, user)
        )
        completed_count = db.scalar(
            scoped(
                select(func.count())
                .select_from(Document)
                .where(Document.status == "COMPLETED"),
                Document,
                user,
            )
        )
        items = db.scalars(
            scoped(select(Inbox.read_by).where(Inbox.resolved.is_(False)), Inbox, user)
        ).all()
        recent = db.scalars(
            scoped(select(Case).where(Case.status != "MERGED"), Case, user)
            .order_by(Case.updated_at.desc())
            .limit(8)
        ).all()
        cfg = latest_config(db, user.org)
        return {
            "cases": len(case_states),
            "documents": document_count,
            "completed_documents": completed_count,
            "processing": sum(x in {"QUEUED", "PROCESSING"} for x in case_states),
            "attention": sum(
                x in {"NEEDS_REVIEW", "WAITING_DOCUMENTS", "PROCESSING_ERROR"}
                for x in case_states
            ),
            "ready": sum(x in {"READY", "FINALIZED"} for x in case_states),
            "unread": sum(user.id not in x for x in items),
            "provider": cfg.payload["provider"],
            "workflow_driver": settings.workflow_driver,
            "config_version": cfg.version,
            "recent": [case_view(c, db) for c in recent],
        }
