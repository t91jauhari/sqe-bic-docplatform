"""One extraction entry point; submission recovery belongs to each adapter."""
import copy
from collections.abc import Mapping
from sqlalchemy import select

from app.configuration.codec import fingerprint
from .adapters import default_adapters
from .contracts import ExtractionAdapter, ExtractionRequest, ExtractionResult, ProcessingIssue


def extract_document(document, configuration, heartbeat, *, adapters: Mapping[str, ExtractionAdapter] | None = None):
    if configuration.get("provider") == "llama":
        raise ProcessingIssue("Llama provider has been removed. Publish a Spider-AI or Google Gemini configuration and explicitly upgrade the case before retrying. Historical results are retained.")
    registry = default_adapters() if adapters is None else adapters
    # Check active connector in database for this organization first
    active_provider = None
    try:
        from app.db import SessionLocal, Connector
        with SessionLocal() as db:
            org = getattr(document, "org", None)
            if org:
                active_conn = db.scalar(
                    select(Connector).where(Connector.org == org, Connector.is_active == True)
                )
                if active_conn and active_conn.provider_type in registry:
                    active_provider = active_conn.provider_type
    except Exception:
        pass

    provider_id = active_provider or configuration.get("provider") or "spider-ai"
    if provider_id not in registry:
        provider_id = "spider-ai"

    adapter = registry.get(provider_id)
    if adapter is None:
        raise ProcessingIssue(f"The configured extraction provider '{provider_id}' is not registered.")
    snapshot = copy.deepcopy(configuration)
    snapshot["provider"] = provider_id
    request = ExtractionRequest(document, snapshot, fingerprint(snapshot), heartbeat)
    result = adapter.extract(request)
    if not isinstance(result, tuple) or len(result) != 2:
        raise ProcessingIssue("Extraction provider returned an invalid result contract.")
    response, classification = result
    if not isinstance(classification, dict) or (response is not None and (
        not isinstance(response, dict) or not isinstance(response.get("extract_result"), dict)
    )):
        raise ProcessingIssue("Extraction provider returned an invalid extraction or classification contract.")
    return ExtractionResult(response, classification)
