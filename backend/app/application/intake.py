"""Intake application operations.

Transactions, authorization, audit and pinned configuration remain one unit.
"""

from app.errors import ApplicationError
from app.application.ports import UploadedFile
from app.configuration.repository import get_revision
import hashlib
import json
import logging
from pathlib import Path
from sqlalchemy import select
from app.application.ports import run_in_threadpool
from app.db import Batch, Case, Document, SessionLocal, uid
from app.auditing import audit
from app.case_lifecycle import enqueue
from app.configuration.revisions import latest_config
from app.grouping import plan_grouping
from app.access import authorized, branch_allowed
from app.settings import settings
from app.storage import object_key, store
from app.contracts import PreviewInput, RegroupInput


def preview_upload(*, data: PreviewInput, user):
    with SessionLocal() as db:
        cfg = latest_config(db, user.org).payload
    return plan_grouping(data.filenames, cfg)


async def upload(
    *,
    branch_id: str,
    template: str,
    files: list[UploadedFile],
    grouping: str,
    case_id: str,
    idempotency_key: str,
    user,
):
    if not idempotency_key or len(idempotency_key) > 100:
        raise ApplicationError("invalid_input", "Provide an Idempotency-Key.")
    if not 1 <= len(files) <= settings.max_batch_files:
        raise ApplicationError("invalid_input", "Upload between 1 and 100 documents.")
    try:
        labels = json.loads(grouping)
    except ValueError:
        raise ApplicationError("invalid_input", "Invalid grouping labels.")
    if not isinstance(labels, dict) or any(
        (
            not isinstance(x, str) or not x.strip() or len(x) > 180
            for x in labels.values()
        )
    ):
        raise ApplicationError(
            "invalid_input",
            "Customer labels must be nonempty strings up to 180 characters.",
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
                    raise ApplicationError(
                        "conflict", "Upload key was used in a different branch."
                    )
                docs = db.scalars(
                    select(Document).where(Document.batch_id == previous.id)
                ).all()
                return {
                    "batch_id": previous.id,
                    "case_ids": list(dict.fromkeys((d.case_id for d in docs))),
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
                raise ApplicationError(
                    "invalid_input", "Select an active transaction flow."
                )
            from app.document_families import families

            if not existing and (
                not families(cfg.payload)[
                    cfg.payload["templates"][template].get("document_family", "forex")
                ].get("enabled", True)
            ):
                raise ApplicationError(
                    "invalid_input",
                    "This document family is inactive. Select a flow in an active family.",
                )
            upload_step = next(
                (s for s in cfg.payload.get("workflow", []) if s["action"] == "upload"),
                {},
            )
            limits = upload_step.get("parameters", {})
            if len(files) > limits.get("max_files", settings.max_batch_files):
                raise ApplicationError(
                    "invalid_input", "File count exceeds the configured upload limit."
                )
            if existing and existing.branch_id != branch_id:
                raise ApplicationError(
                    "invalid_input", "Case belongs to another branch."
                )
            filenames = [
                Path((f.filename or "").replace("\\", "/")).name for f in files
            ]
            if len(set(filenames)) != len(filenames):
                raise ApplicationError(
                    "invalid_input", "Filenames must be unique within an upload."
                )
            if any((k not in filenames for k in labels)):
                raise ApplicationError(
                    "invalid_input", "Grouping contains an unknown filename."
                )
            planned = plan_grouping(filenames, cfg.payload, labels)
            if existing:
                for row in planned:
                    row.update(
                        customer=existing.customer,
                        status="manual",
                        explanation="Attached to the case selected by the user.",
                    )
            if not existing and any((p["status"] == "unresolved" for p in planned)):
                raise ApplicationError(
                    "invalid_input",
                    {
                        "message": "Resolve document grouping before upload.",
                        "documents": planned,
                    },
                )
            plan = {p["filename"]: p for p in planned}
        for f in files:
            filename = Path((f.filename or "").replace("\\", "/")).name
            if (
                not filename.lower().endswith((".pdf", ".png", ".jpg", ".jpeg"))
                or len(filename) > 240
            ):
                raise ApplicationError(
                    "invalid_input",
                    "Only PDF, PNG or JPG files with valid filenames are accepted.",
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
            while data := (await f.read(1024 * 1024)):
                if size == 0:
                    if not (
                        data.startswith(b"%PDF-")
                        or data.startswith(b"\x89PNG\r\n\x1a\n")
                        or data.startswith(b"\xff\xd8\xff")
                    ):
                        raise ApplicationError(
                            "invalid_input", f"{filename}: invalid PDF or image header."
                        )
                size += len(data)
                if size > min(
                    settings.max_file_bytes, limits.get("max_mb", 30) * 1024 * 1024
                ):
                    raise ApplicationError(
                        "too_large", f"{filename}: file exceeds 30 MB."
                    )
                chunks.extend(data)
                sha.update(data)
            if size == 0:
                raise ApplicationError("invalid_input", "Empty PDF.")
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
                (hint, customer, classification) = (
                    resolved["hint"],
                    resolved["customer"],
                    resolved["classification"],
                )
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
                            k: v for (k, v) in resolved.items() if k != "classification"
                        },
                    },
                    doc_type=hint,
                    classification=classification,
                )
                db.add(doc)
                db.flush()
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


def preview_batch_grouping(*, batch_id: str, user):
    from app.grouping_repair import preview

    with SessionLocal() as db:
        return preview(db, batch_id, user)


def repair_batch_grouping(*, batch_id: str, data: RegroupInput, user):
    from app.grouping_repair import apply

    with SessionLocal.begin() as db:
        return apply(db, batch_id, user, data.labels, data.revision, data.reason)
