"""Typed connector options and captured legacy defaults, without persistence."""
import copy
from functools import lru_cache
import json
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


@lru_cache(maxsize=1)
def _release():
    return json.loads((Path(__file__).parents[1] / "config_data/provider_defaults_v1.json").read_text(encoding="utf-8"))


def defaults(provider):
    key = "gemini" if provider in {"gemini", "google-gemini"} else provider
    return copy.deepcopy(_release()[key])


def secure_url(value):
    value = value.strip()
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Use an HTTPS base URL without embedded credentials, query or fragment.")
    return value.rstrip("/")


def bare_key(value):
    if value is not None and (not value.strip() or value.lower().startswith("bearer ") or any(c.isspace() for c in value)):
        raise ValueError("Supply only the API key, without Bearer or whitespace.")
    return value


class SpiderOptions(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    base_url: str = Field(default_factory=lambda: defaults("spider-ai")["base_url"], max_length=2000)
    model_id: str = Field(default_factory=lambda: defaults("spider-ai")["model_id"], min_length=1, max_length=200)
    temperature: float = Field(default_factory=lambda: defaults("spider-ai")["temperature"], ge=0, le=2, strict=True)
    top_p: float = Field(default_factory=lambda: defaults("spider-ai")["top_p"], ge=0, le=1, strict=True)
    max_tokens: int = Field(default_factory=lambda: defaults("spider-ai")["max_tokens"], ge=1, le=65536, strict=True)
    request_body_limit: int = Field(default_factory=lambda: defaults("spider-ai")["request_body_limit"], ge=1, le=20_971_520, strict=True)
    image_max_pixels: int = Field(default_factory=lambda: defaults("spider-ai")["image_max_pixels"], ge=256, le=4800, strict=True)
    image_jpeg_quality: int = Field(default_factory=lambda: defaults("spider-ai")["image_jpeg_quality"], ge=20, le=100, strict=True)
    classify_page_limit: int = Field(default_factory=lambda: defaults("spider-ai")["classify_page_limit"], ge=1, le=20, strict=True)
    image_max_bytes: int | None = Field(default=None, ge=1, le=5_242_880, strict=True, description="Blank keeps automatic image budgeting.")
    field_image_max_bytes: int = Field(default_factory=lambda: defaults("spider-ai")["field_image_max_bytes"], ge=1, le=5_242_880, strict=True)
    timeout_seconds: int = Field(default_factory=lambda: defaults("spider-ai")["timeout_seconds"], ge=1, le=1800, strict=True)
    connect_timeout_seconds: int = Field(default_factory=lambda: defaults("spider-ai")["connect_timeout_seconds"], ge=1, le=120, strict=True)

    _url = field_validator("base_url")(secure_url)

    @field_validator("model_id")
    @classmethod
    def model_name(cls, value):
        if not value.strip():
            raise ValueError("Supply a non-empty model ID.")
        return value.strip()


class SpiderConnectorInput(SpiderOptions):
    model_config = ConfigDict(extra="forbid", frozen=True)
    api_key: str | None = Field(default=None, max_length=500, repr=False)
    _key = field_validator("api_key")(bare_key)


class GeminiOptions(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    base_url: str = Field(default_factory=lambda: defaults("gemini")["base_url"], max_length=2000)
    model_id: str = Field(default_factory=lambda: defaults("gemini")["model_id"], min_length=1, max_length=200)
    temperature: float = Field(default_factory=lambda: defaults("gemini")["temperature"], ge=0, le=2, strict=True)
    top_p: float = Field(default_factory=lambda: defaults("gemini")["top_p"], ge=0, le=1, strict=True)
    max_tokens: int = Field(default_factory=lambda: defaults("gemini")["max_tokens"], ge=1, le=65536, strict=True)
    image_max_pixels: int = Field(default_factory=lambda: defaults("gemini")["image_max_pixels"], ge=256, le=4800, strict=True)
    image_jpeg_quality: int = Field(default_factory=lambda: defaults("gemini")["image_jpeg_quality"], ge=20, le=100, strict=True)
    classify_page_limit: int = Field(default_factory=lambda: defaults("gemini")["classify_page_limit"], ge=1, le=20, strict=True)
    timeout_seconds: int = Field(default_factory=lambda: defaults("gemini")["timeout_seconds"], ge=1, le=1800, strict=True)
    connect_timeout_seconds: int = Field(default_factory=lambda: defaults("gemini")["connect_timeout_seconds"], ge=1, le=120, strict=True)

    _url = field_validator("base_url")(secure_url)

    @field_validator("model_id")
    @classmethod
    def model_name(cls, value):
        if not value.strip():
            raise ValueError("Supply a non-empty model ID.")
        return value.strip()


class GeminiConnectorInput(GeminiOptions):
    model_config = ConfigDict(extra="forbid", frozen=True)
    api_key: str | None = Field(default=None, max_length=500, repr=False)
    _key = field_validator("api_key")(bare_key)


def _options_model(provider):
    if provider == "spider-ai":
        return SpiderOptions
    if provider in {"gemini", "google-gemini"}:
        return GeminiOptions
    raise ValueError(f"Extraction provider '{provider}' is not supported.")


def normalized_options(provider, options):
    model = _options_model(provider)
    return model.model_validate(options).model_dump(exclude_none=True)


def numeric_option_fields(provider="spider-ai"):
    result = []
    model = _options_model(provider)
    for key, field in model.model_json_schema()["properties"].items():
        variants = field.get("anyOf", [field])
        numeric = next((value for value in variants if value.get("type") in {"integer", "number"}), None)
        if numeric:
            result.append({"key": key, "label": field["title"], "minimum": numeric.get("minimum"),
                "maximum": numeric.get("maximum"), "integer": numeric["type"] == "integer",
                "nullable": any(value.get("type") == "null" for value in variants), "description": field.get("description", "")})
    return result


def administrative_options(provider, options):
    warning = None
    try:
        normalized = normalized_options(provider, options)
    except ValueError:
        normalized = normalized_options(provider, {})
        warning = "Stored connector settings are invalid. Compatible defaults are shown; review all fields before saving."
    return {"options": normalized, "numeric_fields": numeric_option_fields(provider), "configuration_warning": warning}
