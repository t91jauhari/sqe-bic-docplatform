"""Connector administration inside the caller's transaction."""
from sqlalchemy import select

from app.db import SpiderConnector
from app.domain import audit
from app.security import encrypt
from .connector_contracts import SpiderConnectorInput, administrative_options, normalized_options


def connector_view(session, *, organization):
    item = session.scalar(select(SpiderConnector).where(SpiderConnector.org == organization))
    return {'configured': bool(item and item.encrypted),
            **administrative_options('spider-ai', item.options if item else {})}


def update_connector(session, *, organization, actor, data: SpiderConnectorInput):
    item = session.scalar(select(SpiderConnector).where(SpiderConnector.org == organization))
    if not item:
        item = SpiderConnector(org=organization, encrypted='', options={})
        session.add(item)
    candidate = {**(item.options or {}), **data.model_dump(exclude={'api_key'}, exclude_unset=True)}
    validated = normalized_options('spider-ai', candidate)
    if data.api_key is not None:
        item.encrypted = encrypt(data.api_key)
    item.options = {**candidate, **validated}
    audit(session, organization, actor, 'spider.connector_updated',
          credential_changed=data.api_key is not None)
    return {'configured': bool(item.encrypted), 'options': validated}
