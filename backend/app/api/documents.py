"""Documents HTTP boundary."""

from app.application import documents as use_cases
from fastapi import APIRouter
from fastapi import Depends, Response
from app.db import Document, SessionLocal
from app.security import authorized, current_user
from app.storage import original_key, store, sniff_mime
from app.api.dependencies import ADMIN, REVIEW, WRITE
from app.api.contracts import (
    ClassificationInput,
    CorrectionInput,
    EffectiveCorrectionInput,
    MoveInput,
    ReconcileInput,
    SpiderResubmit,
)

router = APIRouter(tags=["documents"])


@router.post("/api/documents/{doc_id}/spider-resubmit", status_code=202)
def spider_resubmit(doc_id: str, data: SpiderResubmit, user=Depends(WRITE)):
    return use_cases.spider_resubmit(doc_id=doc_id, data=data, user=user)


@router.get("/api/documents/failure-summary")
def failure_summary(since: float = 0, user=Depends(current_user)):
    'Group recent document errors by their first-line prefix so the UI can\nsurface transient-failure clusters (e.g. one network outage failing many\nuploads). Read-only and org-scoped via `authorized`/scoped queries.'
    return use_cases.failure_summary(since=since, user=user)


@router.get("/api/documents/{doc_id}/file")
def document_file(doc_id: str, user=Depends(current_user)):
    with SessionLocal() as db:
        d = authorized(db, Document, doc_id, user)
    data = store().read(original_key(d))
    return Response(
        data,
        media_type=sniff_mime(data),
        headers={"Content-Disposition": "inline", "Cache-Control": "no-store"},
    )


@router.post("/api/documents/{doc_id}/retry", status_code=202)
def retry_document(doc_id: str, user=Depends(WRITE)):
    return use_cases.retry_document(doc_id=doc_id, user=user)


@router.post("/api/documents/{doc_id}/classification", status_code=202)
def confirm_type(doc_id: str, data: ClassificationInput, user=Depends(REVIEW)):
    return use_cases.confirm_type(doc_id=doc_id, data=data, user=user)


@router.post("/api/documents/{doc_id}/corrections", status_code=202)
def correct_field(doc_id: str, data: CorrectionInput, user=Depends(REVIEW)):
    return use_cases.correct_field(doc_id=doc_id, data=data, user=user)


@router.post("/api/documents/{doc_id}/effective-corrections", status_code=202)
def correct_effective_field(
    doc_id: str, data: EffectiveCorrectionInput, user=Depends(REVIEW)
):
    return use_cases.correct_effective_field(doc_id=doc_id, data=data, user=user)


@router.post("/api/documents/{doc_id}/move")
def move_document(doc_id: str, data: MoveInput, user=Depends(REVIEW)):
    return use_cases.move_document(doc_id=doc_id, data=data, user=user)


@router.post("/api/documents/{doc_id}/reconcile", status_code=202)
def reconcile(doc_id: str, data: ReconcileInput, user=Depends(ADMIN)):
    return use_cases.reconcile(doc_id=doc_id, data=data, user=user)
