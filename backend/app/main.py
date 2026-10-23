"""Application composition, lifecycle and middleware."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from minio.error import S3Error
from sqlalchemy import select
from urllib3.exceptions import HTTPError as StorageHTTPError
from app.db import SessionLocal
from app.settings import settings
from app.configuration.api import router as configuration_router
from app.extraction.api import router as extraction_settings_router
from app.configuration.routes import (
    router as configuration_upgrade_router,
    compatibility_router,
)
from app.configuration.dataset_routes import router as dataset_registry_router
from app.configuration.datasets import DatasetIntegrityError
from app.configuration.report_routes import router as report_configuration_router
from app.configuration.account_policy_routes import router as account_policy_router
from app.api.views import report_download_name  # Compatibility export.
from app.api.dependencies import log
from app.errors import ApplicationError, ErrorCode


def _warm_read_caches():
    from app.db import Case, Config, engine
    from app.configuration.repository import get_revision
    from app.configuration.revisions import latest_config
    from app.report_queries import ReportAudience, ReportQueries

    if getattr(getattr(engine, "dialect", None), "name", None) != "postgresql":
        return
    try:
        with SessionLocal() as db:
            orgs = list(db.scalars(select(Config.org).distinct()))
            for org in orgs:
                latest_config(db, org, copy_payload=False)
                ReportQueries(db, ReportAudience(org, None)).current()
            for config_id in db.scalars(select(Case.config_id).distinct()):
                if config_id:
                    get_revision(db, config_id, copy_payload=False)
    except Exception:
        pass


@asynccontextmanager
async def lifespan(_):
    from app.worker_capacity import initialize_slots

    initialize_slots()
    _warm_read_caches()
    yield


app = FastAPI(title="SQE Document Automation API", version="0.2.0", lifespan=lifespan)


@app.exception_handler(ApplicationError)
async def application_rejection(request, exc):
    statuses = {
        ErrorCode.FORBIDDEN: 403,
        ErrorCode.NOT_FOUND: 404,
        ErrorCode.CONFLICT: 409,
        ErrorCode.TOO_LARGE: 413,
        ErrorCode.INVALID_INPUT: 422,
    }
    return JSONResponse(status_code=statuses[exc.code], content={"detail": exc.detail})


app.include_router(configuration_router)

app.include_router(extraction_settings_router)

app.include_router(configuration_upgrade_router)

app.include_router(compatibility_router)

app.include_router(dataset_registry_router)

app.include_router(report_configuration_router)

app.include_router(account_policy_router)


@app.exception_handler(DatasetIntegrityError)
async def dataset_integrity_failure(request, exc):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(S3Error)
@app.exception_handler(StorageHTTPError)
async def storage_unavailable(request, exc):
    log.error("object_storage_failed error_type=%s", type(exc).__name__)
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Document storage is unavailable. Check MinIO connectivity, bucket and server credentials, then retry."
        },
    )


@app.middleware("http")
async def security_headers(request, call_next):
    origin = request.headers.get("origin")
    if (
        request.method not in {"GET", "HEAD", "OPTIONS"}
        and origin
        and origin not in settings.origins
    ):
        return Response("Origin not allowed", status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/health")
def health():
    with SessionLocal() as db:
        db.execute(select(1))
    return {"status": "ok", "version": "0.3.0"}


from app.api.authentication import router as authentication_router

app.include_router(authentication_router)
from app.api.operations import router as operations_router

app.include_router(operations_router)
from app.api.administration import router as administration_router

app.include_router(administration_router)
from app.api.intake import router as intake_router

app.include_router(intake_router)
from app.api.documents import router as documents_router

app.include_router(documents_router)
from app.api.cases import router as cases_router

app.include_router(cases_router)
from app.api.comparisons import router as comparisons_router

app.include_router(comparisons_router)
from app.api.evidence import router as evidence_router

app.include_router(evidence_router)
from app.api.field_processing import router as field_processing_router

app.include_router(field_processing_router)
from app.api.notifications import router as notifications_router

app.include_router(notifications_router)
from app.api.reports import router as reports_router

app.include_router(reports_router)
from app.api.exports import router as exports_router

app.include_router(exports_router)
