import base64
import hashlib
import hmac
import os
import time

from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select

from .db import AuthSession, SessionLocal, User
from .settings import settings


def hash_password(password):
    salt = os.urandom(16)
    result = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return base64.b64encode(salt + result).decode()


def verify_password(password, stored):
    try:
        data = base64.b64decode(stored)
        return hmac.compare_digest(
            data[16:],
            hashlib.scrypt(
                password.encode(), salt=data[:16], n=16384, r=8, p=1, dklen=32
            ),
        )
    except (ValueError, TypeError):
        return False


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def encrypt(value):
    return (
        Fernet(
            base64.urlsafe_b64encode(hashlib.sha256(settings.secret.encode()).digest())
        )
        .encrypt(value.encode())
        .decode()
    )


def decrypt(value):
    return (
        Fernet(
            base64.urlsafe_b64encode(hashlib.sha256(settings.secret.encode()).digest())
        )
        .decrypt(value.encode())
        .decode()
        if value
        else ""
    )


def current_user(request: Request):
    token = request.cookies.get("sqe_session", "")
    with SessionLocal() as db:
        session = db.get(AuthSession, digest(token))
        if not session or session.expires_at < time.time():
            raise HTTPException(401, "Please sign in.")
        user = db.get(User, session.user_id)
        if not user or not user.active:
            raise HTTPException(401, "Account unavailable.")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not hmac.compare_digest(
            request.headers.get("X-CSRF-Token", ""), session.csrf
        ):
            raise HTTPException(403, "Invalid CSRF token.")
        request.state.csrf = session.csrf
        return user


def require_roles(*roles):
    def dependency(user=Depends(current_user)):
        if user.role not in roles:
            raise HTTPException(403, "This action requires a different role.")
        return user

    return dependency


def scoped(query, model, user):
    query = query.where(model.org == user.org)
    if user.role != "bank_admin":
        query = query.where(model.branch_id.in_(user.branches))
    return query


def authorized(db, model, record_id, user):
    result = db.scalar(scoped(select(model).where(model.id == record_id), model, user))
    if not result:
        raise HTTPException(404, "Record not found.")
    return result


def branch_allowed(db, branch_id, user):
    from .db import Branch

    branch = db.get(Branch, branch_id)
    if (
        not branch
        or branch.org != user.org
        or (user.role != "bank_admin" and branch_id not in user.branches)
    ):
        raise HTTPException(403, "Branch access denied.")
    return branch
