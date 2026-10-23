"""Notifications HTTP boundary."""

from app.application import notifications as use_cases
from fastapi import APIRouter
from fastapi import Depends
from app.security import current_user

router = APIRouter(tags=["notifications"])


@router.get("/api/inbox")
def inbox(offset: int = 0, user=Depends(current_user)):
    return use_cases.inbox(offset=offset, user=user)


@router.post("/api/inbox/{item_id}/read")
def read_inbox(item_id: str, user=Depends(current_user)):
    return use_cases.read_inbox(item_id=item_id, user=user)


@router.get("/api/events")
def events(after: float = 0, user=Depends(current_user)):
    return use_cases.events(after=after, user=user)
