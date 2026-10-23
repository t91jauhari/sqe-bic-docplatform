"""Administration HTTP boundary."""
from fastapi import APIRouter
from fastapi import Depends, HTTPException
from sqlalchemy import select
from app.db import Branch, SessionLocal, User
from app.domain import audit
from app.security import branch_allowed, current_user, hash_password
from app.api.dependencies import ADMIN, USER_ADMIN
from app.api.contracts import BranchInput, UserInput
from app.api.views import user_view

router = APIRouter(tags=['administration'])

@router.get("/api/branches")
def branches(user=Depends(current_user)):
    with SessionLocal() as db:
        query = select(Branch).where(Branch.org == user.org)
        if user.role != "bank_admin":
            query = query.where(Branch.id.in_(user.branches))
        return [
            {"id": b.id, "code": b.code, "name": b.name}
            for b in db.scalars(query.order_by(Branch.name))
        ]

@router.post("/api/branches")
def add_branch(data: BranchInput, user=Depends(ADMIN)):
    with SessionLocal.begin() as db:
        if db.scalar(
            select(Branch).where(
                Branch.org == user.org, Branch.code == data.code.strip().upper()
            )
        ):
            raise HTTPException(409, "Branch code already exists.")
        branch = Branch(
            org=user.org, code=data.code.strip().upper(), name=data.name.strip()
        )
        db.add(branch)
        db.flush()
        audit(db, user.org, user.id, "branch.created", branch.id, code=branch.code)
        return {"id": branch.id, "code": branch.code, "name": branch.name}

@router.get("/api/users")
def users(user=Depends(USER_ADMIN)):
    with SessionLocal() as db:
        rows = db.scalars(select(User).where(User.org == user.org)).all()
        return [
            user_view(x)
            for x in rows
            if user.role == "bank_admin" or set(x.branches).intersection(user.branches)
        ]

@router.post("/api/users")
def add_user(data: UserInput, user=Depends(USER_ADMIN)):
    roles = {"bank_admin", "branch_admin", "officer", "reviewer", "auditor"}
    if data.role not in roles or (
        user.role == "branch_admin"
        and data.role not in {"officer", "reviewer", "auditor"}
    ):
        raise HTTPException(403, "Role assignment is not allowed.")
    with SessionLocal.begin() as db:
        for branch in data.branches:
            branch_allowed(db, branch, user)
        if db.scalar(
            select(User).where(
                User.org == user.org, User.email == data.email.strip().lower()
            )
        ):
            raise HTTPException(409, "Email already exists in this organization.")
        created = User(
            org=user.org,
            email=data.email.strip().lower(),
            name=data.name.strip(),
            role=data.role,
            branches=data.branches,
            password_hash=hash_password(data.password),
        )
        db.add(created)
        db.flush()
        audit(
            db,
            user.org,
            user.id,
            "user.created",
            email=created.email,
            role=created.role,
            branches=created.branches,
        )
        return user_view(created)
