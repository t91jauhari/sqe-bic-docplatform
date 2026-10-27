"""Administration HTTP boundary."""

from app.application import administration as use_cases
from fastapi import APIRouter, Depends, Body
from app.security import current_user
from app.api.dependencies import ADMIN, USER_ADMIN
from app.api.contracts import BranchInput, BranchUpdateInput, UserInput

router = APIRouter(tags=["administration"])


@router.get("/api/branches")
def branches(user=Depends(current_user)):
    return use_cases.branches(user=user)


@router.post("/api/branches")
def add_branch(data: BranchInput, user=Depends(ADMIN)):
    return use_cases.add_branch(data=data, user=user)


@router.put("/api/branches/{branch_id}")
def modify_branch(branch_id: str, data: BranchUpdateInput, user=Depends(ADMIN)):
    return use_cases.update_branch(branch_id=branch_id, data=data, user=user)


@router.get("/api/access/role-permissions")
def get_role_permissions(user=Depends(current_user)):
    return use_cases.get_role_permissions(user=user)


@router.put("/api/access/role-permissions")
def save_role_permissions(data: dict = Body(...), user=Depends(ADMIN)):
    return use_cases.update_role_permissions(data=data, user=user)


@router.get("/api/users")
def users(user=Depends(USER_ADMIN)):
    return use_cases.users(user=user)


@router.post("/api/users")
def add_user(data: UserInput, user=Depends(USER_ADMIN)):
    return use_cases.add_user(data=data, user=user)
