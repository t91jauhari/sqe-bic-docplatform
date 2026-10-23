"""Authentication HTTP boundary."""
from fastapi import APIRouter
import secrets
import time
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from app.db import AuthSession, LoginAttempt, SessionLocal, User
from app.domain import audit
from app.security import current_user, digest, verify_password
from app.settings import settings
from app.api.dependencies import DUMMY_PASSWORD
from app.api.contracts import LoginInput
from app.api.views import user_view

router = APIRouter(tags=['authentication'])

@router.post("/api/auth/login")
def login(data: LoginInput, request: Request, response: Response):
    email, org = data.email.strip().lower(), data.organization.strip().lower()
    # Per-account bucket prevents bypass through spoofed forwarded IP headers.
    key = digest(org + ":" + email)
    with SessionLocal.begin() as db:
        bucket = db.get(LoginAttempt, key)
        if bucket and bucket.window > time.time() - 900 and bucket.count >= 10:
            raise HTTPException(429, "Too many attempts. Try again in 15 minutes.")
        if not bucket:
            bucket = LoginAttempt(id=key, count=0, window=time.time())
            db.add(bucket)
        elif bucket.window < time.time() - 900:
            bucket.count = 0
            bucket.window = time.time()
        user = db.scalar(select(User).where(User.org == org, User.email == email))
        valid = verify_password(
            data.password, user.password_hash if user else DUMMY_PASSWORD
        )
        if not user or not user.active or not valid:
            bucket.count += 1
            db.flush()
            # Commit the counter before returning the generic error.
            db.commit()
            raise HTTPException(401, "Invalid organization, email or password.")
        bucket.count = 0
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        db.add(
            AuthSession(
                id=digest(token),
                user_id=user.id,
                csrf=csrf,
                expires_at=time.time() + 8 * 3600,
            )
        )
        audit(db, org, user.id, "auth.login")
        response.set_cookie(
            "sqe_session",
            token,
            httponly=True,
            secure=settings.secure_cookie,
            samesite="strict",
            max_age=8 * 3600,
            path="/",
        )
        return {"user": user_view(user), "csrf": csrf}

@router.get("/api/auth/session")
def session(request: Request, user=Depends(current_user)):
    return {"user": user_view(user), "csrf": request.state.csrf}

@router.post("/api/auth/logout")
def logout(request: Request, response: Response, user=Depends(current_user)):
    with SessionLocal.begin() as db:
        db.execute(
            delete(AuthSession).where(
                AuthSession.id == digest(request.cookies["sqe_session"])
            )
        )
    response.delete_cookie("sqe_session", path="/")
    return {"ok": True}
