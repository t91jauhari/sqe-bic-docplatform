"""Administration HTTP boundary."""

from app.application import administration as use_cases
from fastapi import APIRouter
from fastapi import Depends
from app.security import current_user
from app.api.dependencies import ADMIN, USER_ADMIN
from app.api.contracts import BranchInput, UserInput

router = APIRouter(tags=["administration"])


@router.get("/api/branches")
def branches(user=Depends(current_user)):
    return use_cases.branches(user=user)


@router.post("/api/branches")
def add_branch(data: BranchInput, user=Depends(ADMIN)):
    return use_cases.add_branch(data=data, user=user)


@router.get("/api/users")
def users(user=Depends(USER_ADMIN)):
    return use_cases.users(user=user)


@router.post("/api/users")
def add_user(data: UserInput, user=Depends(USER_ADMIN)):
    return use_cases.add_user(data=data, user=user)
