"""Organization-scoped connector reads; secrets never appear in object repr."""
import copy
from dataclasses import dataclass, field

from pydantic import ValidationError
from sqlalchemy import select

from app.db import Connector, SpiderConnector
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
        canonical_provider = "gemini" if provider in {"gemini", "google-gemini"} else provider
        with self.sessions() as session:
            record = None
            if canonical_provider != "spider-ai":
                record = session.scalars(
                    select(Connector).where(
                        Connector.org == organization,
                        Connector.provider_type == canonical_provider,
                    ).order_by(Connector.is_active.desc(), Connector.created_at.desc())
                ).first()
            else:
                # For spider-ai: check if an explicitly active connector is registered in connectors table
                record = session.scalars(
                    select(Connector).where(
                        Connector.org == organization,
                        Connector.provider_type == "spider-ai",
                        Connector.is_active.is_(True),
                    ).order_by(Connector.created_at.desc())
                ).first()
                # If no active connector exists, use the canonical spider_connectors table
                if not record:
                    record = session.scalar(select(SpiderConnector).where(SpiderConnector.org == organization))

            if record is None:
                raw = {}
                encrypted = ""
            else:
                raw = copy.deepcopy(record.options) if record.options else {}
                encrypted = record.encrypted or ""

        try:
            options = normalized_options(canonical_provider, raw)
        except (ValueError, ValidationError):
            raise ProcessingIssue("Extraction connector settings are invalid. Review the saved connector configuration.") from None

        return ProviderConnection(self.decrypt(encrypted) if encrypted else "", options)
