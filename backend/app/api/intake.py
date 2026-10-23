"""Intake HTTP boundary."""

from app.application import intake as use_cases
from fastapi import APIRouter
from typing import Annotated
from fastapi import Depends, File, Form, Header, UploadFile
from app.api.dependencies import REVIEW, WRITE
from app.api.contracts import PreviewInput, RegroupInput

router = APIRouter(tags=["intake"])


@router.post("/api/uploads/preview")
def preview_upload(data: PreviewInput, user=Depends(WRITE)):
    return use_cases.preview_upload(data=data, user=user)


@router.post("/api/uploads", status_code=202)
async def upload(
    branch_id: Annotated[str, Form()],
    template: Annotated[str, Form()],
    files: Annotated[list[UploadFile], File()],
    grouping: Annotated[str, Form()] = "{}",
    case_id: Annotated[str, Form()] = "",
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")] = "",
    user=Depends(WRITE),
):
    return await use_cases.upload(
        branch_id=branch_id,
        template=template,
        files=files,
        grouping=grouping,
        case_id=case_id,
        idempotency_key=idempotency_key,
        user=user,
    )


@router.get("/api/batches/{batch_id}/grouping")
def preview_batch_grouping(batch_id: str, user=Depends(REVIEW)):
    return use_cases.preview_batch_grouping(batch_id=batch_id, user=user)


@router.post("/api/batches/{batch_id}/grouping")
def repair_batch_grouping(batch_id: str, data: RegroupInput, user=Depends(REVIEW)):
    return use_cases.repair_batch_grouping(batch_id=batch_id, data=data, user=user)
