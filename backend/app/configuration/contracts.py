"""Strict structural boundary; registered policies validate their own semantics."""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .codec import fingerprint


class ConfigurationEnvelope(BaseModel):
    # Extensions remain lossless while older publications retain extra sections.
    model_config = ConfigDict(extra='allow', frozen=True, strict=True)
    provider: str = Field(min_length=1, max_length=100)
    profiles: dict[str, dict[str, Any]] = Field(max_length=200)
    templates: dict[str, dict[str, Any]] = Field(min_length=1, max_length=100)
    maker_checker: bool
    classification_threshold: float = Field(ge=0, le=1)
    report_title: str = Field(min_length=1, max_length=200)
    name_directory: dict[str, Any]
    rules: list[dict[str, Any]] = Field(default_factory=list)
    sop_rules: list[dict[str, Any]] = Field(default_factory=list)
    generic_sop_rules: list[dict[str, Any]] = Field(default_factory=list)
    workflow: list[dict[str, Any]] = Field(default_factory=list)
    profile_variants: dict[str, dict[str, Any]] = Field(default_factory=dict)
    document_families: dict[str, dict[str, Any]] = Field(default_factory=dict)
    context_definitions: dict[str, dict[str, Any]] = Field(default_factory=dict)
    report_definitions: dict[str, dict[str, Any]] = Field(default_factory=dict)
    report_context: dict[str, str] = Field(default_factory=dict)
    report_mapping: dict[str, Any] = Field(default_factory=dict)
    customer_aliases: dict[str, str] = Field(default_factory=dict)
    suffix_aliases: dict[str, str] = Field(default_factory=dict)
    grouping_prefixes: list[str] = Field(default_factory=list)
    sop_message_templates: dict[str, str] = Field(default_factory=dict)
    forex_sop_policy: dict[str, Any] = Field(default_factory=dict)
    seed_releases: list[str] = Field(default_factory=list)


def validate_envelope(payload):
    """Validate without replacing payload or adding model defaults to a revision."""
    parsed = ConfigurationEnvelope.model_validate(payload)
    try:
        fingerprint(payload)
    except (TypeError, ValueError):
        raise ValueError('Configuration must contain finite JSON values only.') from None
    return parsed
