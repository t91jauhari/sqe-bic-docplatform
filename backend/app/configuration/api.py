"""Configuration HTTP boundary; application services own publication and replay."""

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.db import Case, SessionLocal
from app.configuration.revisions import latest_config
from app.configuration.validation import validate_config
from app.security import authorized, current_user, require_roles
from app.settings import settings
from app.configuration.profiles import profile_schema
from app.configuration.repository import get_revision

router = APIRouter(tags=["configuration"])
ADMIN = require_roles("bank_admin")


@router.get("/api/config")
def configuration(user=Depends(current_user)):
    from app.schema_descriptions import with_schemas

    with SessionLocal() as db:
        cfg = latest_config(db, user.org)
        return {
            "id": cfg.id,
            "version": cfg.version,
            "payload": with_schemas(
                cfg.payload,
                {
                    name: {"schema": profile_schema(cfg.payload, name)}
                    for name in cfg.payload["profiles"]
                },
            ),
            "can_edit": user.role == "bank_admin",
        }


class ConfigInput(BaseModel):
    expected_version: int
    payload: dict


@router.post("/api/config/publish")
def publish_config(data: ConfigInput, user=Depends(ADMIN)):
    from app.configuration.publication import (
        publish_configuration,
        ConfigurationStorageNotReady,
    )
    from app.configuration.service import StaleConfiguration

    try:
        with SessionLocal.begin() as db:
            return publish_configuration(
                db,
                organization=user.org,
                actor=user.id,
                expected_version=data.expected_version,
                payload=data.payload,
                storage_mode=settings.configuration_storage_mode,
            )
    except StaleConfiguration as exc:
        raise HTTPException(409, str(exc)) from exc
    except ConfigurationStorageNotReady as exc:
        raise HTTPException(503, str(exc)) from exc
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(422, str(exc))


@router.post("/api/config/test")
def test_config(data: ConfigInput, user=Depends(ADMIN)):
    from app.configuration.replay import replay_configuration

    try:
        validate_config(data.payload)
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(422, str(exc))
    with SessionLocal() as db:
        return replay_configuration(db, organization=user.org, payload=data.payload)


@router.get("/api/config/catalog")
def configuration_catalog(case_id: str | None = None, user=Depends(current_user)):
    from app.sop import CATEGORIES, OPERATORS, fields, approved_scope
    from app.configuration.contexts import definitions, enum_options
    from app.configuration.dataset_policy import comparison_policy
    from app.configuration.scoring import defaults as scoring_defaults

    with SessionLocal() as db:
        case = authorized(db, Case, case_id, user) if case_id else None
        config = (
            get_revision(db, case.config_id) if case else latest_config(db, user.org)
        )
        family = (
            config.payload["templates"][case.template].get("document_family", "forex")
            if case
            else None
        )
        context_definitions = definitions(config.payload, family)
    return {
        "score_groups": scoring_defaults(),
        "fields": fields(),
        "scope": approved_scope(),
        "operators": {k: sorted(v) if v else None for k, v in OPERATORS.items()},
        "context": enum_options(config.payload, family),
        "context_definitions": {
            key: value.model_dump(mode="json")
            for key, value in context_definitions.items()
        },
        "config_version": config.version,
        "dataset_comparison_policy": comparison_policy().model_dump(mode="json"),
        "categories": (*CATEGORIES, "DOCUMENT_VERIFICATION", "OBSERVATIONS"),
    }


@router.get("/api/config/export")
def configuration_export(user=Depends(ADMIN)):
    from app.config_workbook import MIME, export_config
    from app.sop import defaults

    with SessionLocal() as db:
        cfg = latest_config(db, user.org)
        try:
            data = export_config({**defaults(), **cfg.payload})
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    return Response(
        data,
        media_type=MIME,
        headers={
            "Content-Disposition": 'attachment; filename="document-workflow-config.xlsx"'
        },
    )


@router.post("/api/config/import")
async def configuration_import(file: UploadFile = File(), user=Depends(ADMIN)):
    from app.config_workbook import import_config
    from app.sop import defaults

    data = await file.read(2_000_001)
    if len(data) > 2_000_000:
        raise HTTPException(413, "Configuration workbook exceeds 2 MB.")
    with SessionLocal() as db:
        cfg = latest_config(db, user.org)
        base = {**defaults(), **cfg.payload}
        version = cfg.version
    payload, errors = await run_in_threadpool(import_config, data, base)
    return {
        "valid": not errors,
        "errors": errors,
        "payload": payload,
        "expected_version": version,
        "note": "Validated draft only. Review changes and replay stored cases before publishing.",
    }
