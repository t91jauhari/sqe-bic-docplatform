"""Durable provider checkpoints with explicit independent transactions.

These commits must precede external submissions and survive a later job rollback.
Row locks serialize concurrent merges instead of overwriting other stage receipts.
"""
import copy

from sqlalchemy import select

from app.db import Document
from .contracts import ProcessingIssue


class SqlProviderState:
    def __init__(self, sessions):
        self.sessions = sessions

    def read(self, document_id: str) -> dict:
        with self.sessions() as session:
            document = session.get(Document, document_id)
            if document is None:
                raise ProcessingIssue("Document no longer exists; provider state cannot be read.")
            return copy.deepcopy(document.provider_state or {})

    def checkpoint(self, document_id: str, status: str | None = None, **state) -> None:
        with self.sessions.begin() as session:
            document = session.scalar(select(Document).where(Document.id == document_id).with_for_update())
            if document is None:
                raise ProcessingIssue("Document no longer exists; provider submission was not started.")
            document.provider_state = {**copy.deepcopy(document.provider_state or {}), **copy.deepcopy(state)}
            if status:
                document.status = status
