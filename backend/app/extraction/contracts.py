"""Provider-neutral request/result contracts, without HTTP or database imports."""
from dataclasses import dataclass
from typing import Callable, Protocol


class ProcessingIssue(Exception):
    pass


class ExtractionDocument(Protocol):
    id: str
    org: str
    case_id: str
    doc_type: str


@dataclass(frozen=True)
class ExtractionRequest:
    document: ExtractionDocument
    configuration: dict
    configuration_sha256: str
    heartbeat: Callable[[], None]


@dataclass(frozen=True)
class ExtractionResult:
    response: dict | None
    classification: dict


class ExtractionAdapter(Protocol):
    def extract(self, request: ExtractionRequest) -> tuple[dict | None, dict]: ...


class ProviderStateStore(Protocol):
    def read(self, document_id: str) -> dict: ...
    def checkpoint(self, document_id: str, status: str | None = None, **state) -> None: ...
