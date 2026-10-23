"""Explicit adoption of compatible published rules; historical reports stay frozen."""

from sqlalchemy import select
from app.access import authorized
from app.auditing import audit
from app.case_processing import queue_case
from app.configuration.repository import get_revision
from app.configuration.profiles import profile_schema
from app.schema_descriptions import contract
from app.db import Case, CaseRun, Config, Document, Job, SessionLocal
from app.errors import ApplicationError


def adopt_configuration(*, case_id, data, user):
    with SessionLocal.begin() as db:
        case = authorized(db, Case, case_id, user)
        db.scalar(select(Case).where(Case.id == case.id).with_for_update())
        current = get_revision(db, case.config_id)
        if current.version != data.expected_version:
            raise ApplicationError("conflict", "Case configuration changed. Reload before applying rules.")
        target_record = db.scalar(select(Config).where(Config.org == case.org, Config.version == data.target_version))
        if not target_record:
            raise ApplicationError("not_found", "Published configuration version not found.")
        target = get_revision(db, target_record.id)
        if target.version < current.version:
            raise ApplicationError("invalid_input", "Choose the current or a newer published configuration.")
        active = ["QUEUED", "DISPATCHED", "RUNNING"]
        documents = list(db.scalars(select(Document).where(Document.case_id == case.id)))
        if db.scalar(select(Job.id).where(Job.document_id.in_([d.id for d in documents]), Job.status.in_(active))) or db.scalar(select(CaseRun.id).where(CaseRun.case_id == case.id, CaseRun.status.in_(active))):
            raise ApplicationError("conflict", "Wait for document processing and SOP checks to finish.")
        if current.id == target.id:
            return {"changed": False, "config_version": current.version}
        if case.template not in target.payload["templates"]:
            raise ApplicationError("conflict", "The target version does not contain this transaction flow.")
        for doc in documents:
            if doc.doc_type not in current.payload["profiles"] or doc.doc_type not in target.payload["profiles"] or contract(profile_schema(current.payload, doc.doc_type)) != contract(profile_schema(target.payload, doc.doc_type)):
                raise ApplicationError("conflict", "Extraction schemas differ. Migrate or reprocess the affected documents before applying this version.")
        previous_id = case.config_id
        case.config_id = target.id
        db.flush()
        queue_case(db, case.id)
        audit(db, case.org, user.id, "case.configuration_adopted", case.branch_id, case.id,
              previous_config_id=previous_id, previous_version=current.version,
              config_id=target.id, config_version=target.version, reason=data.reason,
              extraction_reused=True)
        return {"changed": True, "config_version": target.version, "queued": True}
