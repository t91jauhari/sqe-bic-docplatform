"""Provider settings HTTP boundary; no extraction submissions here."""
from fastapi import APIRouter, Depends, HTTPException

from app.db import SessionLocal
from app.security import require_roles
from .administration import connector_view, update_connector
from .connector_contracts import SpiderConnectorInput

router = APIRouter(tags=['extraction settings'])
ADMIN = require_roles('bank_admin')


@router.get('/api/connectors/spider-ai')
def spider_connector(user=Depends(ADMIN)):
    with SessionLocal() as session:
        return connector_view(session, organization=user.org)


@router.put('/api/connectors/spider-ai')
def save_spider_connector(data: SpiderConnectorInput, user=Depends(ADMIN)):
    try:
        with SessionLocal.begin() as session:
            return update_connector(session, organization=user.org, actor=user.id, data=data)
    except ValueError:
        raise HTTPException(422, 'Connector settings are invalid. Review all configured options.') from None


@router.get('/api/connector')
@router.put('/api/connector')
def removed_connector(user=Depends(ADMIN)):
    raise HTTPException(410, 'Llama provider has been removed. Configure Spider-AI instead.')
