"""Organization and branch authorization shared by application operations."""

from sqlalchemy import select

from .errors import ApplicationError


def scoped(query, model, user):
    query = query.where(model.org == user.org)
    if user.role != "bank_admin":
        query = query.where(model.branch_id.in_(user.branches))
    return query


def authorized(db, model, record_id, user):
    result = db.scalar(scoped(select(model).where(model.id == record_id), model, user))
    if not result:
        raise ApplicationError("not_found", "Record not found.")
    return result


def branch_allowed(db, branch_id, user):
    from .db import Branch

    branch = db.get(Branch, branch_id)
    if (
        not branch
        or branch.org != user.org
        or (user.role != "bank_admin" and branch_id not in user.branches)
    ):
        raise ApplicationError("forbidden", "Branch access denied.")
    return branch
