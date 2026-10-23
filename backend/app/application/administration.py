"""Administration application operations.

Transactions, authorization, audit and pinned configuration remain one unit.
"""

from app.errors import ApplicationError
from sqlalchemy import select
from app.db import Branch, SessionLocal, User
from app.auditing import audit
from app.access import branch_allowed
from app.crypto import hash_password
from app.contracts import BranchInput, UserInput
from app.projections import user_view


def branches(*, user):
    with SessionLocal() as db:
        query = select(Branch).where(Branch.org == user.org)
        if user.role != "bank_admin":
            query = query.where(Branch.id.in_(user.branches))
        return [
            {"id": b.id, "code": b.code, "name": b.name}
            for b in db.scalars(query.order_by(Branch.name))
        ]


def add_branch(*, data: BranchInput, user):
    with SessionLocal.begin() as db:
        if db.scalar(
            select(Branch).where(
                Branch.org == user.org, Branch.code == data.code.strip().upper()
            )
        ):
            raise ApplicationError("conflict", "Branch code already exists.")
        branch = Branch(
            org=user.org, code=data.code.strip().upper(), name=data.name.strip()
        )
        db.add(branch)
        db.flush()
        audit(db, user.org, user.id, "branch.created", branch.id, code=branch.code)
        return {"id": branch.id, "code": branch.code, "name": branch.name}


def users(*, user):
    with SessionLocal() as db:
        rows = db.scalars(select(User).where(User.org == user.org)).all()
        return [
            user_view(x)
            for x in rows
            if user.role == "bank_admin" or set(x.branches).intersection(user.branches)
        ]


def add_user(*, data: UserInput, user):
    roles = {"bank_admin", "branch_admin", "officer", "reviewer", "auditor"}
    if data.role not in roles or (
        user.role == "branch_admin"
        and data.role not in {"officer", "reviewer", "auditor"}
    ):
        raise ApplicationError("forbidden", "Role assignment is not allowed.")
    with SessionLocal.begin() as db:
        for branch in data.branches:
            branch_allowed(db, branch, user)
        if db.scalar(
            select(User).where(
                User.org == user.org, User.email == data.email.strip().lower()
            )
        ):
            raise ApplicationError(
                "conflict", "Email already exists in this organization."
            )
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
