"""Field Processing HTTP boundary."""

from app.application import field_processing as use_cases
from fastapi import APIRouter
from fastapi import Depends
from app.security import current_user
from app.api.dependencies import WRITE
from app.api.contracts import ReprocessFieldsInput, RetryFieldsInput

router = APIRouter(tags=["field processing"])


@router.post("/api/documents/{doc_id}/reprocess-fields", status_code=202)
def reprocess_document_fields(
    doc_id: str, data: ReprocessFieldsInput, user=Depends(WRITE)
):
    return use_cases.reprocess_document_fields(doc_id=doc_id, data=data, user=user)


@router.get("/api/documents/{doc_id}/reprocess-fields")
def field_reprocess_history(doc_id: str, user=Depends(current_user)):
    return use_cases.field_reprocess_history(doc_id=doc_id, user=user)


@router.post(
    "/api/documents/{doc_id}/reprocess-fields/{request_id}/retry", status_code=202
)
def retry_field_request(
    doc_id: str,
    request_id: str,
    data: RetryFieldsInput = RetryFieldsInput(),
    user=Depends(WRITE),
):
    return use_cases.retry_field_request(
        doc_id=doc_id, request_id=request_id, data=data, user=user
    )
