"""Read-only upgrade preview endpoints; publication remains a separate action."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.db import SessionLocal
from app.configuration.revisions import latest_config
from app.security import require_roles
from .service import (
    StaleConfiguration,
    comparison_candidates,
    preview_comparison_upgrade,
    preview_compatibility_upgrade,
)

router = APIRouter(
    prefix="/api/config/upgrades/comparisons", tags=["Configuration upgrades"]
)
compatibility_router = APIRouter(
    prefix="/api/config/upgrades/compatibility", tags=["Configuration upgrades"]
)
administrator = require_roles("bank_admin")


class PreviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    rule_ids: list[str] = Field(min_length=1, max_length=1000)
    payload: dict | None = None


class CompatibilityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    selected_keys: list[str] = Field(min_length=1, max_length=30)
    payload: dict | None = None


class FieldOptionsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    family: str = Field(min_length=1, max_length=40)
    payload: dict | None = None


@router.post("/fields")
def field_options(data: FieldOptionsInput, user=Depends(administrator)):
    from .field_options import text_field_options, policy_field_options
    from .contexts import enum_options

    with SessionLocal() as session:
        current = latest_config(session, user.org)
        if current.version != data.expected_version:
            raise HTTPException(409, "Configuration changed. Reload field options.")
        try:
            return {
                "fields": text_field_options(
                    current.payload if data.payload is None else data.payload,
                    data.family,
                ),
                **policy_field_options(
                    current.payload if data.payload is None else data.payload,
                    data.family,
                ),
                "context_options": enum_options(
                    current.payload if data.payload is None else data.payload,
                    data.family,
                ),
            }
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(422, str(exc)) from exc


@compatibility_router.get("")
def compatibility_candidates(user=Depends(administrator)):
    from .compatibility import missing_settings

    with SessionLocal() as session:
        current = latest_config(session, user.org)
        return {"version": current.version, **missing_settings(current.payload)}


@compatibility_router.post("/preview")
def compatibility_preview(data: CompatibilityInput, user=Depends(administrator)):
    with SessionLocal() as session:
        current = latest_config(session, user.org)
        try:
            return preview_compatibility_upgrade(
                current_version=current.version,
                expected_version=data.expected_version,
                payload=current.payload if data.payload is None else data.payload,
                selected_keys=data.selected_keys,
            )
        except StaleConfiguration as exc:
            raise HTTPException(409, str(exc)) from exc
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(422, str(exc)) from exc


@router.get("")
def candidates(user=Depends(administrator)):
    with SessionLocal() as session:
        current = latest_config(session, user.org)
        return {
            "version": current.version,
            "candidates": comparison_candidates(current.payload),
        }


@router.post("/preview")
def preview(data: PreviewInput, user=Depends(administrator)):
    with SessionLocal() as session:
        current = latest_config(session, user.org)
        try:
            return preview_comparison_upgrade(
                current_version=current.version,
                expected_version=data.expected_version,
                payload=current.payload if data.payload is None else data.payload,
                selected_ids=data.rule_ids,
            )
        except StaleConfiguration as exc:
            raise HTTPException(409, str(exc)) from exc
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(422, str(exc)) from exc
