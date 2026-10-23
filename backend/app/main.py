from .configuration.repository import get_revision
from .configuration.profiles import profile_schema, validate_shape
import copy
import csv
import hashlib
import io
import json
import logging
import re
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit, quote

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import JSONResponse
from minio.error import S3Error
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from starlette.concurrency import run_in_threadpool
from urllib3.exceptions import HTTPError as StorageHTTPError

from .db import (
    Audit,
    AuthSession,
    Batch,
    Branch,
    Case,
    CaseTask,
    CaseContext,
    CaseRun,
    Config,
    Document,
    DatasetComparison,
    Inbox,
    Job,
    LoginAttempt,
    Report,
    SessionLocal,
    User,
    uid,
)
from .domain import (
    LABELS,
    audit,
    enqueue,
    get_profile,
    latest_config,
    refresh_case,
    seed,
    validate_config,
)
from .grouping import plan_grouping
from .reporting import csv_safe, make_report, persist_report, report_key
from .security import (
    authorized,
    branch_allowed,
    current_user,
    digest,
    hash_password,
    require_roles,
    scoped,
    verify_password,
)
from .settings import settings
from .storage import object_key, original_key, store, sniff_mime, fitz_open_original

WRITE = require_roles("bank_admin", "branch_admin", "officer", "reviewer")
REVIEW = require_roles("bank_admin", "branch_admin", "reviewer")
ADMIN = require_roles("bank_admin")
USER_ADMIN = require_roles("bank_admin", "branch_admin")
log = logging.getLogger("sqe.api")
DUMMY_PASSWORD = hash_password(secrets.token_urlsafe(24))


@asynccontextmanager
async def lifespan(_):
    from .worker_capacity import initialize_slots

    initialize_slots()
    yield


app = FastAPI(title="SQE Document Automation API", version="0.2.0", lifespan=lifespan)
from .configuration.api import router as configuration_router
app.include_router(configuration_router)
from .extraction.api import router as extraction_settings_router
app.include_router(extraction_settings_router)
from .configuration.routes import router as configuration_upgrade_router, compatibility_router

app.include_router(configuration_upgrade_router)
app.include_router(compatibility_router)
from .configuration.dataset_routes import router as dataset_registry_router
from .configuration.datasets import DatasetIntegrityError
app.include_router(dataset_registry_router)
from .configuration.report_routes import router as report_configuration_router
app.include_router(report_configuration_router)
from .configuration.account_policy_routes import router as account_policy_router
app.include_router(account_policy_router)


@app.exception_handler(DatasetIntegrityError)
async def dataset_integrity_failure(request, exc):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(S3Error)
@app.exception_handler(StorageHTTPError)
async def storage_unavailable(request, exc):
    log.error("object_storage_failed error_type=%s", type(exc).__name__)
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Document storage is unavailable. Check MinIO connectivity, bucket and server credentials, then retry."
        },
    )


@app.middleware("http")
async def security_headers(request, call_next):
    origin = request.headers.get("origin")
    if (
        request.method not in {"GET", "HEAD", "OPTIONS"}
        and origin
        and origin not in settings.origins
    ):
        return Response("Origin not allowed", status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


class LoginInput(BaseModel):
    organization: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


def user_view(user):
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "organization": user.org,
        "branches": user.branches,
        "active": user.active,
    }


@app.post("/api/auth/login")
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


@app.get("/api/auth/session")
def session(request: Request, user=Depends(current_user)):
    return {"user": user_view(user), "csrf": request.state.csrf}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, user=Depends(current_user)):
    with SessionLocal.begin() as db:
        db.execute(
            delete(AuthSession).where(
                AuthSession.id == digest(request.cookies["sqe_session"])
            )
        )
    response.delete_cookie("sqe_session", path="/")
    return {"ok": True}


@app.get("/api/health")
def health():
    with SessionLocal() as db:
        db.execute(select(1))
    return {"status": "ok", "version": "0.3.0"}


@app.get("/api/operations/metrics")
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


@app.get("/api/branches")
def branches(user=Depends(current_user)):
    with SessionLocal() as db:
        query = select(Branch).where(Branch.org == user.org)
        if user.role != "bank_admin":
            query = query.where(Branch.id.in_(user.branches))
        return [
            {"id": b.id, "code": b.code, "name": b.name}
            for b in db.scalars(query.order_by(Branch.name))
        ]


class BranchInput(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)


@app.post("/api/branches")
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


@app.get("/api/users")
def users(user=Depends(USER_ADMIN)):
    with SessionLocal() as db:
        rows = db.scalars(select(User).where(User.org == user.org)).all()
        return [
            user_view(x)
            for x in rows
            if user.role == "bank_admin" or set(x.branches).intersection(user.branches)
        ]


class UserInput(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=200)
    role: str
    branches: list[str] = Field(min_length=1, max_length=100)


@app.post("/api/users")
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


class PreviewInput(BaseModel):
    filenames: list[str] = Field(max_length=100)


@app.post("/api/uploads/preview")
def preview_upload(data: PreviewInput, user=Depends(WRITE)):
    with SessionLocal() as db:
        cfg = latest_config(db, user.org).payload
    return plan_grouping(data.filenames, cfg)


class SpiderResubmit(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)
    accept_possible_duplicate_charge: bool


@app.post("/api/documents/{doc_id}/spider-resubmit", status_code=202)
def spider_resubmit(doc_id: str, data: SpiderResubmit, user=Depends(WRITE)):
    with SessionLocal.begin() as db:
        d = authorized(db, Document, doc_id, user)
        pending = str(d.provider_state.get("pending_create") or "")
        stage = (
            pending.removeprefix("spider_")
            if pending.startswith("spider_")
            else str(d.provider_state.get("provider_stage", ""))
            .removeprefix("SPIDER_")
            .lower()
        )
        cached_key = d.provider_state.get(f"spider_{stage}_response_key")
        if stage.startswith('fields_'):
            raise HTTPException(409,'This is a failed field reread. Resume its field request instead of resubmitting the whole document.')
        if (
            d.status != "ERROR"
            or not (
                stage in {"classify", "extract"}
                or re.fullmatch(r"extract_page_([1-9]|1[0-9]|20)", stage)
            )
            or not (pending.startswith("spider_") or cached_key)
            or not data.accept_possible_duplicate_charge
        ):
            raise HTTPException(
                409,
                "Only uncertain or cached failed Spider-AI submissions can be explicitly resubmitted.",
            )
        state = {**d.provider_state, "pending_create": None}
        state.pop(f"spider_{stage}_response_key", None)
        d.provider_state = state
        if stage.startswith("extract"):
            d.raw = {}
            d.metadata_json = {}
        job = enqueue(db, d)
        audit(
            db,
            user.org,
            user.id,
            "spider.resubmission_authorized",
            d.branch_id,
            d.case_id,
            document_id=d.id,
            reason=data.reason,
            duplicate_charge_accepted=True,
            stage=stage,
            previous_response_key=cached_key,
        )
        db.flush()
        return {"job_id": job.id}


@app.get("/api/documents/failure-summary")
def failure_summary(since: float = 0, user=Depends(current_user)):
    """Group recent document errors by their first-line prefix so the UI can
    surface transient-failure clusters (e.g. one network outage failing many
    uploads). Read-only and org-scoped via `authorized`/scoped queries."""
    since = max(0.0, float(since or 0))
    with SessionLocal() as db:
        query = scoped(select(Document), Document, user).where(
            Document.error != "",
            Document.created_at >= since,
        )
        rows = db.scalars(query).all()
        grouped: dict[str, dict] = {}
        for d in rows:
            prefix = " ".join((d.error or "").split()[:8]) or "Unknown error"
            entry = grouped.setdefault(
                prefix,
                {"error_prefix": prefix, "count": 0, "case_ids": [], "first_seen": d.created_at},
            )
            entry["count"] += 1
            if d.case_id not in entry["case_ids"]:
                entry["case_ids"].append(d.case_id)
            entry["first_seen"] = min(entry["first_seen"], d.created_at)
        return sorted(grouped.values(), key=lambda g: -g["count"])



def case_view(c, db):
    states = db.scalars(select(Document.status).where(Document.case_id == c.id)).all()
    docs = db.scalars(select(Document).where(Document.case_id == c.id)).all()
    payload = get_revision(db, c.config_id).payload
    missing_documents = sorted(
        {
            payload["profiles"][d.doc_type]["label"]
            for d in docs
            if d.doc_type in payload["profiles"] and d.status != "COMPLETED"
        }
    )
    return {
        "id": c.id,
        "reference": c.reference,
        "customer": c.customer,
        "branch_id": c.branch_id,
        "status": c.status,
        "validation_status": c.validation_status,
        "template": c.template,
        "transaction_flow_label": payload["templates"][
            c.template
        ]["label"],
        "created_at": c.created_at,
        "updated_at": c.updated_at,
        "documents_count": len(states),
        "completed_count": sum(x == "COMPLETED" for x in states),
        "missing_documents": missing_documents,
        "created_by": c.created_by,
        "config_version": get_revision(db, c.config_id).version,
    }


@app.post("/api/uploads", status_code=202)
async def upload(
    branch_id: Annotated[str, Form()],
    template: Annotated[str, Form()],
    files: Annotated[list[UploadFile], File()],
    grouping: Annotated[str, Form()] = "{}",
    case_id: Annotated[str, Form()] = "",
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")] = "",
    user=Depends(WRITE),
):
    if not idempotency_key or len(idempotency_key) > 100:
        raise HTTPException(422, "Provide an Idempotency-Key.")
    if not 1 <= len(files) <= settings.max_batch_files:
        raise HTTPException(422, "Upload between 1 and 100 documents.")
    try:
        labels = json.loads(grouping)
    except ValueError:
        raise HTTPException(422, "Invalid grouping labels.")
    if not isinstance(labels, dict) or any(
        not isinstance(x, str) or not x.strip() or len(x) > 180 for x in labels.values()
    ):
        raise HTTPException(
            422, "Customer labels must be nonempty strings up to 180 characters."
        )
    prepared = []
    try:
        with SessionLocal() as db:
            branch_allowed(db, branch_id, user)
            previous = db.scalar(
                select(Batch).where(
                    Batch.org == user.org,
                    Batch.created_by == user.id,
                    Batch.idempotency_key == idempotency_key,
                )
            )
            if previous:
                if previous.branch_id != branch_id:
                    raise HTTPException(
                        409, "Upload key was used in a different branch."
                    )
                docs = db.scalars(
                    select(Document).where(Document.batch_id == previous.id)
                ).all()
                return {
                    "batch_id": previous.id,
                    "case_ids": list(dict.fromkeys(d.case_id for d in docs)),
                    "replayed": True,
                }
            cfg = latest_config(db, user.org)
            existing = authorized(db, Case, case_id, user) if case_id else None
            if existing:
                cfg = get_revision(db, existing.config_id)
                template = existing.template
            elif template not in cfg.payload["templates"] or not cfg.payload[
                "templates"
            ][template].get("enabled", True):
                raise HTTPException(422, "Select an active transaction flow.")
            from .document_families import families
            if not existing and not families(cfg.payload)[cfg.payload['templates'][template].get('document_family','forex')].get('enabled',True):
                raise HTTPException(422, 'This document family is inactive. Select a flow in an active family.')
            upload_step = next(
                (s for s in cfg.payload.get("workflow", []) if s["action"] == "upload"),
                {},
            )
            limits = upload_step.get("parameters", {})
            if len(files) > limits.get("max_files", settings.max_batch_files):
                raise HTTPException(
                    422, "File count exceeds the configured upload limit."
                )
            if existing and existing.branch_id != branch_id:
                raise HTTPException(422, "Case belongs to another branch.")
            filenames = [
                Path((f.filename or "").replace("\\", "/")).name for f in files
            ]
            if len(set(filenames)) != len(filenames):
                raise HTTPException(422, "Filenames must be unique within an upload.")
            if any(k not in filenames for k in labels):
                raise HTTPException(422, "Grouping contains an unknown filename.")
            planned = plan_grouping(filenames, cfg.payload, labels)
            if existing:
                for row in planned:
                    row.update(
                        customer=existing.customer,
                        status="manual",
                        explanation="Attached to the case selected by the user.",
                    )
            if not existing and any(p["status"] == "unresolved" for p in planned):
                raise HTTPException(
                    422,
                    {
                        "message": "Resolve document grouping before upload.",
                        "documents": planned,
                    },
                )
            plan = {p["filename"]: p for p in planned}
        # Persist all originals before queuing any work. No worker can see a partial batch.
        for f in files:
            filename = Path((f.filename or "").replace("\\", "/")).name
            if not filename.lower().endswith((".pdf", ".png", ".jpg", ".jpeg")) or len(filename) > 240:
                raise HTTPException(
                    422, "Only PDF, PNG or JPG files with valid filenames are accepted."
                )
            doc_id = uid()
            ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else "pdf"
            is_image = ext in {"png", "jpg", "jpeg"}
            mime = (
                {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}[ext]
                if is_image
                else "application/pdf"
            )
            key = object_key(
                user.org, branch_id, "documents", doc_id, f"original.{ext}"
            )
            size = 0
            sha = hashlib.sha256()
            prepared.append({"id": doc_id, "filename": filename, "key": key})
            chunks = bytearray()
            while data := await f.read(1024 * 1024):
                if size == 0:
                    # Validate magic bytes: PDF, PNG or JPEG signatures.
                    if not (
                        data.startswith(b"%PDF-")
                        or data.startswith(b"\x89PNG\r\n\x1a\n")
                        or data.startswith(b"\xff\xd8\xff")
                    ):
                        raise HTTPException(
                            422, f"{filename}: invalid PDF or image header."
                        )
                size += len(data)
                if size > min(
                    settings.max_file_bytes, limits.get("max_mb", 30) * 1024 * 1024
                ):
                    raise HTTPException(413, f"{filename}: file exceeds 30 MB.")
                chunks.extend(data)
                sha.update(data)
            if size == 0:
                raise HTTPException(422, "Empty PDF.")
            await run_in_threadpool(store().put, key, bytes(chunks), mime)
            prepared[-1]["sha256"] = sha.hexdigest()
        with SessionLocal.begin() as db:
            batch = Batch(
                org=user.org,
                branch_id=branch_id,
                created_by=user.id,
                idempotency_key=idempotency_key,
            )
            db.add(batch)
            db.flush()
            grouped = {}
            case_ids = []
            for p in prepared:
                resolved = plan[p["filename"]]
                hint, customer, classification = (
                    resolved["hint"],
                    resolved["customer"],
                    resolved["classification"],
                )
                # Group by customer within this branch and batch; never merge historical cases by name.
                grouping_key = customer.casefold()
                if existing:
                    case = authorized(db, Case, existing.id, user)
                elif grouping_key in grouped:
                    case = grouped[grouping_key]
                else:
                    case = Case(
                        org=user.org,
                        branch_id=branch_id,
                        customer=customer,
                        reference=f"{customer} / {batch.id[:8]}",
                        template=template,
                        created_by=user.id,
                        config_id=cfg.id,
                    )
                    db.add(case)
                    db.flush()
                    grouped[grouping_key] = case
                    audit(
                        db,
                        user.org,
                        user.id,
                        "case.grouped_from_filename",
                        branch_id,
                        case.id,
                        customer=customer,
                        batch_id=batch.id,
                    )
                if case.id not in case_ids:
                    case_ids.append(case.id)
                duplicate = db.scalar(
                    select(Document).where(
                        Document.case_id == case.id, Document.sha256 == p["sha256"]
                    )
                )
                if duplicate:
                    await run_in_threadpool(store().delete, p["key"])
                    continue
                doc = Document(
                    id=p["id"],
                    org=user.org,
                    branch_id=branch_id,
                    case_id=case.id,
                    batch_id=batch.id,
                    filename=p["filename"],
                    sha256=p["sha256"],
                    provider_state={
                        "storage_key": p["key"],
                        "grouping": {
                            k: v for k, v in resolved.items() if k != "classification"
                        },
                    },
                    doc_type=hint,
                    classification=classification,
                )
                db.add(doc)
                db.flush()
            # Only after every document has case membership is classification/extraction queued.
            for doc in db.scalars(
                select(Document).where(Document.batch_id == batch.id)
            ):
                enqueue(db, doc)
            audit(
                db,
                user.org,
                user.id,
                "batch.accepted",
                branch_id,
                batch_id=batch.id,
                file_count=len(prepared),
                case_ids=case_ids,
            )
            return {"batch_id": batch.id, "case_ids": case_ids, "replayed": False}
    except Exception:
        for p in prepared:
            try:
                await run_in_threadpool(store().delete, p["key"])
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to clean up uncommitted upload %s", p["id"]
                )
        raise


class RegroupInput(BaseModel):
    labels: dict[str, str]
    revision: str
    reason: str = Field(min_length=5, max_length=1000)


@app.get("/api/batches/{batch_id}/grouping")
def preview_batch_grouping(batch_id: str, user=Depends(REVIEW)):
    from .grouping_repair import preview

    with SessionLocal() as db:
        return preview(db, batch_id, user)


@app.post("/api/batches/{batch_id}/grouping")
def repair_batch_grouping(batch_id: str, data: RegroupInput, user=Depends(REVIEW)):
    from .grouping_repair import apply

    with SessionLocal.begin() as db:
        return apply(db, batch_id, user, data.labels, data.revision, data.reason)


@app.get("/api/dashboard")
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


@app.get("/api/cases")
def cases(
    q: str = "",
    status: str = "",
    transaction_flow: str = "",
    offset: int = 0,
    limit: int = 50,
    user=Depends(current_user),
):
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    with SessionLocal() as db:
        query = scoped(select(Case), Case, user)
        if not status:
            query = query.where(Case.status != "MERGED")
        if transaction_flow:
            query = query.where(Case.template == transaction_flow)
        if q:
            query = query.where(Case.customer.ilike("%" + q[:100] + "%"))
        if status:
            query = query.where(Case.status == status)
        count = db.scalar(select(func.count()).select_from(query.subquery()))
        return {
            "total": count,
            "items": [
                case_view(c, db)
                for c in db.scalars(
                    query.order_by(Case.updated_at.desc()).offset(offset).limit(limit)
                )
            ],
        }


def doc_view(d):
    return {
        "id": d.id,
        "filename": d.filename,
        "doc_type": d.doc_type,
        "status": d.status,
        "validation_status": d.validation_status,
        "classification": d.classification,
        "provider_state": d.provider_state,
        "raw": d.raw,
        "normalized": d.normalized,
        "overrides": d.overrides,
        "validation": d.validation,
        "error": d.error,
        "case_id": d.case_id,
    }


@app.get("/api/cases/{case_id}")
def case_detail(case_id: str, user=Depends(current_user)):
    with SessionLocal() as db:
        c = authorized(db, Case, case_id, user)
        docs = db.scalars(
            select(Document)
            .where(Document.case_id == c.id)
            .order_by(Document.created_at)
        ).all()
        reports = db.scalars(
            select(Report).where(Report.case_id == c.id).order_by(Report.version.desc())
        ).all()
        events = db.scalars(
            select(Audit)
            .where(Audit.case_id == c.id)
            .order_by(Audit.created_at.desc())
            .limit(100)
        ).all()
        return {
            **case_view(c, db),
            "context_suggestions": __import__(
                "app.case_context", fromlist=["suggestions"]
            ).suggestions(docs),
            "case_context": (
                db.scalar(
                    select(CaseContext).where(CaseContext.case_id == c.id)
                ).payload
                if db.scalar(select(CaseContext).where(CaseContext.case_id == c.id))
                else {}
            ),
            "sop_runs": [
                {
                    "id": run.id,
                    "status": run.status,
                    "stage": run.stage,
                    "error": run.error,
                    "snapshot_hash": run.fingerprint,
                    "created_at": run.created_at,
                }
                for run in db.scalars(
                    select(CaseRun)
                    .where(CaseRun.case_id == c.id)
                    .order_by(CaseRun.created_at.desc())
                    .limit(10)
                )
            ],
            "documents": [doc_view(d) for d in docs],
            "reports": [
                {
                    "id": r.id,
                    "version": r.version,
                    "state": r.state,
                    "created_at": r.created_at,
                    "approved_by": r.approved_by,
                    "snapshot": {
                        key: r.snapshot.get(key)
                        for key in [
                            "findings",
                            "missing",
                            "validation_status",
                            "provider",
                            "customer",
                            "config_version",
                            "scores",
                            "sop_summary",
                            "sop_packages",
                            "technical_findings",
                        ]
                    },
                }
                for r in reports
            ],
            "timeline": [
                {
                    "id": e.id,
                    "event": e.event,
                    "actor": e.actor,
                    "created_at": e.created_at,
                    "details": e.details,
                }
                for e in events
            ],
            "can_write": user.role not in {"auditor"},
            "can_review": user.role in {"bank_admin", "branch_admin", "reviewer"},
            "maker_checker": get_revision(db, c.config_id).payload["maker_checker"],
        }


class ComparisonInput(BaseModel):
    expected_revision: int = Field(ge=0)
    sample_id: str
    documents: dict[str, str] = Field(default_factory=dict)
    edits: dict[str, object] = Field(default_factory=dict)
    reason: str = Field(min_length=5, max_length=1000)


@app.get("/api/dataset-sample")
def dataset_sample(case_id: str = "", user=Depends(current_user)):
    from .dataset_comparison import dataset_for_case
    from .configuration.dataset_sources import resolve_dataset

    if not case_id:
        with SessionLocal() as db:
            return resolve_dataset(db, user.org, "forex-sample-v1")
    with SessionLocal() as db:
        case = authorized(db, Case, case_id, user)
        return dataset_for_case(db, case)


def comparison_view(db, case, state):
    from .dataset_comparison import compare, dataset_for_case

    docs = db.scalars(
        select(Document)
        .where(Document.case_id == case.id)
        .order_by(Document.created_at)
    ).all()
    from .configuration.dataset_policy import comparison_policy
    policy = comparison_policy(get_revision(db, case.config_id).payload, case.template)
    return compare(case, docs, state, dataset_for_case(db, case), policy=policy)


@app.get("/api/cases/{case_id}/comparison")
def dataset_comparison(case_id: str, user=Depends(current_user)):
    with SessionLocal() as db:
        case = authorized(db, Case, case_id, user)
        item = db.scalar(
            select(DatasetComparison).where(DatasetComparison.case_id == case.id)
        )
        return comparison_view(db, case, item.payload if item else {})


@app.put("/api/cases/{case_id}/comparison")
def edit_comparison(case_id: str, data: ComparisonInput, user=Depends(WRITE)):
    from .dataset_comparison import dataset_for_case

    with SessionLocal.begin() as db:
        case = authorized(db, Case, case_id, user)
        DATASET = dataset_for_case(db, case)
        if data.sample_id not in {s["id"] for s in DATASET["samples"]}:
            raise HTTPException(
                422, "Unknown dataset sample for this transaction flow."
            )
        rows = {r["id"]: r for r in DATASET["rows"]}
        if (
            any(k not in rows for k in data.edits)
            or len(json.dumps(data.edits)) > 200_000
        ):
            raise HTTPException(
                422, "Unknown reference field or reference edits are too large."
            )
        sections = {str(r["section"]): r["document_type"] for r in rows.values()}
        # Lock the case as well to serialize first writes before a comparison row exists.
        db.scalar(select(Case).where(Case.id == case.id).with_for_update())
        item = db.scalar(
            select(DatasetComparison)
            .where(DatasetComparison.case_id == case.id)
            .with_for_update()
        )
        previous = item.payload if item else {}
        if previous.get("revision", 0) != data.expected_revision:
            raise HTTPException(
                409, "Comparison changed. Reload before saving your edits."
            )
        for section, doc_id in data.documents.items():
            doc = db.get(Document, doc_id)
            if (
                section not in sections
                or not doc
                or doc.case_id != case.id
                or doc.org != case.org
                or doc.doc_type != sections[section]
            ):
                raise HTTPException(
                    422,
                    "Source document must belong to this case and match the section type.",
                )
        edits = (
            copy.deepcopy(previous.get("edits", {}))
            if previous.get("sample_id") == data.sample_id
            else {}
        )
        for row_id, value in data.edits.items():
            if value is not None and not isinstance(
                value, (str, bool, int, float, list, dict)
            ):
                raise HTTPException(422, "Unsupported reference value.")
            edits[row_id] = {
                "value": value,
                "actor": user.id,
                "reason": data.reason,
                "at": time.time(),
            }
        payload = {
            "revision": data.expected_revision + 1,
            "sample_id": data.sample_id,
            "documents": data.documents,
            "edits": edits,
        }
        if not item:
            item = DatasetComparison(
                org=case.org, branch_id=case.branch_id, case_id=case.id, payload=payload
            )
            db.add(item)
        else:
            item.payload = payload
        audit(
            db,
            case.org,
            user.id,
            "dataset.comparison_saved",
            case.branch_id,
            case.id,
            before=previous,
            after=payload,
            reason=data.reason,
        )
        return comparison_view(db, case, payload)


@app.get("/api/cases/{case_id}/comparison/export")
def export_comparison(case_id: str, format: str = "csv", user=Depends(current_user)):
    if format not in {"csv", "json"}:
        raise HTTPException(422, "Supported comparison formats: csv, json.")
    with SessionLocal.begin() as db:
        case = authorized(db, Case, case_id, user)
        item = db.scalar(
            select(DatasetComparison).where(DatasetComparison.case_id == case.id)
        )
        result = comparison_view(db, case, item.payload if item else {})
        if not result.get("sample_id"):
            raise HTTPException(
                409, "Select and save a dataset sample before exporting."
            )
        result["exported_at"] = time.time()
        audit(
            db,
            case.org,
            user.id,
            "dataset.comparison_exported",
            case.branch_id,
            case.id,
            revision=result["revision"],
            fingerprint=result["fingerprint"],
            format=format,
        )
        if format == "json":
            body = json.dumps(result, ensure_ascii=False, indent=2)
            mime = "application/json"
        else:
            stream = io.StringIO()
            writer = csv.writer(stream)
            columns = [
                "case_id",
                "customer",
                "sample_name",
                "revision",
                "fingerprint",
                "dataset_sha256",
                "result",
                "match_rate",
                "complete",
                "compared_fields",
                "policy",
                "document_label",
                "filename",
                "document_id",
                "extraction_id",
                "field",
                "label",
                "original_value",
                "dataset_value",
                "effective_value",
                "status",
                "message",
                "edited",
                "edit_reason",
                "edit_actor",
                "source",
                "similarity",
                "method",
            ]
            writer.writerow(columns)
            for row in result["rows"]:
                record = {
                    **result,
                    **result["summary"],
                    **row,
                    "edit_reason": (row.get("edit") or {}).get("reason"),
                    "edit_actor": (row.get("edit") or {}).get("actor"),
                }
                writer.writerow([csv_safe(record.get(k)) for k in columns])
            body = "\ufeff" + stream.getvalue()
            mime = "text/csv; charset=utf-8"
        return Response(
            body,
            media_type=mime,
            headers={
                "Content-Disposition": f'attachment; filename="comparison-{case.id}-r{result["revision"]}.{format}"'
            },
        )


@app.get("/api/comparisons/export")
def export_all_comparisons(user=Depends(current_user)):
    from .comparison_excel import MIME, export_workbook

    with SessionLocal.begin() as db:
        cases = db.scalars(
            scoped(
                select(Case)
                .join(DatasetComparison, DatasetComparison.case_id == Case.id)
                .where(Case.status != "MERGED")
                .order_by(Case.created_at),
                Case,
                user,
            )
        ).all()
        results = []
        for case in cases:
            state = db.scalar(
                select(DatasetComparison).where(DatasetComparison.case_id == case.id)
            ).payload
            result = comparison_view(db, case, state)
            if result.get("sample_id"):
                results.append(result)
        if not results:
            raise HTTPException(
                404, "No saved comparisons are available in your accessible cases."
            )
        body = export_workbook(results)
        audit(
            db,
            user.org,
            user.id,
            "dataset.all_comparisons_exported",
            comparisons=[
                {
                    "case_id": r["case_id"],
                    "revision": r["revision"],
                    "fingerprint": r["fingerprint"],
                }
                for r in results
            ],
        )
        return Response(
            body,
            media_type=MIME,
            headers={
                "Content-Disposition": 'attachment; filename="all-dataset-comparisons.xlsx"'
            },
        )


class ContextInput(BaseModel):
    values: dict
    reason: str = Field(min_length=5, max_length=1000)
    evidence: str = Field(min_length=5, max_length=1000)


@app.put("/api/cases/{case_id}/context")
def edit_case_context(case_id: str, data: ContextInput, user=Depends(WRITE)):
    from .configuration.contexts import validate_values
    with SessionLocal.begin() as db:
        case = authorized(db, Case, case_id, user)
        config = get_revision(db, case.config_id)
        family = config.payload["templates"][case.template].get("document_family", "forex")
        try:
            validate_values(config.payload, data.values, family=family,
                            document_lookup=lambda identifier: db.get(Document, identifier), case_id=case.id)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        item = db.scalar(
            select(CaseContext).where(CaseContext.case_id == case.id).with_for_update()
        )
        if not item:
            item = CaseContext(
                org=case.org, branch_id=case.branch_id, case_id=case.id, payload={}
            )
            db.add(item)
        previous = item.payload
        item.payload = {
            **previous,
            **data.values,
            "annotation": {
                "actor": user.id,
                "reason": data.reason,
                "evidence": data.evidence,
                "at": time.time(),
            },
            "rule_reviews": {},
        }
        audit(
            db,
            case.org,
            user.id,
            "case.context_corrected",
            case.branch_id,
            case.id,
            before=previous,
            after=item.payload,
        )
        refresh_case(db, case.id)
        return {"queued": True}


@app.post("/api/cases/{case_id}/sop-rerun", status_code=202)
def rerun_sop(case_id: str, user=Depends(WRITE)):
    from .case_processing import queue_case

    with SessionLocal.begin() as db:
        case = authorized(db, Case, case_id, user)
        for run in db.scalars(
            select(CaseRun).where(CaseRun.case_id == case.id, CaseRun.status == "ERROR")
        ):
            run.status = "QUEUED"
            run.error = ""
            run.lease_until = 0
        queue_case(db, case.id)
        audit(db, case.org, user.id, "sop.rerun_requested", case.branch_id, case.id)
        return {
            "queued": True,
            "note": "Uses stored extraction and pinned rules. No cloud jobs.",
        }


class FindingReview(BaseModel):
    report_id: str | None = None
    rule_id: str
    result: str
    reason: str = Field(min_length=10, max_length=1000)
    observations: list[dict] = Field(min_length=1, max_length=20)


@app.post("/api/cases/{case_id}/sop-review", status_code=202)
def review_sop(case_id: str, data: FindingReview, user=Depends(REVIEW)):
    if data.result not in {"PASS", "FAIL"}:
        raise HTTPException(422, "Review result must be PASS or FAIL.")
    with SessionLocal.begin() as db:
        case = authorized(db, Case, case_id, user)
        report = db.scalar(
            select(Report)
            .where(Report.case_id == case.id)
            .order_by(Report.version.desc())
            .limit(1)
        )
        finding = (
            next(
                (
                    f
                    for f in report.snapshot["findings"]
                    if f["rule_id"] == data.rule_id
                ),
                None,
            )
            if report
            else None
        )
        if data.report_id and (not report or report.id != data.report_id):
            raise HTTPException(409, "The SOP report changed. Reload the check and inspect the latest evidence before saving.")

        from .case_processing import fingerprint, inputs

        if (
            report
            and "configuration" in report.snapshot
            and fingerprint(inputs(db, case)) != report.fingerprint
        ):
            raise HTTPException(
                409,
                "Case inputs changed. Wait for the latest SOP report before review.",
            )
        if not finding or finding["result"] != "REVIEW" or finding.get("evaluation_type") != "VISUAL" or not finding.get("eligible"):
            raise HTTPException(
                409, "Only unresolved eligible findings can be reviewed."
            )
        docs = {
            d.id: d
            for d in db.scalars(select(Document).where(Document.case_id == case.id))
        }
        for o in data.observations:
            if (
                o.get("document_id") not in docs
                or type(o.get("page")) is not int
                or o["page"] < 1
                or not isinstance(o.get("region"), str)
                or len(o["region"]) < 3
            ):
                raise HTTPException(
                    422,
                    "Each observation needs a case document, 1-based page and visible region description.",
                )
        cfg = get_revision(db, case.config_id)
        rule = next(
            (r for r in cfg.payload.get("sop_rules", []) if r["id"] == data.rule_id),
            None,
        )
        related = set(
            finding.get("evidence", {}).get("document_ids", [])
            + finding.get("evidence", {}).get("reference_document_ids", [])
        )
        if related and any(o["document_id"] not in related for o in data.observations):
            raise HTTPException(
                422, "Evidence must reference the documents used by this finding."
            )
        if (
            rule
            and (
                rule["operator"] == "signature_visual_consistency"
                or rule["operator"] == "account_check"
                and json.loads(rule["comparison_policy"]).get("require_two_signatures")
            )
            and data.result == "PASS"
        ):
            if (
                not related
                or {o["document_id"] for o in data.observations} != related
                or len(related) < 2
            ):
                raise HTTPException(
                    422,
                    "Signature consistency needs reviewed observations from both document signing regions.",
                )
        if cfg.payload["maker_checker"] and case.created_by == user.id:
            raise HTTPException(
                403, "A different reviewer must record this finding review."
            )
        item = db.scalar(
            select(CaseContext).where(CaseContext.case_id == case.id).with_for_update()
        )
        if not item:
            item = CaseContext(
                org=case.org, branch_id=case.branch_id, case_id=case.id, payload={}
            )
            db.add(item)
        item.payload = {
            **item.payload,
            "rule_reviews": {
                **item.payload.get("rule_reviews", {}),
                data.rule_id: {
                    "result": data.result,
                    "reason": data.reason,
                    "observations": data.observations,
                    "document_basis": fingerprint(
                        {
                            "documents": report.snapshot["documents"],
                            "config_id": report.snapshot["config_id"],
                        }
                    ),
                    "actor": user.id,
                    "at": time.time(),
                },
            },
        }
        audit(
            db,
            case.org,
            user.id,
            "sop.finding_reviewed",
            case.branch_id,
            case.id,
            **data.model_dump(),
        )
        refresh_case(db, case.id)
        return {"queued": True}


@app.get("/api/documents/{doc_id}/file")
def document_file(doc_id: str, user=Depends(current_user)):
    with SessionLocal() as db:
        d = authorized(db, Document, doc_id, user)
    data = store().read(original_key(d))
    return Response(
        data,
        media_type=sniff_mime(data),
        headers={"Content-Disposition": "inline", "Cache-Control": "no-store"},
    )


@app.get("/api/location-learning")
def location_learning_history(document_type: str = "", user=Depends(current_user)):
    from .db import LocationFeedback

    with SessionLocal() as db:
        query = select(LocationFeedback).where(LocationFeedback.org == user.org)
        if user.role != "bank_admin":
            query = query.where(LocationFeedback.branch_id.in_(user.branches))
        if document_type:
            query = query.where(LocationFeedback.document_type == document_type)
        return [
            {
                "id": s.id,
                "document_type": s.document_type,
                "field": s.field,
                "page_number": s.page_number,
                "bbox": s.bbox,
                "enabled": s.enabled,
                "layout_available": bool(s.layout),
                "created_at": s.created_at,
                "reviewer_id": s.reviewer_id,
                "reason": s.reason,
            }
            for s in db.scalars(
                query.order_by(LocationFeedback.created_at.desc()).limit(200)
            )
        ]


@app.post("/api/location-learning/{sample_id}/disable")
def disable_location_learning(sample_id: str, user=Depends(REVIEW)):
    from .db import LocationFeedback

    with SessionLocal.begin() as db:
        item = authorized(db, LocationFeedback, sample_id, user)
        item.enabled = False
        audit(
            db,
            user.org,
            user.id,
            "location_feedback.disabled",
            item.branch_id,
            document_id=item.document_id,
            sample_id=item.id,
        )
    return {"disabled": True}


class VisualBoxReview(BaseModel):
    field: str = Field(min_length=1, max_length=200)
    page_number: int = Field(ge=1)
    bbox: list[float] = Field(min_length=4, max_length=4)
    learn_for_future: bool = True
    reason: str = Field(min_length=5, max_length=1000)


@app.post("/api/documents/{doc_id}/visual-box", status_code=202)
def review_visual_box(doc_id: str, data: VisualBoxReview, user=Depends(REVIEW)):
    from .evidence import build_evidence, apply_evidence_review, visual_fields
    from .provider import validate_extraction
    from .field_evidence import (
        build_field_evidence,
        populated_fields,
        attach_field_evidence,
    )

    with SessionLocal.begin() as db:
        d = authorized(db, Document, doc_id, user)
        if d.status != "COMPLETED":
            raise HTTPException(409, "Wait for document processing to complete.")
        visual_names = {key for key, _ in visual_fields(d.raw)}
        visual_roots = {key.split(".")[0] for key in visual_names}
        ordinary_names = {
            key
            for key, _ in populated_fields(d.raw, include_empty=True)
            if key.split(".")[0] not in visual_roots
        }
        if data.field not in visual_names | ordinary_names:
            raise HTTPException(422, "Unknown extracted field.")
        cfg = get_revision(db, db.get(Case, d.case_id).config_id).payload
        metadata = {
            **d.metadata_json,
            "visual_evidence": {
                **d.metadata_json.get("visual_evidence", {}),
                data.field: {
                    "page_number": data.page_number,
                    "bbox": data.bbox,
                    "units": "normalized",
                    "reviewed_by": user.id,
                    "reason": data.reason,
                },
            },
        }
        response = {
            "extract_result": d.raw,
            "extract_metadata": metadata,
            "id": d.provider_state.get("extract_job_id"),
        }
        evidence = build_evidence(d, response)
        field_evidence = build_field_evidence(d, response)
        item = next(e for e in evidence + field_evidence if e["field"] == data.field)
        if not item["available"]:
            raise HTTPException(422, item.get("error", "Invalid visual region."))
        item["review_status"] = "REVIEWED"
        item["reviewed_by"] = user.id
        item["review_reason"] = data.reason
        report = validate_extraction(d, cfg, response)
        if cfg.get("provider") == "spider-ai":
            report["visual_evidence"] = evidence
        else:
            apply_evidence_review(report, evidence)
        attach_field_evidence(report, field_evidence)
        from .location_learning import record_feedback

        profile = cfg["profiles"][d.doc_type]
        sample = record_feedback(
            db,
            d,
            {
                **profile,
                "schema": profile.get("schema") or profile_schema(cfg, d.doc_type),
            },
            data,
            user,
        )
        metadata["location_feedback_revision"] = sample.id
        d.metadata_json = metadata
        d.validation = report
        d.validation_status = report["status"]
        audit(
            db,
            d.org,
            user.id,
            "document.visual_box_reviewed",
            d.branch_id,
            d.case_id,
            document_id=d.id,
            field=data.field,
            location_feedback_id=sample.id,
            future_guidance_enabled=sample.enabled,
            page=data.page_number,
            reason=data.reason,
        )
        refresh_case(db, d.case_id)
    return {
        "queued": True,
        "location_feedback_id": sample.id,
        "future_guidance_enabled": sample.enabled,
    }


@app.post("/api/documents/{doc_id}/field-evidence", status_code=202)
def refresh_field_evidence(doc_id: str, user=Depends(WRITE)):
    from .field_evidence import build_field_evidence, attach_field_evidence

    with SessionLocal.begin() as db:
        d = authorized(db, Document, doc_id, user)
        if d.status != "COMPLETED":
            raise HTTPException(409, "Wait for document processing to complete.")
        response = {
            "extract_result": d.raw,
            "extract_metadata": d.metadata_json,
            "id": d.provider_state.get("extract_job_id"),
        }
        from .evidence import build_evidence
        evidence = build_field_evidence(d, response)
        report = copy.deepcopy(d.validation)
        if d.metadata_json.get("spatial_evidence"):
            previous = {item["field"]:item for item in report.get("visual_evidence",[])}
            visual = build_evidence(d, response)
            for item in visual:
                old = previous.get(item["field"],{})
                if item.get("available") and item.get("revision") == old.get("revision") and item.get("image_sha256") == old.get("image_sha256"):
                    item["review_status"] = old.get("review_status",item["review_status"])
            report["visual_evidence"] = visual
        d.validation = attach_field_evidence(report, evidence)
        audit(
            db,
            d.org,
            user.id,
            "document.field_evidence_refreshed",
            d.branch_id,
            d.case_id,
            document_id=d.id,
            fields=len(evidence),
            available=sum(e["available"] for e in evidence),
        )
        refresh_case(db, d.case_id)
    return {"queued": True}


@app.get("/api/documents/{doc_id}/pages/{page_number}")
def document_page(doc_id: str, page_number: int, user=Depends(current_user)):
    import fitz

    with SessionLocal() as db:
        d = authorized(db, Document, doc_id, user)
    with fitz_open_original(store().read(original_key(d))) as pdf:
        if page_number < 1 or page_number > len(pdf):
            raise HTTPException(404, "Page not found.")
        page = pdf[page_number - 1]
        scale = min(4, 3200 / max(page.rect.width, page.rect.height))
        image = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).tobytes(
            "png"
        )
    return Response(
        image, media_type="image/png", headers={"Cache-Control": "no-store"}
    )


@app.get("/api/documents/{doc_id}/evidence/{revision}/{image_id}")
def document_evidence(
    doc_id: str, revision: str, image_id: str, user=Depends(current_user)
):
    with SessionLocal() as db:
        d = authorized(db, Document, doc_id, user)
        from .field_evidence import evidence_images

        items = evidence_images(d.validation)
        item = next(
            (
                e
                for e in items
                if e.get("available")
                and e.get("revision") == revision
                and e.get("storage_key", "").endswith(
                    "/" + revision + "-" + image_id + ".png"
                )
            ),
            None,
        )
        if not item:
            raise HTTPException(
                404, "Evidence not available for this extraction revision."
            )
    return Response(
        store().read(item["storage_key"]),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


class ReprocessFieldsInput(BaseModel):
    fields: list[str] = Field(min_length=1, max_length=100)
    instruction: str = Field(default='', max_length=10000)
    reason: str = Field(min_length=3, max_length=2000)
    use_latest_config: bool = True
    replace_overrides: bool = False
    save_to_profile: bool = True


@app.post('/api/documents/{doc_id}/reprocess-fields', status_code=202)
def reprocess_document_fields(doc_id: str, data: ReprocessFieldsInput, user=Depends(WRITE)):
    from .db import FieldReprocess
    with SessionLocal.begin() as db:
        d = authorized(db, Document, doc_id, user)
        d = db.scalar(select(Document).where(Document.id==d.id).with_for_update())
        if d.status != 'COMPLETED' or not d.raw:
            raise HTTPException(409, 'Wait for extraction to complete before reprocessing fields.')
        if d.provider_state.get('pending_create'):
            raise HTTPException(409, 'Reconcile the pending provider submission first.')
        if db.scalar(select(Job).where(Job.document_id==d.id,Job.status.in_(['QUEUED','DISPATCHED','RUNNING']))):
            raise HTTPException(409, 'A document job is already active.')
        case=db.get(Case,d.case_id)
        pinned=get_revision(db, case.config_id)
        instruction=data.instruction.strip()
        save_guidance=bool(instruction and data.save_to_profile)
        if save_guidance and user.role != 'bank_admin':
            raise HTTPException(403, 'Only a bank administrator can save shared document-profile instructions. Use request-only guidance or ask an administrator.')
        if save_guidance and not data.use_latest_config:
            raise HTTPException(422, 'Use the latest published profile when saving reusable guidance.')
        from .profile_guidance import locked_latest_config, append_profile_guidance
        config=(locked_latest_config(db,user.org) if save_guidance else latest_config(db,user.org)) if data.use_latest_config else pinned
        payload=copy.deepcopy(config.payload)
        # Use the new profile, but retain the document's original provider/connector family.
        payload['provider']=pinned.payload['provider']
        try:
            validate_config(payload)
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(422, 'Published profile is incompatible with this document provider: '+str(exc))
        profile=payload['profiles'].get(d.doc_type,{})
        fields=list(dict.fromkeys(data.fields))
        if set(fields)-set(profile.get('schema',profile_schema(payload, d.doc_type))['properties']):
            raise HTTPException(422, 'Select existing fields from this document profile.')
        if set(fields)&set(d.overrides) and not data.replace_overrides:
            raise HTTPException(409, 'Selected fields have reviewer overrides; resolve those corrections before reprocessing.')
        if set(fields)&set(d.overrides) and data.replace_overrides and user.role not in {'bank_admin','branch_admin','reviewer'}:
            raise HTTPException(403,'A reviewer must authorize replacing reviewer corrections.')
        guidance_appended=False
        if save_guidance:
            try:
                config,guidance_appended=append_profile_guidance(db,config,d,fields,instruction,user)
            except (ValueError, TypeError, KeyError) as exc:
                raise HTTPException(422, 'Cannot save profile guidance: '+str(exc))
            payload=copy.deepcopy(config.payload)
            payload['provider']=pinned.payload['provider']
            validate_config(payload)
            profile=payload['profiles'][d.doc_type]
        profile.setdefault('schema',copy.deepcopy(profile_schema(payload, d.doc_type)))
        job=enqueue(db,d,action='reprocess_fields');db.flush()
        req=FieldReprocess(org=d.org,branch_id=d.branch_id,document_id=d.id,job_id=job.id,requested_by=user.id,
            payload={'fields':fields,'instruction':instruction,'reason':data.reason,
                     'guidance_saved_to_profile':save_guidance,'guidance_appended':guidance_appended,
                     'config':payload,'config_version':config.version,'replace_overrides':data.replace_overrides,
                     'input_values':{k:copy.deepcopy(d.raw[k]) for k in fields if k in d.raw},
                     'input_overrides':{k:copy.deepcopy(d.overrides[k]) for k in fields if k in d.overrides}})
        db.add(req);db.flush()
        audit(db,d.org,user.id,'document.fields_reprocess_requested',d.branch_id,d.case_id,
              document_id=d.id,request_id=req.id,fields=fields,reason=data.reason,config_version=config.version)
        return {'job_id':job.id,'request_id':req.id,'fields':fields,'config_version':config.version,
                'guidance_saved_to_profile':save_guidance,'guidance_appended':guidance_appended}


@app.get('/api/documents/{doc_id}/reprocess-fields')
def field_reprocess_history(doc_id: str, user=Depends(current_user)):
    from .db import FieldReprocess
    with SessionLocal() as db:
        d=authorized(db,Document,doc_id,user)
        requests=db.scalars(select(FieldReprocess).where(FieldReprocess.document_id==d.id).order_by(FieldReprocess.created_at.desc())).all()
        from .spider_failures import confirmed_connection_rejection
        rejection=confirmed_connection_rejection(d.provider_state)
        pending=str(d.provider_state.get('pending_create') or '')
        return [{'id':r.id,'fields':r.payload['fields'],'config_version':r.payload['config_version'],
                 'instruction':r.payload.get('instruction',''),
                 'guidance_saved_to_profile':r.payload.get('guidance_saved_to_profile',False),
                 'reason':r.payload['reason'],'status':db.get(Job,r.job_id).status,'error':db.get(Job,r.job_id).error,'result':r.result,
                 'requires_duplicate_charge_ack':bool(pending and (pending.startswith('spider_fields_'+r.id+'_') or pending=='field_extract_'+r.id) and not rejection),
                 'can_retry':db.get(Job,r.job_id).status=='ERROR' and d.status=='COMPLETED' and (not pending or pending.startswith('spider_fields_'+r.id+'_') or pending=='field_extract_'+r.id),
                 'retry_explanation':rejection['message'] if rejection else ''} for r in requests]


class RetryFieldsInput(BaseModel):
    accept_possible_duplicate_charge: bool = False


@app.post('/api/documents/{doc_id}/reprocess-fields/{request_id}/retry',status_code=202)
def retry_field_request(doc_id: str, request_id: str, data: RetryFieldsInput = RetryFieldsInput(), user=Depends(WRITE)):
    from .db import FieldReprocess
    with SessionLocal.begin() as db:
        d=authorized(db,Document,doc_id,user)
        d=db.scalar(select(Document).where(Document.id==d.id).with_for_update())
        req=db.get(FieldReprocess,request_id)
        if not req or req.document_id!=d.id:raise HTTPException(404,'Field request not found.')
        job=db.get(Job,req.job_id)
        if job.status!='ERROR' or d.status!='COMPLETED':raise HTTPException(409,'Only failed field requests can be resumed.')
        pending=d.provider_state.get('pending_create')
        if pending:
            if not (str(pending).startswith('spider_fields_'+request_id+'_') or pending=='field_extract_'+request_id):
                raise HTTPException(409,'A different provider request must be reconciled first.')
            from .spider_failures import confirmed_connection_rejection
            rejection=confirmed_connection_rejection(d.provider_state)
            if not rejection and not data.accept_possible_duplicate_charge:
                raise HTTPException(409,'The last provider submission may have been processed. Acknowledge possible duplicate provider charges to resubmit this field request.')
            audit(db,d.org,user.id,'document.fields_resubmission_authorized',d.branch_id,d.case_id,request_id=req.id,pending_stage=pending,possible_duplicate_charge=not bool(rejection),confirmed_connection_rejection=bool(rejection))
            d.provider_state={**d.provider_state,'pending_create':None}
        if db.scalar(select(Job).where(Job.document_id==d.id,Job.status.in_(['QUEUED','DISPATCHED','RUNNING']))):raise HTTPException(409,'A document job is already active.')
        job=enqueue(db,d,action='reprocess_fields');db.flush()
        req.job_id=job.id
        refresh_case(db,d.case_id)
        audit(db,d.org,user.id,'document.fields_reprocess_resumed',d.branch_id,d.case_id,request_id=req.id)
        return {'job_id':job.id,'request_id':req.id}


@app.post("/api/documents/{doc_id}/retry", status_code=202)
def retry_document(doc_id: str, user=Depends(WRITE)):
    with SessionLocal.begin() as db:
        d = authorized(db, Document, doc_id, user)
        if d.status not in {"ERROR", "NEEDS_CLASSIFICATION"}:
            raise HTTPException(409, "Document is not waiting for retry.")
        if d.provider_state.get("pending_create"):
            if str(d.provider_state['pending_create']).startswith('spider_fields_'):
                raise HTTPException(409,'Resume the failed field request instead of retrying the whole document.')
            from .spider_failures import confirmed_connection_rejection
            rejection=confirmed_connection_rejection(d.provider_state)
            if not rejection:raise HTTPException(409, "Reconcile the uncertain provider submission before retrying.")
            audit(db,d.org,user.id,'spider.connection_rejection_reconciled',d.branch_id,d.case_id,document_id=d.id,pending_stage=d.provider_state['pending_create'])
            d.provider_state={**d.provider_state,'pending_create':None}
        if d.status == "NEEDS_CLASSIFICATION":
            raise HTTPException(409, "Confirm document type before retrying.")
        job = enqueue(db, d)
        audit(
            db,
            user.org,
            user.id,
            "document.retry_requested",
            d.branch_id,
            d.case_id,
            document_id=d.id,
        )
        db.flush()
        return {"job_id": job.id}


@app.post("/api/cases/{case_id}/retry-documents", status_code=202)
def retry_case_documents(case_id: str, user=Depends(WRITE)):
    # Bulk per-document retry: re-queue every document in the case that can be
    # safely re-processed, regardless of its current status (ERROR, COMPLETED,
    # QUEUED, etc.). Documents with an uncertain provider submission
    # (pending_create) are skipped and must be reconciled individually first,
    # since re-submitting them could create a duplicate paid job at the provider.
    # enqueue() deduplicates against in-flight jobs, so re-queueing a document
    # that is already QUEUED/DISPATCHED/RUNNING returns the existing job.
    with SessionLocal.begin() as db:
        case = authorized(db, Case, case_id, user)
        queued = []
        skipped = []
        for d in db.scalars(select(Document).where(Document.case_id == case.id)):
            if d.provider_state.get("pending_create"):
                skipped.append(
                    {
                        "id": d.id,
                        "filename": d.filename,
                        "reason": "uncertain provider submission — reconcile first",
                    }
                )
                continue
            job = enqueue(db, d)
            queued.append({"id": d.id, "filename": d.filename, "job_id": job.id})
        audit(
            db,
            case.org,
            user.id,
            "case.documents_retry_requested",
            case.branch_id,
            case.id,
        )
        db.flush()
        return {"queued": queued, "skipped": skipped}


class ClassificationInput(BaseModel):
    doc_type: str
    reason: str = Field(min_length=5, max_length=1000)


@app.post("/api/documents/{doc_id}/classification", status_code=202)
def confirm_type(doc_id: str, data: ClassificationInput, user=Depends(REVIEW)):
    with SessionLocal.begin() as db:
        d = authorized(db, Document, doc_id, user)
        if d.status not in {"NEEDS_CLASSIFICATION", "ERROR"} or d.raw:
            raise HTTPException(409, "Type can only be assigned before extraction.")
        cfg = get_revision(db, db.get(Case, d.case_id).config_id).payload
        if data.doc_type not in cfg["profiles"]:
            raise HTTPException(422, "Unknown profile.")
        before = d.doc_type
        d.doc_type = data.doc_type
        d.classification = {
            **d.classification,
            "manual": True,
            "type": data.doc_type,
            "confirmed": True,
            "reviewer": user.id,
            "reason": data.reason,
        }
        if before != d.doc_type:
            # An already-created specialized parse belongs to its old profile.
            d.provider_state = {
                k: v
                for k, v in d.provider_state.items()
                if k
                not in {"parse_job_id", "extract_job_id", "spider_extract_response_key"}
                and not re.fullmatch(r"spider_extract_page_\d+_response_key", k)
            }
        enqueue(db, d)
        audit(
            db,
            user.org,
            user.id,
            "document.classification_confirmed",
            d.branch_id,
            d.case_id,
            document_id=d.id,
            reason=data.reason,
            type=data.doc_type,
        )
        return {"ok": True}


class CorrectionInput(BaseModel):
    field: str
    value: object
    reason: str = Field(min_length=5, max_length=1000)


@app.post("/api/documents/{doc_id}/corrections", status_code=202)
def correct_field(doc_id: str, data: CorrectionInput, user=Depends(REVIEW)):
    from validation import check_schema

    with SessionLocal.begin() as db:
        d = authorized(db, Document, doc_id, user)
        if d.status != "COMPLETED":
            raise HTTPException(409, "Wait for document completion.")
        if data.field not in d.raw:
            raise HTTPException(422, "Unknown field.")
        effective = copy.deepcopy(d.raw)
        effective.update(d.overrides)
        effective[data.field] = data.value
        cfg = get_revision(db, db.get(Case, d.case_id).config_id).payload
        try:
            if cfg.get("provider") != "spider-ai":
                if cfg["profiles"][d.doc_type].get("validation_adapter") == "schema":
                    validate_shape(effective, profile_schema(cfg, d.doc_type))
                else:
                    check_schema(effective, profile_schema(cfg, d.doc_type))
        except ValueError:
            raise HTTPException(
                422, "Value does not match this field's extraction schema."
            )
        previous = d.overrides.get(data.field, d.raw[data.field])
        d.overrides = {**d.overrides, data.field: data.value}
        enqueue(db, d, "revalidate")
        audit(
            db,
            user.org,
            user.id,
            "document.field_corrected",
            d.branch_id,
            d.case_id,
            document_id=d.id,
            field=data.field,
            before=previous,
            after=data.value,
            reason=data.reason,
        )
        return {"ok": True}


class EffectiveCorrectionInput(CorrectionInput):
    expected_value: object


@app.post("/api/documents/{doc_id}/effective-corrections", status_code=202)
def correct_effective_field(
    doc_id: str, data: EffectiveCorrectionInput, user=Depends(REVIEW)
):
    from .effective_corrections import extraction_value
    from .provider import validate_extraction
    from validation import check_schema

    with SessionLocal.begin() as db:
        d = authorized(db, Document, doc_id, user)
        db.scalar(select(Document).where(Document.id == d.id).with_for_update())
        if d.status != "COMPLETED":
            raise HTTPException(409, "Wait for document completion or revalidation.")
        if data.field not in d.raw or data.field not in d.normalized:
            raise HTTPException(422, "Unknown effective field.")
        before = d.normalized[data.field]
        if before != data.expected_value:
            raise HTTPException(
                409, "The effective value changed. Refresh before correcting it."
            )
        cfg = get_revision(db, db.get(Case, d.case_id).config_id).payload
        try:
            replacement = (
                data.value
                if cfg.get("provider") == "spider-ai"
                else extraction_value(
                    data.field,
                    data.value,
                    d.overrides.get(data.field, d.raw[data.field]),
                    cfg["profiles"][d.doc_type]["policy"],
                )
            )
            effective = {**copy.deepcopy(d.raw), **d.overrides, data.field: replacement}
            if cfg.get("provider") != "spider-ai":
                if cfg["profiles"][d.doc_type].get("validation_adapter") == "schema":
                    validate_shape(effective, profile_schema(cfg, d.doc_type))
                else:
                    check_schema(effective, profile_schema(cfg, d.doc_type))
            from types import SimpleNamespace

            candidate = SimpleNamespace(
                doc_type=d.doc_type,
                overrides={**d.overrides, data.field: replacement},
                provider_state=d.provider_state,
            )
            preview = validate_extraction(
                candidate,
                cfg,
                {
                    "extract_result": d.raw,
                    "extract_metadata": d.metadata_json,
                    "id": d.provider_state.get("extract_job_id"),
                },
            )
            after = preview["normalized"].get(data.field)
            if after == before:
                raise ValueError(
                    "This edit does not change the effective value. Computed fields must be corrected through their source inputs."
                )
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(422, str(exc)) from exc
        d.overrides = candidate.overrides
        enqueue(db, d, "revalidate")
        audit(
            db,
            d.org,
            user.id,
            "document.effective_value_corrected",
            d.branch_id,
            d.case_id,
            document_id=d.id,
            field=data.field,
            before=before,
            requested=data.value,
            validated_preview=after,
            reason=data.reason,
        )
        return {"queued": True, "normalized_preview": after}


class MoveInput(BaseModel):
    case_id: str
    reason: str = Field(min_length=5, max_length=1000)


@app.post("/api/documents/{doc_id}/move")
def move_document(doc_id: str, data: MoveInput, user=Depends(REVIEW)):
    with SessionLocal.begin() as db:
        d = authorized(db, Document, doc_id, user)
        target = authorized(db, Case, data.case_id, user)
        if d.status not in {"COMPLETED", "ERROR", "NEEDS_CLASSIFICATION"}:
            raise HTTPException(409, "Wait until processing stops before moving.")
        if d.branch_id != target.branch_id:
            raise HTTPException(422, "Move documents only within the same branch.")
        if db.get(Case, d.case_id).config_id != target.config_id:
            raise HTTPException(
                422, "Case configurations differ; reprocessing migration is required."
            )
        old = d.case_id
        d.case_id = target.id
        db.flush()
        refresh_case(db, old)
        refresh_case(db, target.id)
        audit(
            db,
            user.org,
            user.id,
            "document.moved",
            d.branch_id,
            target.id,
            document_id=d.id,
            from_case=old,
            reason=data.reason,
        )
        return {"ok": True}


class ReconcileInput(BaseModel):
    stage: str
    provider_id: str = Field(min_length=5, max_length=100)
    reason: str = Field(min_length=5, max_length=1000)


@app.post("/api/documents/{doc_id}/reconcile", status_code=202)
def reconcile(doc_id: str, data: ReconcileInput, user=Depends(ADMIN)):
    with SessionLocal.begin() as db:
        d = authorized(db, Document, doc_id, user)
        if d.status != "ERROR" or d.provider_state.get("pending_create") != data.stage:
            raise HTTPException(
                409,
                "This document does not have an uncertain submission for that stage.",
            )
        d.provider_state = {
            **d.provider_state,
            data.stage: data.provider_id,
            "pending_create": None,
        }
        enqueue(db, d)
        audit(
            db,
            user.org,
            user.id,
            "provider.submission_reconciled",
            d.branch_id,
            d.case_id,
            document_id=d.id,
            stage=data.stage,
            provider_id=data.provider_id,
            reason=data.reason,
        )
        return {"ok": True}


class TaskAssignment(BaseModel):
    assigned_to: str | None = None
    due_at: float | None = Field(default=None, ge=0)


@app.get("/api/cases/{case_id}/assignment")
def case_assignment(case_id: str, user=Depends(current_user)):
    with SessionLocal() as db:
        c = authorized(db, Case, case_id, user)
        task = db.scalar(
            select(CaseTask).where(CaseTask.case_id == c.id, CaseTask.org == user.org)
        )
        candidates = [
            u
            for u in db.scalars(
                select(User).where(User.org == user.org, User.active.is_(True))
            )
            if u.role == "bank_admin" or c.branch_id in u.branches
        ]
        return {
            "assigned_to": task.assigned_to if task else None,
            "due_at": task.due_at if task else None,
            "candidates": [{"id": u.id, "name": u.name} for u in candidates],
            "can_edit": user.role in {"bank_admin", "branch_admin", "reviewer"},
        }


@app.put("/api/cases/{case_id}/assignment")
def assign_case(case_id: str, data: TaskAssignment, user=Depends(REVIEW)):
    with SessionLocal.begin() as db:
        c = authorized(db, Case, case_id, user)
        if data.assigned_to:
            target = db.get(User, data.assigned_to)
            if (
                not target
                or not target.active
                or target.org != user.org
                or (target.role != "bank_admin" and c.branch_id not in target.branches)
            ):
                raise HTTPException(422, "Assignee must have access to this branch.")
        task = db.scalar(
            select(CaseTask).where(CaseTask.case_id == c.id, CaseTask.org == user.org)
        )
        if not task:
            task = CaseTask(
                org=user.org, branch_id=c.branch_id, case_id=c.id, assigned_by=user.id
            )
            db.add(task)
        task.assigned_to, task.due_at, task.assigned_by = (
            data.assigned_to,
            data.due_at,
            user.id,
        )
        audit(
            db,
            user.org,
            user.id,
            "case.assignment_updated",
            c.branch_id,
            c.id,
            assigned_to=data.assigned_to,
            due_at=data.due_at,
        )
    return {"saved": True}


@app.get("/api/inbox")
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


@app.post("/api/inbox/{item_id}/read")
def read_inbox(item_id: str, user=Depends(current_user)):
    with SessionLocal.begin() as db:
        item = authorized(db, Inbox, item_id, user)
        item.read_by = list(set(item.read_by + [user.id]))
        return {"ok": True}


@app.get("/api/events")
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


@app.get("/api/reports")
def reports(user=Depends(current_user)):
    from .report_queries import ReportAudience, ReportQueries
    audience = ReportAudience(user.org, None if user.role == "bank_admin" else tuple(user.branches))
    with SessionLocal() as db:
        return ReportQueries(db, audience).current()


@app.get("/api/reports/kertas-kerja")
def export_branch_report(branch_id: str, transaction_flow: str | None = None, date_from: str | None = None, date_to: str | None = None, user=Depends(current_user)):
    from .config_workbook import MIME
    from .kertas_kerja import workbook

    from .branch_report import select_branch_reports, export_period
    from datetime import date
    try:
        start_date = date.fromisoformat(date_from) if date_from else None
        end_date = date.fromisoformat(date_to) if date_to else None
        if start_date and end_date and start_date > end_date:
            raise ValueError()
    except ValueError:
        raise HTTPException(422,"Use valid YYYY-MM-DD transaction dates; the start must not be after the end.")
    with SessionLocal.begin() as db:
        branch_allowed(db, branch_id, user)
        reports = db.scalars(
            select(Report)
            .where(
                Report.org == user.org,
                Report.branch_id == branch_id,
                Report.case_id.in_(select(Case.id).where(Case.status != "MERGED")),
            )
            .order_by(Report.case_id, Report.version.desc())
        ).all()
        latest = select_branch_reports(db, reports, transaction_flow, start_date, end_date)
        if not latest:
            raise HTTPException(404, "No current customer reports match this branch, transaction flow and transaction-date range.")
        period = export_period(start_date,end_date)
        snapshots = [
            {**r.snapshot, "release_state": r.state, "snapshot_hash": r.fingerprint,
             "report_export_context":{"period":period,"transaction_flow":transaction_flow or "All services"}}
            for r in latest.values()
        ]
        data = workbook(snapshots)
        export_id = uid()
        key = object_key(user.org, branch_id, "exports", export_id, "kertas-kerja.xlsx")
        store().put(key, data, MIME)
        manifest = {
            "reports": [
                {"id": r.id, "version": r.version, "snapshot_hash": r.fingerprint}
                for r in latest.values()
            ],
            "exported_by": user.id,
            "at": time.time(),
            "branch_id": branch_id,
            "transaction_flow":transaction_flow,
            "date_from":date_from, "date_to":date_to,
        }
        store().put(
            object_key(user.org, branch_id, "exports", export_id, "manifest.json"),
            json.dumps(manifest).encode(),
            "application/json",
        )
        audit(
            db,
            user.org,
            user.id,
            "report.branch_exported",
            branch_id,
            export_id=export_id,
            source_reports=manifest["reports"],
        )
        return Response(
            data,
            media_type=MIME,
            headers={
                "Content-Disposition": 'attachment; filename="branch-kertas-kerja.xlsx"'
            },
        )


@app.get("/api/reports/{report_id}/download")
def download_report(report_id: str, format: str = "pdf", user=Depends(current_user)):
    if format not in {"pdf", "xlsx", "json"}:
        raise HTTPException(422, "Use pdf, xlsx or json.")
    with SessionLocal.begin() as db:
        r = authorized(db, Report, report_id, user)
        data, mime = make_report(r, format)
        # Also materialize legacy/error-case artifacts after storage recovery.
        store().put(report_key(r, format), data, mime)
        data = store().read(report_key(r, format))
        audit(
            db,
            user.org,
            user.id,
            "report.downloaded",
            r.branch_id,
            r.case_id,
            report_id=r.id,
            format=format,
        )
    return Response(
        data,
        media_type=mime,
        headers={
            "Content-Disposition": report_download_name(r,format)
        },
    )


def report_download_name(report, format):
    customer=re.sub(r'[^\w .-]','_',str(report.snapshot.get('customer') or 'customer')).strip(' .')[:100] or 'customer'
    name=f'kertas-kerja-{customer}-v{report.version}.{format}'
    fallback=re.sub(r'[^a-zA-Z0-9 ._-]','_',name)
    return f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{quote(name,safe="")}'


@app.get('/api/reports/{report_id}')
def report_detail(report_id: str, user=Depends(current_user)):
    with SessionLocal() as db:
        original=authorized(db,Report,report_id,user)
        case=authorized(db,Case,original.case_id,user)
        if case.status=='MERGED':raise HTTPException(404,'This case has been merged.')
        report=db.scalar(scoped(select(Report).where(Report.case_id==case.id),Report,user).order_by(Report.version.desc(),Report.created_at.desc()).limit(1))
        return {'id':report.id,'case_id':case.id,'customer':report.snapshot['customer'],
                'version':report.version,'state':report.state,'created_at':report.created_at,
                'validation_status':report.snapshot['validation_status'],'provider':report.snapshot['provider'],
                'reference':report.snapshot.get('reference',case.reference),
                'snapshot':report.snapshot}


@app.post("/api/reports/{report_id}/approve")
def approve_report(report_id: str, user=Depends(REVIEW)):
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
            or c.status != "READY"
            or r.snapshot["validation_status"] not in {"PASS", "FAIL"}
            or r.snapshot.get("missing")
            or any(
                (not e.get("available") or e.get("link_review_required"))
                for d in r.snapshot.get("documents", [])
                for e in d.get("validation", {}).get("visual_evidence", [])
            )
            or any(f["result"] in {"REVIEW", "ERROR"} for f in r.snapshot["findings"])
        ):
            raise HTTPException(
                409,
                "Only the latest ready report with complete processing and no unresolved review findings can be released. Confirmed violations may be released.",
            )
        cfg = get_revision(db, c.config_id)
        if cfg.payload["maker_checker"] and c.created_by == user.id:
            raise HTTPException(403, "A different reviewer must approve this case.")
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


@app.get("/api/exports/{doc_type}")
def export_csv(doc_type: str, user=Depends(current_user)):
    if doc_type not in LABELS:
        raise HTTPException(404, "Unknown document type.")
    with SessionLocal.begin() as db:
        docs = db.scalars(
            scoped(
                select(Document).where(Document.doc_type == doc_type), Document, user
            ).order_by(Document.created_at)
        ).all()
        columns = list(latest_config(db,user.org).payload['profiles'][doc_type]['columns'])
        known = {k for k,_ in columns}
        for doc in docs:
            for key in doc.normalized:
                if key not in known and not key.startswith('_') and key != 'page_results':
                    columns.append([key,key]);known.add(key)
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(
            [
                "source_file",
                "case_id",
                "branch_id",
                "processing_status",
                "validation_status",
            ]
            + [x[0] for x in columns]
        )
        for d in docs:
            writer.writerow(
                [
                    csv_safe(d.filename),
                    d.case_id,
                    d.branch_id,
                    d.status,
                    d.validation_status,
                ]
                + [csv_safe(d.normalized.get(k)) for k, _ in columns]
            )
        audit(
            db,
            user.org,
            user.id,
            "export.downloaded",
            document_type=doc_type,
            count=len(docs),
        )
        return Response(
            ("\ufeff" + stream.getvalue()).encode(),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{doc_type}_result.csv"'
            },
        )


class EnumRevalidationInput(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)


@app.post("/api/cases/{case_id}/revalidate-enum-aliases", status_code=202)
def revalidate_enum_aliases(
    case_id: str, data: EnumRevalidationInput, user=Depends(REVIEW)
):
    from .enum_aliases import validate_aliases

    with SessionLocal.begin() as db:
        case = authorized(db, Case, case_id, user)
        documents = db.scalars(
            select(Document).where(Document.case_id == case.id)
        ).all()
        if any(
            d.status
            in {
                "QUEUED",
                "PROCESSING",
                "CLASSIFYING",
                "PARSING",
                "EXTRACTING",
                "VALIDATING",
            }
            for d in documents
        ) or db.scalar(
            select(Job).where(
                Job.document_id.in_([d.id for d in documents]),
                Job.status.in_(["QUEUED", "DISPATCHED", "RUNNING"]),
            )
        ):
            raise HTTPException(409, "Wait for case processing to finish.")
        targets = [
            d
            for d in documents
            if d.doc_type == "ektp" and d.status == "COMPLETED" and d.raw
        ]
        if not targets:
            raise HTTPException(422, "No completed eKTP extraction is available.")
        old = get_revision(db, case.config_id)
        latest = latest_config(db, user.org)
        payload = copy.deepcopy(old.payload)
        policy = payload["profiles"]["ektp"]["policy"]
        policy["enum_aliases"] = copy.deepcopy(
            latest.payload["profiles"]["ektp"]["policy"].get("enum_aliases", {})
        )
        policy["enum_raw_fallback_fields"] = copy.deepcopy(
            latest.payload["profiles"]["ektp"]["policy"].get(
                "enum_raw_fallback_fields", ["religion"]
            )
        )
        try:
            validate_aliases(policy)
            targets_in_policy = set(policy['enum_aliases']) | set(policy['enum_raw_fallback_fields'])
            if not targets_in_policy or targets_in_policy - set(payload['profiles']['ektp']['schema']['properties']):
                raise ValueError('Choose an approved enum policy for fields present in this document profile before revalidation.')
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        aliases = copy.deepcopy(policy["enum_aliases"])
        for d in targets:
            d.provider_state = {
                **d.provider_state,
                "normalization_enum_aliases": aliases,
                "normalization_enum_raw_fallback_fields": policy[
                    "enum_raw_fallback_fields"
                ],
                "normalization_source_config_id": latest.id,
            }
            enqueue(db, d, "revalidate")
        audit(
            db,
            user.org,
            user.id,
            "case.enum_aliases_revalidated",
            case.branch_id,
            case.id,
            config_id=old.id,
            source_config_id=latest.id,
            reason=data.reason,
            enum_aliases=aliases,
        )
        return {"queued": len(targets)}
