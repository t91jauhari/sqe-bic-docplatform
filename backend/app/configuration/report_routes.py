"""Report binding metadata for configuration drafts; publication stays explicit."""
from fastapi import APIRouter, Depends
from app.security import require_roles
from .reporting import defaults

router = APIRouter(prefix='/api/config/report-bindings', tags=['Report configuration'])


@router.get('')
def report_binding_defaults(user=Depends(require_roles('bank_admin'))):
    return defaults()
