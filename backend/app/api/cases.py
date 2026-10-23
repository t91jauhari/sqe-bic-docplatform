"""Cases HTTP boundary."""

from app.application import cases as use_cases
from app.application import case_configuration as configuration_use_cases
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from fastapi import Depends
from app.security import current_user
from app.security import require_roles
from app.contracts import CaseConfigurationInput
from app.api.dependencies import REVIEW, WRITE
from app.api.contracts import (
    ContextInput,
    EnumRevalidationInput,
    FindingReview,
    TaskAssignment,
)

router = APIRouter(tags=["cases"])


@router.post("/api/cases/{case_id}/configuration", status_code=202)
def adopt_case_configuration(case_id: str, data: CaseConfigurationInput,
                            user=Depends(require_roles("bank_admin", "branch_admin"))):
    return configuration_use_cases.adopt_configuration(case_id=case_id, data=data, user=user)


@router.get("/api/cases")
def cases(
    q: str = "",
    status: str = "",
    transaction_flow: str = "",
    offset: int = 0,
    limit: int = 50,
    user=Depends(current_user),
):
    return use_cases.cases(
        q=q,
        status=status,
        transaction_flow=transaction_flow,
        offset=offset,
        limit=limit,
        user=user,
    )


@router.get("/api/cases/{case_id}")
def case_detail(case_id: str, user=Depends(current_user)):
    return JSONResponse(use_cases.case_detail(case_id=case_id, user=user))


@router.put("/api/cases/{case_id}/context")
def edit_case_context(case_id: str, data: ContextInput, user=Depends(WRITE)):
    return use_cases.edit_case_context(case_id=case_id, data=data, user=user)


@router.post("/api/cases/{case_id}/sop-rerun", status_code=202)
def rerun_sop(case_id: str, user=Depends(WRITE)):
    return use_cases.rerun_sop(case_id=case_id, user=user)


@router.post("/api/cases/{case_id}/sop-review", status_code=202)
def review_sop(case_id: str, data: FindingReview, user=Depends(REVIEW)):
    return use_cases.review_sop(case_id=case_id, data=data, user=user)


@router.post("/api/cases/{case_id}/retry-documents", status_code=202)
def retry_case_documents(case_id: str, user=Depends(WRITE)):
    return use_cases.retry_case_documents(case_id=case_id, user=user)


@router.get("/api/cases/{case_id}/assignment")
def case_assignment(case_id: str, user=Depends(current_user)):
    return use_cases.case_assignment(case_id=case_id, user=user)


@router.put("/api/cases/{case_id}/assignment")
def assign_case(case_id: str, data: TaskAssignment, user=Depends(REVIEW)):
    return use_cases.assign_case(case_id=case_id, data=data, user=user)


@router.post("/api/cases/{case_id}/revalidate-enum-aliases", status_code=202)
def revalidate_enum_aliases(
    case_id: str, data: EnumRevalidationInput, user=Depends(REVIEW)
):
    return use_cases.revalidate_enum_aliases(case_id=case_id, data=data, user=user)
