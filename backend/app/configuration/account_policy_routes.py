from fastapi import APIRouter, Depends
from app.security import require_roles
from .account_policies import captured_conditions

router = APIRouter(prefix='/api/config/account-conditions', tags=['SOP configuration'])


@router.get('')
def condition_metadata(user=Depends(require_roles('bank_admin'))):
    return captured_conditions()
