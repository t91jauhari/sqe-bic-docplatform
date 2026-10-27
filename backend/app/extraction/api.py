"""Provider settings HTTP boundary; multi-provider connector management."""
from fastapi import APIRouter, Depends, HTTPException, Body

from app.db import SessionLocal
from app.security import require_roles
from .administration import (
    connector_view,
    update_connector,
    list_connectors,
    create_connector,
    update_connector_item,
    delete_connector_item,
    activate_connector_item,
    test_connector_connectivity,
)
from .connector_contracts import SpiderConnectorInput

router = APIRouter(tags=['extraction settings'])
ADMIN = require_roles('bank_admin')


# Backward compatibility for legacy spider-ai forms
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


@router.get('/api/connectors')
def get_all_connectors(user=Depends(ADMIN)):
    """List all registered extraction connectors (Spider-AI, Google Gemini, etc.)."""
    with SessionLocal() as session:
        return list_connectors(session, organization=user.org)


@router.post('/api/connectors')
def register_connector(data: dict = Body(...), user=Depends(ADMIN)):
    """Register a new extraction connector."""
    try:
        with SessionLocal.begin() as session:
            return create_connector(session, organization=user.org, actor=user.id, data=data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.put('/api/connectors/{connector_id}')
def modify_connector(connector_id: str, data: dict = Body(...), user=Depends(ADMIN)):
    """Update an existing extraction connector."""
    try:
        with SessionLocal.begin() as session:
            return update_connector_item(session, organization=user.org, actor=user.id, connector_id=connector_id, data=data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.delete('/api/connectors/{connector_id}')
def remove_connector(connector_id: str, user=Depends(ADMIN)):
    """Delete a connector."""
    try:
        with SessionLocal.begin() as session:
            return delete_connector_item(session, organization=user.org, actor=user.id, connector_id=connector_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post('/api/connectors/{connector_id}/activate')
def set_active_connector(connector_id: str, user=Depends(ADMIN)):
    """Activate a connector as the organization's primary model."""
    try:
        with SessionLocal.begin() as session:
            return activate_connector_item(session, organization=user.org, actor=user.id, connector_id=connector_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post('/api/connectors/test')
def test_connector(data: dict = Body(...), user=Depends(ADMIN)):
    """Live connectivity test for Gemini or Spider-AI."""
    with SessionLocal() as session:
        return test_connector_connectivity(session, organization=user.org, data=data)


@router.get('/api/connector')
@router.put('/api/connector')
def removed_connector(user=Depends(ADMIN)):
    raise HTTPException(410, 'Llama provider has been removed. Configure Spider-AI or Google Gemini instead.')
