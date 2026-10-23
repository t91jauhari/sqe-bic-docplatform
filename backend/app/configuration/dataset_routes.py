"""Reference registry administration; imports never rewrite extraction values."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import inspect

from app.db import SessionLocal
from app.auditing import audit
from app.security import current_user, require_roles
from app.settings import settings
from .datasets import DatasetReference, DatasetIntegrityError, register_dataset
from .dataset_sources import catalog

router = APIRouter(prefix="/api/reference-datasets", tags=["Reference datasets"])


@router.get("")
def list_datasets(user=Depends(current_user)):
    with SessionLocal() as session:
        return catalog(session, user.org)


@router.post("", status_code=201)
def import_dataset(data: DatasetReference, user=Depends(require_roles("bank_admin"))):
    if settings.dataset_read_mode != "registry":
        raise HTTPException(
            409,
            "Dataset imports require registry mode after the explicit migration and baseline import.",
        )
    with SessionLocal.begin() as session:
        if not inspect(session.connection()).has_table("reference_datasets"):
            raise HTTPException(
                409, "Apply the reference dataset migration before importing."
            )
        try:
            record = register_dataset(session, user.org, data.model_dump())
        except DatasetIntegrityError as exc:
            raise HTTPException(409, str(exc)) from exc
        audit(
            session,
            user.org,
            user.id,
            "reference_dataset.imported",
            dataset_id=record.dataset_id,
            digest=record.digest,
        )
        return {
            "id": record.dataset_id,
            "digest": record.digest,
            "source_name": record.payload["source_name"],
        }
