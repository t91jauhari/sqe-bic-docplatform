import time
import uuid

from sqlalchemy import (
    JSON,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .settings import settings


def uid():
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False, "timeout": 30}
    if settings.database_url.startswith("sqlite")
    else {},
)
if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def sqlite_options(conn, _):
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")


SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Record(Base):
    __abstract__ = True
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org: Mapped[str] = mapped_column(String(80), index=True)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class LocationFeedback(Record):
    __tablename__ = "location_feedback"
    branch_id: Mapped[str] = mapped_column(String(36), index=True)
    document_id: Mapped[str] = mapped_column(String(36), index=True)
    document_type: Mapped[str] = mapped_column(String(80), index=True)
    field: Mapped[str] = mapped_column(String(200))
    schema_hash: Mapped[str] = mapped_column(String(64))
    source_sha256: Mapped[str] = mapped_column(String(64))
    page_number: Mapped[int] = mapped_column(Integer)
    bbox: Mapped[list] = mapped_column(JSON)
    layout: Mapped[dict] = mapped_column(JSON)
    reviewer_id: Mapped[str] = mapped_column(String(36))
    reason: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(default=True)


class User(Record):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("org", "email"),)
    email: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(30))
    branches: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(default=True)


class Branch(Record):
    __tablename__ = "branches"
    __table_args__ = (UniqueConstraint("org", "code"),)
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))


class AuthSession(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    csrf: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[float] = mapped_column(Float)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    window: Mapped[float] = mapped_column(Float, default=time.time)


class Config(Record):
    __tablename__ = "configurations"
    __table_args__ = (UniqueConstraint("org", "version"),)
    version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    published_by: Mapped[str] = mapped_column(String(36))


class Connector(Record):
    __tablename__ = "connectors"
    __table_args__ = (UniqueConstraint("org"),)
    encrypted: Mapped[str] = mapped_column(Text, default="")
    options: Mapped[dict] = mapped_column(JSON, default=dict)


class SpiderConnector(Record):
    __tablename__ = "spider_connectors"
    __table_args__ = (UniqueConstraint("org"),)
    encrypted: Mapped[str] = mapped_column(Text, default="")
    options: Mapped[dict] = mapped_column(JSON, default=dict)


class WorkerSlot(Base):
    __tablename__ = "worker_slots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner: Mapped[str] = mapped_column(String(36), default="")
    lease_until: Mapped[float] = mapped_column(Float, default=0)


class Case(Record):
    __tablename__ = "cases"
    branch_id: Mapped[str] = mapped_column(String(36), index=True)
    reference: Mapped[str] = mapped_column(String(180))
    customer: Mapped[str] = mapped_column(String(180))
    template: Mapped[str] = mapped_column(String(40))
    created_by: Mapped[str] = mapped_column(String(36))
    config_id: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(40), default="QUEUED")
    validation_status: Mapped[str] = mapped_column(String(30), default="PENDING")
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)


class Batch(Record):
    __tablename__ = "batches"
    branch_id: Mapped[str] = mapped_column(String(36))
    created_by: Mapped[str] = mapped_column(String(36))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    __table_args__ = (UniqueConstraint("org", "created_by", "idempotency_key"),)


class Document(Record):
    __tablename__ = "documents"
    branch_id: Mapped[str] = mapped_column(String(36), index=True)
    case_id: Mapped[str] = mapped_column(String(36), index=True)
    batch_id: Mapped[str] = mapped_column(String(36))
    filename: Mapped[str] = mapped_column(String(240))
    sha256: Mapped[str] = mapped_column(String(64))
    doc_type: Mapped[str] = mapped_column(String(50), default="unknown")
    status: Mapped[str] = mapped_column(String(40), default="QUEUED")
    validation_status: Mapped[str] = mapped_column(String(30), default="PENDING")
    classification: Mapped[dict] = mapped_column(JSON, default=dict)
    provider_state: Mapped[dict] = mapped_column(JSON, default=dict)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    normalized: Mapped[dict] = mapped_column(JSON, default=dict)
    overrides: Mapped[dict] = mapped_column(JSON, default=dict)
    validation: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")


class Job(Record):
    __tablename__ = "jobs"
    document_id: Mapped[str] = mapped_column(String(36), index=True)
    branch_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(30), default="process")
    status: Mapped[str] = mapped_column(String(30), default="QUEUED", index=True)
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    error: Mapped[str] = mapped_column(Text, default="")


class FieldReprocess(Record):
    __tablename__ = 'field_reprocess_requests'
    document_id: Mapped[str] = mapped_column(String(36), index=True)
    job_id: Mapped[str] = mapped_column(String(36), unique=True)
    branch_id: Mapped[str] = mapped_column(String(36), index=True)
    requested_by: Mapped[str] = mapped_column(String(36))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)


class Inbox(Record):
    __tablename__ = "inbox"
    branch_id: Mapped[str] = mapped_column(String(36), index=True)
    case_id: Mapped[str] = mapped_column(String(36))
    key: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(30))
    resolved: Mapped[bool] = mapped_column(default=False)
    read_by: Mapped[list] = mapped_column(JSON, default=list)


class Audit(Record):
    __tablename__ = "audit"
    branch_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    case_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    actor: Mapped[str] = mapped_column(String(100))
    event: Mapped[str] = mapped_column(String(80))
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class Report(Record):
    __tablename__ = "reports"
    case_id: Mapped[str] = mapped_column(String(36), index=True)
    branch_id: Mapped[str] = mapped_column(String(36))
    fingerprint: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(20), default="DRAFT")
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    __table_args__ = (UniqueConstraint("case_id", "fingerprint"),)


class CaseContext(Record):
    __tablename__ = "case_contexts"
    __table_args__ = (UniqueConstraint("case_id"),)
    case_id: Mapped[str] = mapped_column(String(36), index=True)
    branch_id: Mapped[str] = mapped_column(String(36))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class DatasetComparison(Record):
    __tablename__ = "dataset_comparisons"
    __table_args__ = (UniqueConstraint("case_id"),)
    case_id: Mapped[str] = mapped_column(String(36), index=True)
    branch_id: Mapped[str] = mapped_column(String(36))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class CaseRun(Record):
    __tablename__ = "case_runs"
    __table_args__ = (UniqueConstraint("case_id", "fingerprint"),)
    case_id: Mapped[str] = mapped_column(String(36), index=True)
    branch_id: Mapped[str] = mapped_column(String(36))
    fingerprint: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="QUEUED", index=True)
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    stage: Mapped[str] = mapped_column(String(40), default="CASE_SOP")
    error: Mapped[str] = mapped_column(Text, default="")


class CaseTask(Record):
    """Separate assignment table: additive schema, existing case rows untouched."""

    __tablename__ = "case_tasks"
    __table_args__ = (UniqueConstraint("org", "case_id"),)
    branch_id: Mapped[str] = mapped_column(String(36), index=True)
    case_id: Mapped[str] = mapped_column(String(36), index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(36), nullable=True)
    due_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    assigned_by: Mapped[str] = mapped_column(String(36))
