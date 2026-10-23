"""Operations HTTP boundary."""

from app.application import operations as use_cases
from fastapi import APIRouter
from fastapi import Depends
from app.security import current_user
from app.api.dependencies import ADMIN

router = APIRouter(tags=["operations"])


@router.get("/api/operations/metrics")
def operations_metrics(user=Depends(ADMIN)):
    return use_cases.operations_metrics(user=user)


@router.get("/api/dashboard")
def dashboard(user=Depends(current_user)):
    return use_cases.dashboard(user=user)
