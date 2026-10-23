"""Immutable, organization-scoped reference datasets, separate from extraction.

Dataset IDs identify immutable content. Replacing a workbook requires a new ID
and an explicit configuration publication; existing case pins retain their ID.
The caller owns transactions and authorization.
"""
import copy
import json

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import JSON, String, UniqueConstraint, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .codec import fingerprint


class DatasetReference(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,119}$")
    source_name: str = Field(min_length=1, max_length=500)
    sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    samples: list[dict] = Field(max_length=10000)
    rows: list[dict] = Field(max_length=100000)

    @model_validator(mode="after")
    def validate_references(self):
        samples = [sample.get("id") for sample in self.samples]
        if any(not isinstance(value, str) or not value for value in samples) or len(set(samples)) != len(samples):
            raise ValueError("Sample IDs must be unique nonempty strings.")
        if any(not isinstance(sample.get("name"), str) for sample in self.samples):
            raise ValueError("Every sample requires a display name.")
        rows = [row.get("id") for row in self.rows]
        if any(not isinstance(value, str) or not value for value in rows) or len(set(rows)) != len(rows):
            raise ValueError("Row IDs must be unique nonempty strings.")
        for row in self.rows:
            if not all(isinstance(row.get(key), str) and row[key] for key in ("document_type", "label", "kind")) or type(row.get('section')) not in {int, str}:
                raise ValueError("Every row requires section, document type, label and value kind.")
            if row.get("field") is not None and not isinstance(row["field"], str):
                raise ValueError("Field mappings must be strings or null.")
            if not isinstance(row.get("values"), dict) or set(row["values"]) - set(samples):
                raise ValueError("Row values must reference registered sample IDs.")
        json.dumps(self.model_dump(), allow_nan=False)
        return self


class DatasetBase(DeclarativeBase):
    pass


class DatasetRecord(DatasetBase):
    __tablename__ = "reference_datasets"
    __table_args__ = (UniqueConstraint("organization", "dataset_id"),)
    organization: Mapped[str] = mapped_column(String(80), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    digest: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)


class DatasetIntegrityError(ValueError):
    pass


def register_dataset(session, organization, payload):
    validated = DatasetReference.model_validate(payload).model_dump()
    digest = fingerprint(validated)
    existing = session.get(DatasetRecord, (organization, validated["id"]))
    if existing:
        if existing.digest != digest or fingerprint(existing.payload) != digest:
            raise DatasetIntegrityError("Dataset IDs are immutable. Import the workbook under a new ID.")
        return existing
    record = DatasetRecord(organization=organization, dataset_id=validated["id"], digest=digest, payload=validated)
    session.add(record)
    session.flush()
    return record


def read_dataset(session, organization, dataset_id):
    record = session.get(DatasetRecord, (organization, dataset_id))
    if record is None:
        raise DatasetIntegrityError("The configured reference dataset is not registered for this organization.")
    if fingerprint(record.payload) != record.digest:
        raise DatasetIntegrityError("Reference dataset integrity verification failed.")
    return copy.deepcopy(record.payload)


def dataset_catalog(session, organization):
    records = session.scalars(select(DatasetRecord).where(DatasetRecord.organization == organization).order_by(DatasetRecord.dataset_id))
    return [{"id": record.dataset_id, "source_name": record.payload["source_name"], "digest": record.digest}
            for record in records]
