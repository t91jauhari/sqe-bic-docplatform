"""Organization-scoped connector reads; secrets never appear in object repr."""
import copy
from dataclasses import dataclass, field

from pydantic import ValidationError
from sqlalchemy import select

from app.db import SpiderConnector
from .connector_contracts import normalized_options
from .contracts import ProcessingIssue


@dataclass(frozen=True)
class ProviderConnection:
    api_key: str = field(repr=False)
    options: dict = field(repr=False)


class SqlConnectorRepository:
    def __init__(self, sessions, decrypt):
        self.sessions, self.decrypt = sessions, decrypt

    def read(self, organization, provider):
        model = {"spider-ai": SpiderConnector}.get(provider)
        if model is None:
            raise ProcessingIssue("The configured extraction provider is not registered.")
        with self.sessions() as session:
            record = session.scalar(select(model).where(model.org == organization))
            raw = copy.deepcopy(record.options) if record else {}
            encrypted = record.encrypted if record else ""
        try:
            options = normalized_options(provider, raw)
        except (ValueError, ValidationError):
            raise ProcessingIssue("Extraction connector settings are invalid. Review the saved connector configuration.") from None
        return ProviderConnection(self.decrypt(encrypted) if encrypted else "", options)
