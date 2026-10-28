"""Connector administration inside the caller's transaction."""

import copy
import time
from sqlalchemy import select, update
from app.db import Connector, SpiderConnector
from app.auditing import audit
from app.crypto import encrypt, decrypt
from .connector_contracts import (
    SpiderConnectorInput,
    administrative_options,
    normalized_options,
)


def connector_view(session, *, organization):
    item = session.scalar(
        select(SpiderConnector).where(SpiderConnector.org == organization)
    )
    return {
        "configured": bool(item and item.encrypted),
        **administrative_options("spider-ai", item.options if item else {}),
    }


def update_connector(session, *, organization, actor, data: SpiderConnectorInput):
    item = session.scalar(
        select(SpiderConnector).where(SpiderConnector.org == organization)
    )
    if not item:
        item = SpiderConnector(org=organization, encrypted="", options={})
        session.add(item)
    candidate = {
        **(item.options or {}),
        **data.model_dump(exclude={"api_key"}, exclude_unset=True),
    }
    validated = normalized_options("spider-ai", candidate)
    if data.api_key is not None:
        item.encrypted = encrypt(data.api_key)
    item.options = {**candidate, **validated}
    audit(
        session,
        organization,
        actor,
        "spider.connector_updated",
        credential_changed=data.api_key is not None,
    )
    return {"configured": bool(item.encrypted), "options": validated}


def list_connectors(session, *, organization):
    """List all registered connectors for an organization."""
    rows = session.scalars(
        select(Connector)
        .where(Connector.org == organization)
        .order_by(Connector.is_active.desc(), Connector.created_at.desc())
    ).all()

    connectors = []
    has_active = False
    for r in rows:
        if r.is_active:
            has_active = True
        options = copy.deepcopy(r.options) if r.options else {}
        provider = r.provider_type or options.get("provider_type", "spider-ai")
        model = r.model_id or options.get("model_id", "")
        name = r.name or f"{provider.capitalize()} ({model})"
        connectors.append({
            "id": r.id,
            "name": name,
            "provider_type": provider,
            "model_id": model,
            "is_active": bool(r.is_active),
            "configured": bool(r.encrypted),
            "base_url": options.get("base_url", ""),
            "options": options,
            "created_at": r.created_at,
        })

    # Include legacy SpiderConnector if present and no active connector exists
    legacy_spider = session.scalar(
        select(SpiderConnector).where(SpiderConnector.org == organization)
    )
    if legacy_spider and not any(c["provider_type"] == "spider-ai" for c in connectors):
        opts = legacy_spider.options or {}
        connectors.append({
            "id": legacy_spider.id,
            "name": "Spider-AI Legacy Connector",
            "provider_type": "spider-ai",
            "model_id": opts.get("model_id", "pct-prod-spider/pecut/gemini-3.8-flash-high"),
            "is_active": not has_active,
            "configured": bool(legacy_spider.encrypted),
            "base_url": opts.get("base_url", ""),
            "options": opts,
            "created_at": legacy_spider.created_at,
        })

    return connectors


def create_connector(session, *, organization, actor, data: dict):
    """Register a new named connector (Google Gemini or Spider-AI)."""
    provider = data.get("provider_type", "gemini")
    raw_model = data.get("model_id", "gemini-2.5-pro").strip()
    model_id = raw_model.removeprefix("models/")
    name = data.get("name", "").strip() or f"{provider.capitalize()} - {model_id}"
    api_key = data.get("api_key", "").strip() if data.get("api_key") else ""
    is_active = bool(data.get("is_active", False))

    raw_options = data.get("options", {})
    if "base_url" in data and "base_url" not in raw_options:
        raw_options["base_url"] = data["base_url"]
    raw_options["model_id"] = model_id

    validated = normalized_options(provider, raw_options)

    if is_active:
        # Deactivate others
        session.execute(
            update(Connector).where(Connector.org == organization).values(is_active=False)
        )

    item = Connector(
        org=organization,
        name=name,
        provider_type=provider,
        model_id=model_id,
        is_active=is_active,
        encrypted=encrypt(api_key) if api_key else "",
        options={**raw_options, **validated},
    )
    session.add(item)
    session.flush()

    audit(
        session,
        organization,
        actor,
        "connector.created",
        connector_id=item.id,
        provider=provider,
        model=model_id,
    )
    return {
        "id": item.id,
        "name": item.name,
        "provider_type": item.provider_type,
        "model_id": item.model_id,
        "is_active": item.is_active,
        "configured": bool(item.encrypted),
        "options": item.options,
    }


def update_connector_item(session, *, organization, actor, connector_id: str, data: dict):
    """Update an existing connector."""
    item = session.scalar(
        select(Connector).where(Connector.org == organization, Connector.id == connector_id)
    )
    if not item:
        raise ValueError("Connector not found.")

    provider = data.get("provider_type") or item.provider_type
    if "name" in data and data["name"].strip():
        item.name = data["name"].strip()
    if "model_id" in data and data["model_id"].strip():
        item.model_id = data["model_id"].strip().removeprefix("models/")
    if "provider_type" in data:
        item.provider_type = data["provider_type"]

    options = {**(item.options or {}), **data.get("options", {})}
    if "base_url" in data:
        options["base_url"] = data["base_url"]
    options["model_id"] = item.model_id
    validated = normalized_options(provider, options)
    item.options = {**options, **validated}

    if data.get("api_key"):
        item.encrypted = encrypt(data["api_key"].strip())

    if data.get("is_active"):
        session.execute(
            update(Connector).where(Connector.org == organization).values(is_active=False)
        )
        item.is_active = True

    audit(
        session,
        organization,
        actor,
        "connector.updated",
        connector_id=item.id,
        provider=item.provider_type,
    )
    return {
        "id": item.id,
        "name": item.name,
        "provider_type": item.provider_type,
        "model_id": item.model_id,
        "is_active": item.is_active,
        "configured": bool(item.encrypted),
        "options": item.options,
    }


def delete_connector_item(session, *, organization, actor, connector_id: str):
    """Delete a connector."""
    item = session.scalar(
        select(Connector).where(Connector.org == organization, Connector.id == connector_id)
    )
    if not item:
        raise ValueError("Connector not found.")
    session.delete(item)
    audit(session, organization, actor, "connector.deleted", connector_id=connector_id)
    return {"deleted": True, "id": connector_id}


def activate_connector_item(session, *, organization, actor, connector_id: str):
    """Set connector as active extraction provider."""
    item = session.scalar(
        select(Connector).where(Connector.org == organization, Connector.id == connector_id)
    )
    if not item:
        raise ValueError("Connector not found.")
    session.execute(
        update(Connector).where(Connector.org == organization).values(is_active=False)
    )
    item.is_active = True
    audit(session, organization, actor, "connector.activated", connector_id=connector_id)
    return {"activated": True, "id": item.id, "provider_type": item.provider_type}


def test_connector_connectivity(session, *, organization, data: dict):
    """Test connection and return latency / status."""
    provider = data.get("provider_type", "gemini")
    model_id = data.get("model_id", "gemini-2.5-pro")
    base_url = data.get("base_url") or "https://generativelanguage.googleapis.com/v1beta"
    api_key = data.get("api_key", "").strip()

    if not api_key and data.get("connector_id"):
        item = session.scalar(
            select(Connector).where(Connector.org == organization, Connector.id == data["connector_id"])
        )
        if item and item.encrypted:
            api_key = decrypt(item.encrypted)

    if not api_key:
        return {"success": False, "error": "API key is required for connectivity test."}

    if provider in {"gemini", "google-gemini"}:
        from app.gemini_provider import test_gemini_ping
        return test_gemini_ping(api_key, base_url, model_id)
    else:
        # Spider / OpenAI-compatible test
        import httpx
        start = time.time()
        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"model": model_id, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 2}
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(url, headers=headers, json=payload)
                latency = int((time.time() - start) * 1000)
                if resp.status_code == 200:
                    return {"success": True, "latency_ms": latency, "model": model_id}
                return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
