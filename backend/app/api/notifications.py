"""Notifications HTTP boundary."""
from fastapi import APIRouter
import time
from fastapi import Depends, HTTPException
from sqlalchemy import select
from app.db import Audit, CaseTask, Inbox, SessionLocal
from app.security import authorized, current_user, scoped

router = APIRouter(tags=['notifications'])

@router.get("/api/inbox")
def inbox(offset: int = 0, user=Depends(current_user)):
    if offset < 0:
        raise HTTPException(422, "Offset must be nonnegative.")
    with SessionLocal() as db:
        rows = db.scalars(
            scoped(select(Inbox).where(Inbox.resolved.is_(False)), Inbox, user)
            .order_by(Inbox.created_at.desc(), Inbox.id.desc())
            .offset(offset)
            .limit(100)
        )
        tasks = {
            t.case_id: t for t in db.scalars(scoped(select(CaseTask), CaseTask, user))
        }
        return [
            {
                "assigned_to": tasks[x.case_id].assigned_to
                if x.case_id in tasks
                else None,
                "due_at": tasks[x.case_id].due_at if x.case_id in tasks else None,
                "overdue": bool(
                    x.case_id in tasks
                    and tasks[x.case_id].due_at
                    and tasks[x.case_id].due_at < time.time()
                ),
                "id": x.id,
                "case_id": x.case_id,
                "title": x.title,
                "body": x.body,
                "severity": x.severity,
                "read": user.id in x.read_by,
                "created_at": x.created_at,
            }
            for x in rows
        ]

@router.post("/api/inbox/{item_id}/read")
def read_inbox(item_id: str, user=Depends(current_user)):
    with SessionLocal.begin() as db:
        item = authorized(db, Inbox, item_id, user)
        item.read_by = list(set(item.read_by + [user.id]))
        return {"ok": True}

@router.get("/api/events")
def events(after: float = 0, user=Depends(current_user)):
    with SessionLocal() as db:
        query = select(Audit).where(Audit.org == user.org, Audit.created_at > after)
        if user.role != "bank_admin":
            query = query.where(Audit.branch_id.in_(user.branches))
        rows = db.scalars(query.order_by(Audit.created_at).limit(200)).all()
        return {
            "cursor": max([x.created_at for x in rows], default=after),
            "items": [
                {
                    "id": x.id,
                    "case_id": x.case_id,
                    "event": x.event,
                    "created_at": x.created_at,
                }
                for x in rows
            ],
        }
