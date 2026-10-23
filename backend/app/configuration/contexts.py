"""Shared versioned context contracts for rule editors and case annotations."""
import copy
import json
from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContextDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    label: str = Field(min_length=1, max_length=200)
    kind: Literal["enum", "text", "digits", "document_reference"]
    options: tuple[str, ...] = Field(default=(), max_length=100)
    profiles: tuple[str, ...] = Field(default=(), max_length=100)
    families: tuple[str, ...] = Field(default=(), max_length=100)
    max_length: int = Field(default=200, ge=1, le=200, strict=True)

    @model_validator(mode="after")
    def consistent_definition(self):
        if not self.label.strip():
            raise ValueError("Context labels must not be blank.")
        if any(not value.strip() or len(value) > self.max_length for value in self.options):
            raise ValueError("Context options must be nonblank and fit the value limit.")
        if any(len(values) != len(set(values)) for values in (self.options, self.profiles, self.families)):
            raise ValueError("Context choices and bindings must be distinct.")
        if bool(self.options) != (self.kind == "enum"):
            raise ValueError("Only enum contexts require options.")
        if bool(self.profiles) != (self.kind == "document_reference"):
            raise ValueError("Only document references require profile bindings.")
        return self


def default_definitions():
    return json.loads((Path(__file__).parents[1] / "config_data/context_defaults_v1.json").read_text(encoding="utf-8"))["definitions"]


def definitions(payload, family=None):
    raw = payload["context_definitions"] if "context_definitions" in payload else default_definitions()
    if not isinstance(raw, dict) or len(raw) > 100:
        raise ValueError("Configure at most 100 case-context definitions.")
    result = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,79}", key):
            raise ValueError("Context IDs must be lowercase identifiers.")
        if key in {"annotation", "rule_reviews"}:
            raise ValueError("Context ID is reserved for audit metadata.")
        definition = ContextDefinition.model_validate(value)
        if family is None or not definition.families or family in definition.families:
            result[key] = definition
    return result


def validate_definitions(payload):
    from app.document_families import families
    for value in definitions(payload).values():
        if set(value.profiles) - set(payload.get("profiles", {})):
            raise ValueError("Context document bindings require registered profiles.")
        if set(value.families) - set(families(payload)):
            raise ValueError("Context definitions require registered families.")


def enum_options(payload, family=None):
    return {key: list(value.options) for key, value in definitions(payload, family).items() if value.kind == "enum"}


def validate_values(payload, values, *, family=None, document_lookup=None, case_id=None):
    catalog = definitions(payload, family)
    for key, value in values.items():
        spec = catalog.get(key)
        if spec is None or not isinstance(value, str) or len(value) > spec.max_length:
            raise ValueError("Unknown case context field or invalid value length.")
        if spec.kind == "enum" and value not in spec.options:
            raise ValueError(f"{spec.label}: select a configured option.")
        if spec.kind == "digits" and value and not re.fullmatch(r"[0-9]+", value):
            raise ValueError(f"{spec.label}: use digits, preserving leading zeros.")
        if spec.kind == "document_reference" and value:
            doc = document_lookup(value) if document_lookup else None
            if doc is None or doc.case_id != case_id or doc.doc_type not in spec.profiles or doc.status != "COMPLETED":
                raise ValueError(f"{spec.label}: select a completed document of the correct type from this case.")


def propose_defaults(payload):
    if "context_definitions" in payload:
        raise ValueError("Context definitions are already configured; existing definitions cannot be replaced by defaults.")
    draft = copy.deepcopy(payload)
    draft["context_definitions"] = default_definitions()
    return draft
