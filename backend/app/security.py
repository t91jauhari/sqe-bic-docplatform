from .crypto import decrypt, digest, encrypt, hash_password, verify_password
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


def current_user(request: Request):
    token = request.cookies.get("sqe_session", "")
    with SessionLocal() as db:
        session = db.get(AuthSession, digest(token))
        if not session or session.expires_at < time.time():
            raise HTTPException(401, "Please sign in.")
        user = db.get(User, session.user_id)
        if not user or not user.active:
            raise HTTPException(401, "Account unavailable.")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and (
            not hmac.compare_digest(
                request.headers.get("X-CSRF-Token", ""), session.csrf
            )
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


from .access import scoped, authorized, branch_allowed
