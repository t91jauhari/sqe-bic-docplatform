"""Administration application operations.

Transactions, authorization, audit and pinned configuration remain one unit.
"""

from app.errors import ApplicationError
from sqlalchemy import select
from app.db import Branch, RolePermission, SessionLocal, User
from app.auditing import audit
from app.access import branch_allowed
from app.crypto import hash_password
from app.contracts import BranchInput, BranchUpdateInput, UserInput
from app.projections import user_view

DEFAULT_MENUS = ["overview", "inbox", "cases", "reports", "upload", "settings"]

DEFAULT_ROLE_PERMISSIONS = {
    "bank_admin": {
        "label": "Bank Administrator",
        "menus": ["overview", "inbox", "cases", "reports", "upload", "settings"],
        "can_edit_settings": True,
        "can_override_cases": True,
        "can_manage_users": True,
    },
    "branch_admin": {
        "label": "Branch Administrator",
        "menus": ["overview", "inbox", "cases", "reports", "upload", "settings"],
        "can_edit_settings": False,
        "can_override_cases": True,
        "can_manage_users": True,
    },
    "reviewer": {
        "label": "Reviewer / Checker",
        "menus": ["overview", "inbox", "cases", "reports"],
        "can_edit_settings": False,
        "can_override_cases": True,
        "can_manage_users": False,
    },
    "officer": {
        "label": "Officer / Maker",
        "menus": ["overview", "inbox", "cases", "upload"],
        "can_edit_settings": False,
        "can_override_cases": False,
        "can_manage_users": False,
    },
    "auditor": {
        "label": "Compliance Auditor",
        "menus": ["overview", "cases", "reports"],
        "can_edit_settings": False,
        "can_override_cases": False,
        "can_manage_users": False,
    },
}


def branches(*, user):
    with SessionLocal() as db:
        query = select(Branch).where(Branch.org == user.org)
        if user.role != "bank_admin":
            query = query.where(Branch.id.in_(user.branches))
        return [
            {
                "id": b.id,
                "code": b.code,
                "name": b.name,
                "tier": getattr(b, "tier", "KCU") or "KCU",
                "menus": getattr(b, "menus", None) or DEFAULT_MENUS,
            }
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
            org=user.org,
            code=data.code.strip().upper(),
            name=data.name.strip(),
            tier=getattr(data, "tier", None) or "KCU",
            menus=getattr(data, "menus", None) or DEFAULT_MENUS,
        )
        db.add(branch)
        db.flush()
        audit(db, user.org, user.id, "branch.created", branch.id, code=branch.code)
        return {
            "id": branch.id,
            "code": branch.code,
            "name": branch.name,
            "tier": branch.tier,
            "menus": branch.menus,
        }


def update_branch(*, branch_id: str, data: BranchUpdateInput, user):
    with SessionLocal.begin() as db:
        branch = db.scalar(
            select(Branch).where(Branch.org == user.org, Branch.id == branch_id)
        )
        if not branch:
            raise ApplicationError("not_found", "Branch not found.")
        if data.name is not None and data.name.strip():
            branch.name = data.name.strip()
        if data.tier is not None:
            branch.tier = data.tier
        if data.menus is not None:
            branch.menus = data.menus
        db.flush()
        audit(db, user.org, user.id, "branch.updated", branch.id, code=branch.code)
        return {
            "id": branch.id,
            "code": branch.code,
            "name": branch.name,
            "tier": branch.tier,
            "menus": branch.menus,
        }


def get_role_permissions(*, user):
    with SessionLocal() as db:
        stored = {
            r.role: {
                "menus": r.menus or [],
                "can_edit_settings": bool(r.can_edit_settings),
                "can_override_cases": bool(r.can_override_cases),
                "can_manage_users": bool(r.can_manage_users),
            }
            for r in db.scalars(select(RolePermission).where(RolePermission.org == user.org))
        }
        result = {}
        for role, defaults in DEFAULT_ROLE_PERMISSIONS.items():
            override = stored.get(role, {})
            result[role] = {
                "label": defaults["label"],
                "menus": override.get("menus", defaults["menus"]),
                "can_edit_settings": override.get("can_edit_settings", defaults["can_edit_settings"]),
                "can_override_cases": override.get("can_override_cases", defaults["can_override_cases"]),
                "can_manage_users": override.get("can_manage_users", defaults["can_manage_users"]),
            }
        return result


def update_role_permissions(*, data: dict, user):
    with SessionLocal.begin() as db:
        roles_payload = data.get("roles", data)
        for role, perms in roles_payload.items():
            if role not in DEFAULT_ROLE_PERMISSIONS:
                continue
            item = db.scalar(
                select(RolePermission).where(RolePermission.org == user.org, RolePermission.role == role)
            )
            if not item:
                item = RolePermission(
                    org=user.org,
                    role=role,
                    menus=perms.get("menus", []),
                    can_edit_settings=bool(perms.get("can_edit_settings", False)),
                    can_override_cases=bool(perms.get("can_override_cases", False)),
                    can_manage_users=bool(perms.get("can_manage_users", False)),
                )
                db.add(item)
            else:
                if "menus" in perms:
                    item.menus = perms["menus"]
                if "can_edit_settings" in perms:
                    item.can_edit_settings = bool(perms["can_edit_settings"])
                if "can_override_cases" in perms:
                    item.can_override_cases = bool(perms["can_override_cases"])
                if "can_manage_users" in perms:
                    item.can_manage_users = bool(perms["can_manage_users"])

        audit(db, user.org, user.id, "access.role_permissions_updated")
        db.flush()
        return get_role_permissions(user=user)


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
        if db.scalar(
            select(User).where(User.org == user.org, User.email == data.email.strip())
        ):
            raise ApplicationError("conflict", "Email already exists.")
        for branch_id in data.branches:
            branch_allowed(db, branch_id, user)
        row = User(
            org=user.org,
            email=data.email.strip(),
            name=data.name.strip(),
            password_hash=hash_password(data.password),
            role=data.role,
            branches=list(dict.fromkeys(data.branches)),
        )
        db.add(row)
        db.flush()
        audit(
            db,
            user.org,
            user.id,
            "user.created",
            row.id,
            email=row.email,
            role=row.role,
            branches=row.branches,
        )
        return user_view(row)
