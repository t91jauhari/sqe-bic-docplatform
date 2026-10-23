"""One extraction entry point; submission recovery belongs to each adapter."""
import copy
from collections.abc import Mapping

from app.configuration.codec import fingerprint
from .adapters import default_adapters
from .contracts import ExtractionAdapter, ExtractionRequest, ExtractionResult, ProcessingIssue


def extract_document(document, configuration, heartbeat, *, adapters: Mapping[str, ExtractionAdapter] | None = None):
    if configuration.get("provider") == "llama":
        raise ProcessingIssue("Llama provider has been removed. Publish a Spider-AI configuration and explicitly upgrade the case before retrying. Historical results are retained.")
    registry = default_adapters() if adapters is None else adapters
    provider_id = configuration.get("provider")
    adapter = registry.get(provider_id) if isinstance(provider_id, str) else None
    if adapter is None:
        raise ProcessingIssue("The configured extraction provider is not registered.")
    snapshot = copy.deepcopy(configuration)
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
