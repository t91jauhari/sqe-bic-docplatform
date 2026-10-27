from .configuration.repository import get_revision
import logging
import time

from llama_cloud import APIError

from .db import Case, Config, Document, Job, SessionLocal
from app.auditing import audit, serial
from app.case_lifecycle import refresh_case
from sqlalchemy import select
from .evidence import build_evidence, apply_evidence_review
from .provider import ProcessingIssue, run_provider, validate_extraction
from .provider_errors import api_diagnostic

log = logging.getLogger("sqe.worker")


def process_job(job_id, heartbeat=lambda: None):
    with SessionLocal.begin() as db:
        job = db.get(Job, job_id)
        if not job or job.status == "COMPLETED":
            return
        if job.action == "reprocess_fields":
            from .field_reprocessing import process_fields

            db.rollback()
            return process_fields(job_id, heartbeat)
        job.status = "RUNNING"
        job.lease_until = time.time() + 120
        doc = db.get(Document, job.document_id)
        case = db.get(Case, doc.case_id)
        case.status = "PROCESSING"
        case.updated_at = time.time()
        cfg = get_revision(db, case.config_id).payload
        from .document_families import extraction_config

        cfg = extraction_config(cfg, case.template)
        audit(
            db,
            doc.org,
            "worker",
            "document.started",
            doc.branch_id,
            doc.case_id,
            document_id=doc.id,
            job_id=job.id,
        )

    def beat():
        heartbeat()
        with SessionLocal.begin() as db:
            active = db.get(Job, job_id)
            active.lease_until = time.time() + 120

    try:
        if doc.raw and job.action != "reextract":
            response = {
                "extract_result": doc.raw,
                "extract_metadata": doc.metadata_json,
                "id": doc.provider_state.get("extract_job_id"),
                "parse_response_key": doc.provider_state.get("parse_response_key"),
            }
            classification = doc.classification
        else:
            response, classification = run_provider(doc, cfg, beat)
        if response is not None:
            from .spatial_grounding import normalize_response

            response = normalize_response(response)
            with SessionLocal.begin() as db:
                stored = db.get(Document, doc.id)
                stored.status = (
                    "EXTRACTING" if cfg.get("provider") == "spider-ai" else "VALIDATING"
                )
                stored.raw = serial(response["extract_result"])
                stored.metadata_json = serial(response.get("extract_metadata") or {})
                stored.classification = classification
            # Save raw extraction before validation so invalid schemas never cause another paid job.
            if (
                cfg.get("provider") == "spider-ai"
                and cfg["profiles"][doc.doc_type].get("validation_adapter") != "schema"
            ):
                from .spider_result import extraction_report

                report = extraction_report(doc, cfg, response)
            else:
                report = validate_extraction(doc, cfg, response)
            evidence = build_evidence(doc, response)
            if cfg.get("provider") == "spider-ai":
                report["visual_evidence"] = evidence
            else:
                apply_evidence_review(report, evidence)
            from .field_evidence import build_field_evidence, attach_field_evidence

            attach_field_evidence(report, build_field_evidence(doc, response))
            with SessionLocal.begin() as db:
                db.scalar(select(Case).where(Case.id == doc.case_id).with_for_update())
                from .profile_context import apply_context

                report = apply_context(db, doc, cfg, report)
                stored = db.get(Document, doc.id)
                stored.normalized = report["normalized"]
                stored.validation = report
                stored.validation_status = report["status"]
                stored.status = "COMPLETED"
                stored.error = ""
        with SessionLocal.begin() as db:
            db.scalar(select(Case).where(Case.id == doc.case_id).with_for_update())
            job = db.get(Job, job_id)
            job.status = "COMPLETED"
            job.lease_until = 0
            audit(
                db,
                doc.org,
                "worker",
                "document.completed",
                doc.branch_id,
                doc.case_id,
                document_id=doc.id,
                job_id=job_id,
            )
            refresh_case(db, doc.case_id)
            from .profile_context import queue_dependents

            queue_dependents(db, db.get(Document, doc.id), cfg)
    except Exception as exc:
        if isinstance(exc, ProcessingIssue):
            message = str(exc)
        elif isinstance(exc, APIError):
            with SessionLocal() as db:
                stage = db.get(Document, doc.id).provider_state.get(
                    "provider_stage", "UNKNOWN"
                )
            diagnostic = api_diagnostic(exc, stage)
            message = f"LlamaCloud {diagnostic['stage']} HTTP {diagnostic['status']}: {diagnostic['detail']}"
            log.error(
                "provider_rejected stage=%s endpoint=%s status=%s request_id=%s detail=%s",
                diagnostic["stage"],
                diagnostic["endpoint"],
                diagnostic["status"],
                diagnostic["request_id"],
                diagnostic["detail"],
            )

        elif isinstance(exc, ValueError):
            if cfg.get("provider") == "spider-ai":
                message = f"Spider-AI response decoding failed: {str(exc)[:800]}. Cached responses are retained."
            else:
                message = "Extraction/schema or policy validation failed. Inspect stored raw extraction and profile configuration."
        else:
            message = f"Processing interrupted ({type(exc).__name__}). Saved provider identifiers will be used on retry."
        log.exception(
            "document_failed job=%s document=%s error_type=%s",
            job_id,
            doc.id,
            type(exc).__name__,
        )
        with SessionLocal.begin() as db:
            stored = db.get(Document, doc.id)
            if isinstance(exc, APIError):
                stored.provider_state = {
                    **stored.provider_state,
                    "provider_error": diagnostic,
                }
            stored.status = "ERROR"
            stored.error = message
            job = db.get(Job, job_id)
            job.status = "ERROR"
            job.error = message
            job.lease_until = 0
            audit(
                db,
                doc.org,
                "worker",
                "document.failed",
                doc.branch_id,
                doc.case_id,
                document_id=doc.id,
                error_type=type(exc).__name__,
            )
            refresh_case(db, doc.case_id)
